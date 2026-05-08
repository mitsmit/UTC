"""
Merge clause dicts from all chunks, deduplicate, rank by risk,
generate TL;DR and overall risk rating.
"""

from openai import OpenAI

import config
from analyzer import to_clause
from prompts import OVERALL_RISK_PROMPT, TLDR_PROMPT
from schemas import AnalysisResult, Clause, RiskLevel

_client = OpenAI(api_key=config.OPENAI_API_KEY)

_RISK_ORDER = {RiskLevel.red: 0, RiskLevel.yellow: 1, RiskLevel.green: 2}

CATEGORY_MAP = {
    "rights_given_up": "rights_given_up",
    "rights given up": "rights_given_up",
    "obligations": "obligations",
    "obligation": "obligations",
    "benefits": "benefits",
    "benefit": "benefits",
    "unusual": "unusual_clauses",
    "unusual_clauses": "unusual_clauses",
}


def _deduplicate(clauses: list[Clause]) -> list[Clause]:
    """Remove near-duplicate summaries (same first 60 chars)."""
    seen: set[str] = set()
    unique = []
    for c in clauses:
        key = c.summary[:60].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def _sort_by_risk(clauses: list[Clause]) -> list[Clause]:
    return sorted(clauses, key=lambda c: _RISK_ORDER[c.risk])


def _generate_tldr(buckets: dict[str, list[Clause]]) -> str:
    high_risk = [
        c.summary
        for bucket in buckets.values()
        for c in bucket
        if c.risk == RiskLevel.red
    ]
    unusual = [c.summary for c in buckets.get("unusual_clauses", []) if c.unusual]
    findings = "\n".join(f"- {s}" for s in (high_risk + unusual)[:10])

    if not findings:
        findings = "No high-risk clauses identified. Document appears standard."

    response = _client.chat.completions.create(
        model=config.CHAT_MODEL,
        messages=[{"role": "user", "content": TLDR_PROMPT.format(findings=findings)}],
        max_tokens=80,
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


def _overall_risk(buckets: dict[str, list[Clause]]) -> RiskLevel:
    all_risks = [c.risk for bucket in buckets.values() for c in bucket]
    risk_summary = ", ".join(r.value for r in all_risks) if all_risks else "none"

    response = _client.chat.completions.create(
        model=config.CHAT_MODEL,
        messages=[
            {"role": "user", "content": OVERALL_RISK_PROMPT.format(risk_summary=risk_summary)}
        ],
        max_tokens=5,
        temperature=0,
    )
    verdict = response.choices[0].message.content.strip().lower()
    for level in ("red", "yellow", "green"):
        if level in verdict:
            return RiskLevel(level)
    return RiskLevel.yellow


def aggregate(raw_clauses: list[dict], source: str) -> AnalysisResult:
    buckets: dict[str, list[Clause]] = {
        "rights_given_up": [],
        "obligations": [],
        "benefits": [],
        "unusual_clauses": [],
    }

    for raw in raw_clauses:
        clause = to_clause(raw)
        if not clause or not clause.summary:
            continue
        category_raw = str(raw.get("category", "")).lower().strip()
        bucket = CATEGORY_MAP.get(category_raw, "obligations")
        buckets[bucket].append(clause)

    # Deduplicate and sort each bucket
    for key in buckets:
        buckets[key] = _sort_by_risk(_deduplicate(buckets[key]))

    tldr = _generate_tldr(buckets)
    overall = _overall_risk(buckets)

    return AnalysisResult(
        source=source,
        tldr=tldr,
        overall_risk=overall,
        rights_given_up=buckets["rights_given_up"],
        obligations=buckets["obligations"],
        benefits=buckets["benefits"],
        unusual_clauses=buckets["unusual_clauses"],
    )
