"""
Send each chunk to GPT-4o and extract structured clauses.
Chunks are processed concurrently for speed.
"""

import json
import asyncio
from openai import AsyncOpenAI

import config
from prompts import CHUNK_ANALYSIS_PROMPT
from schemas import Clause, RiskLevel

_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)


def _parse_clauses(raw: str) -> list[dict]:
    """Parse JSON array from LLM response, tolerating markdown fences."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip().rstrip("`").strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


async def _analyze_chunk(chunk: str, index: int) -> list[dict]:
    try:
        response = await _client.chat.completions.create(
            model=config.CHAT_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": CHUNK_ANALYSIS_PROMPT.format(chunk=chunk),
                }
            ],
            temperature=0,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        parsed = json.loads(raw)
        # model returns {"clauses": [...]} per the prompt instruction
        if isinstance(parsed, dict):
            for key in ("clauses", "result", "items", "data"):
                if key in parsed and isinstance(parsed[key], list):
                    return parsed[key]
            # fallback: first list value found
            for v in parsed.values():
                if isinstance(v, list):
                    return v
            return []
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


async def _analyze_all_chunks(chunks: list[str]) -> list[dict]:
    tasks = [_analyze_chunk(chunk, i) for i, chunk in enumerate(chunks)]
    results = await asyncio.gather(*tasks)
    all_clauses = []
    for batch in results:
        all_clauses.extend(batch)
    return all_clauses


def analyze_chunks(chunks: list[str]) -> list[dict]:
    """Synchronous entry point — runs async analysis and returns raw clause dicts."""
    return asyncio.run(_analyze_all_chunks(chunks))


def to_clause(raw: dict) -> Clause | None:
    """Convert a raw dict from the LLM into a validated Clause object."""
    try:
        risk_str = str(raw.get("risk", "yellow")).lower()
        risk = RiskLevel(risk_str) if risk_str in ("red", "yellow", "green") else RiskLevel.yellow
        return Clause(
            summary=str(raw.get("summary", "")).strip(),
            risk=risk,
            unusual=bool(raw.get("unusual", False)),
            citation=str(raw.get("citation", "")).strip()[:300],
        )
    except Exception:
        return None
