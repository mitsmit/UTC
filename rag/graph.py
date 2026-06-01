"""
LangGraph compliance agent.

Flow
----
                        START
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
   retrieve_HIPAA   retrieve_GDPR   retrieve_EU_AI
          │               │               │
          └───────────────┼───────────────┘
                          ▼
                       compare
                          │
                         END  → ComplianceReport

Public API
----------
run(tc_text, tc_source, regulations=None) -> ComplianceReport
    regulations: list of slugs to check, default ["HIPAA","GDPR","EU_AI_ACT"]
"""

import json
import sys
from pathlib import Path
from typing import Annotated

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from rag.schemas import ComplianceReport, ComplianceGap, ComplianceStatus, RegulationResult
from rag import store

_ALL_REGS = ["HIPAA", "GDPR", "EU_AI_ACT"]

_REG_CONTEXT = {
    "HIPAA":     "US Health Insurance Portability and Accountability Act — governs PHI (protected health information), data safeguards, breach notification, and patient rights.",
    "GDPR":      "EU General Data Protection Regulation — governs personal data processing, lawful basis, data subject rights (access, erasure, portability), consent, DPO requirements.",
    "EU_AI_ACT": "EU Artificial Intelligence Act — governs AI system risk classification, transparency obligations, prohibited practices, high-risk AI requirements, GPAI model rules.",
}

_COMPARE_PROMPT = """\
You are a legal compliance analyst. You have been given:

1. A Terms & Conditions document (the "T&C").
2. Retrieved excerpts from {regulation} ({reg_context}).

Your task: analyse the T&C for compliance with {regulation}.

For each compliance requirement found in the retrieved excerpts:
- Identify the relevant T&C clause (or note its absence).
- Rate compliance: COMPLIANT, GAP, PARTIAL, or N/A.
- If GAP or PARTIAL, describe what is missing and rate severity (HIGH / MEDIUM / LOW).

Return a JSON object exactly matching this schema:
{{
  "regulation": "{regulation}",
  "status": "COMPLIANT | GAP | PARTIAL | N/A",
  "summary": "2-3 sentence plain-English summary",
  "gaps": [
    {{
      "regulation": "{regulation}",
      "article": "article/section reference",
      "requirement": "what the regulation requires",
      "tc_clause": "relevant text from the T&C, or 'Not addressed'",
      "status": "COMPLIANT | GAP | PARTIAL | N/A",
      "gap_description": "what is missing or non-compliant (empty if COMPLIANT)",
      "severity": "HIGH | MEDIUM | LOW"
    }}
  ]
}}

--- RETRIEVED {regulation} EXCERPTS ---
{regulation_chunks}

--- T&C TEXT (first 8000 chars) ---
{tc_text}
"""

_AGGREGATE_PROMPT = """\
You are a senior compliance analyst. Given per-regulation results below, produce an overall compliance report.

Return a JSON object exactly matching this schema:
{{
  "overall": "COMPLIANT | GAP | PARTIAL | N/A",
  "summary": "3-5 sentence plain-English executive summary highlighting the biggest risks",
  "regulations": [ ... (pass through the per-regulation results unchanged) ... ],
  "tc_source": "{tc_source}"
}}

Per-regulation results:
{per_reg_json}
"""


# ── State ─────────────────────────────────────────────────────────────────────

class AgentState(BaseModel):
    tc_text:    str
    tc_source:  str
    regulations: list[str]

    # retrieved chunks per regulation (filled by retrieve nodes)
    retrieved:  dict[str, str] = {}

    # per-regulation analysis results (filled by compare nodes)
    reg_results: list[dict] = []

    # final report
    report: dict | None = None


# ── LLM ───────────────────────────────────────────────────────────────────────

def _llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=config.CHAT_MODEL,
        api_key=config.OPENAI_API_KEY,
        temperature=0,
    )


# ── Node factories ─────────────────────────────────────────────────────────────

def _make_retrieve_node(slug: str):
    def retrieve(state: AgentState) -> AgentState:
        if slug not in state.regulations:
            return state
        if not store.is_ingested(slug):
            # gracefully skip un-ingested regulations
            retrieved = dict(state.retrieved)
            retrieved[slug] = f"[{slug} not yet ingested — run: python -m rag.ingest --reg {slug}]"
            return state.model_copy(update={"retrieved": retrieved})
        ret    = store.retriever(slug, k=6)
        docs   = ret.invoke(state.tc_text[:3000])
        text   = "\n\n---\n\n".join(d.page_content for d in docs)
        retrieved = dict(state.retrieved)
        retrieved[slug] = text
        return state.model_copy(update={"retrieved": retrieved})
    retrieve.__name__ = f"retrieve_{slug}"
    return retrieve


def _make_compare_node(slug: str):
    def compare(state: AgentState) -> AgentState:
        if slug not in state.regulations:
            return state
        chunks = state.retrieved.get(slug, "")
        if chunks.startswith("[") and "not yet ingested" in chunks:
            # regulation not ingested — return a placeholder result
            result = {
                "regulation": slug,
                "status": "N/A",
                "summary": f"{slug} not ingested. Run python -m rag.ingest --reg {slug}",
                "gaps": [],
            }
            reg_results = list(state.reg_results) + [result]
            return state.model_copy(update={"reg_results": reg_results})

        prompt = _COMPARE_PROMPT.format(
            regulation=slug,
            reg_context=_REG_CONTEXT.get(slug, slug),
            regulation_chunks=chunks[:6000],
            tc_text=state.tc_text[:8000],
        )
        response = _llm().invoke(prompt)
        raw = response.content.strip()
        # strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip().rstrip("`").strip()
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {"regulation": slug, "status": "GAP",
                      "summary": "Parse error — raw LLM output stored.",
                      "gaps": [], "_raw": raw}

        reg_results = list(state.reg_results) + [result]
        return state.model_copy(update={"reg_results": reg_results})
    compare.__name__ = f"compare_{slug}"
    return compare


def _aggregate_node(state: AgentState) -> AgentState:
    prompt = _AGGREGATE_PROMPT.format(
        tc_source=state.tc_source,
        per_reg_json=json.dumps(state.reg_results, indent=2),
    )
    response = _llm().invoke(prompt)
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip().rstrip("`").strip()
    try:
        report = json.loads(raw)
    except json.JSONDecodeError:
        report = {
            "overall": "GAP",
            "summary": "Aggregation parse error.",
            "regulations": state.reg_results,
            "tc_source": state.tc_source,
        }
    return state.model_copy(update={"report": report})


# ── Graph builder ──────────────────────────────────────────────────────────────

def _build_graph(regulations: list[str]):
    builder = StateGraph(AgentState)

    for slug in regulations:
        builder.add_node(f"retrieve_{slug}", _make_retrieve_node(slug))
        builder.add_node(f"compare_{slug}",  _make_compare_node(slug))

    builder.add_node("aggregate", _aggregate_node)

    # entry: fan-out to all retrieve nodes
    first = f"retrieve_{regulations[0]}"
    builder.set_entry_point(first)
    for slug in regulations[1:]:
        builder.add_edge(first, f"retrieve_{slug}")

    # retrieve → compare (one-to-one)
    for slug in regulations:
        builder.add_edge(f"retrieve_{slug}", f"compare_{slug}")
        builder.add_edge(f"compare_{slug}",  "aggregate")

    builder.add_edge("aggregate", END)
    return builder.compile()


# ── Public entry point ─────────────────────────────────────────────────────────

def run(
    tc_text:     str,
    tc_source:   str,
    regulations: list[str] | None = None,
) -> dict:
    """
    Run the compliance agent. Returns raw report dict (matches ComplianceReport schema).
    """
    regs  = [r.upper() for r in (regulations or _ALL_REGS)]
    graph = _build_graph(regs)

    initial = AgentState(tc_text=tc_text, tc_source=tc_source, regulations=regs)
    final   = graph.invoke(initial)

    return final["report"] if isinstance(final, dict) else final.report
