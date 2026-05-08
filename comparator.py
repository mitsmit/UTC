"""
Orchestrates the full comparison pipeline:
  1. Analyze each company's T&C text (reuses existing pipeline)
  2. Align clauses onto common topics
  3. Score each company 0-100
  4. Write a plain-English summary
"""

import json

from openai import OpenAI

import aggregator
import analyzer
import preprocessor
from comparison_prompts import (
    COMPARISON_SUMMARY_PROMPT,
    SCORING_PROMPT,
    TOPIC_ALIGNMENT_PROMPT,
)
from comparison_schemas import (
    ClauseStance,
    CompanyScore,
    ComparisonResult,
    TopicComparison,
)
from schemas import AnalysisResult, RiskLevel

_client = OpenAI()


# ── Step 1: analyze each company ─────────────────────────────────────────────

def analyze_company(name: str, text: str) -> AnalysisResult:
    chunks = preprocessor.chunk(text)
    raw_clauses = analyzer.analyze_chunks(chunks)
    result = aggregator.aggregate(raw_clauses, source=name)
    return result


# ── Step 2: align topics ──────────────────────────────────────────────────────

def _flatten_clauses(results: dict[str, AnalysisResult]) -> str:
    parts = []
    for company, result in results.items():
        clauses = (
            result.rights_given_up
            + result.obligations
            + result.benefits
            + result.unusual_clauses
        )
        bullet_lines = "\n".join(
            f"  [{c.risk.value}] {c.summary}" for c in clauses
        )
        parts.append(f"{company}:\n{bullet_lines}")
    return "\n\n".join(parts)


def _align_topics(results: dict[str, AnalysisResult]) -> list[TopicComparison]:
    company_clauses = _flatten_clauses(results)
    companies = list(results.keys())

    prompt = TOPIC_ALIGNMENT_PROMPT.format(
        n=len(companies),
        company_clauses=company_clauses,
    )
    response = _client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=2500,
    )
    raw = json.loads(response.choices[0].message.content)
    topics_data = raw.get("topics", [])

    topics = []
    for t in topics_data:
        stances = {}
        for company, stance_data in t.get("stances", {}).items():
            risk_str = str(stance_data.get("risk", "yellow")).lower()
            risk = RiskLevel(risk_str) if risk_str in ("red", "yellow", "green") else RiskLevel.yellow
            stances[company] = ClauseStance(
                present=bool(stance_data.get("present", True)),
                risk=risk,
                summary=str(stance_data.get("summary", "")),
                winner=bool(stance_data.get("winner", False)),
            )
        if stances:
            topics.append(TopicComparison(topic=t.get("topic", ""), stances=stances))

    return topics


# ── Step 3: score companies ───────────────────────────────────────────────────

def _score_companies(results: dict[str, AnalysisResult]) -> list[CompanyScore]:
    risk_summaries = []
    for company, result in results.items():
        all_clauses = (
            result.rights_given_up
            + result.obligations
            + result.benefits
            + result.unusual_clauses
        )
        counts = {
            "red": sum(1 for c in all_clauses if c.risk == RiskLevel.red),
            "yellow": sum(1 for c in all_clauses if c.risk == RiskLevel.yellow),
            "green": sum(1 for c in all_clauses if c.risk == RiskLevel.green),
        }
        risk_summaries.append(
            f"{company}: {counts['red']} red, {counts['yellow']} yellow, {counts['green']} green clauses"
        )

    prompt = SCORING_PROMPT.format(risk_summaries="\n".join(risk_summaries))
    response = _client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=400,
    )
    raw = json.loads(response.choices[0].message.content)
    scores_data = raw.get("scores", [])

    return [
        CompanyScore(
            company=s["company"],
            score=int(s.get("score", 50)),
            label=str(s.get("label", "Mixed")),
        )
        for s in scores_data
    ]


# ── Step 4: summary ───────────────────────────────────────────────────────────

def _write_summary(
    winner: str,
    scores: list[CompanyScore],
    topics: list[TopicComparison],
) -> str:
    scores_text = ", ".join(f"{s.company}: {s.score}/100 ({s.label})" for s in scores)
    topics_text = "; ".join(t.topic for t in topics[:5])

    response = _client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": COMPARISON_SUMMARY_PROMPT.format(
                    winner=winner,
                    scores=scores_text,
                    topics=topics_text,
                ),
            }
        ],
        temperature=0.3,
        max_tokens=250,
    )
    return response.choices[0].message.content.strip()


# ── Main entry point ──────────────────────────────────────────────────────────

def compare(results: dict[str, AnalysisResult]) -> ComparisonResult:
    """
    results: {company_name: AnalysisResult}
    Returns a ComparisonResult ready for the API / UI.
    """
    companies = list(results.keys())
    topics = _align_topics(results)
    scores = _score_companies(results)

    overall_winner = max(scores, key=lambda s: s.score).company if scores else companies[0]
    summary = _write_summary(overall_winner, scores, topics)

    return ComparisonResult(
        companies=companies,
        topics=topics,
        scores=scores,
        overall_winner=overall_winner,
        summary=summary,
    )
