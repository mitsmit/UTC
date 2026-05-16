"""
Append-only analysis history stored in history.json.
Each entry captures the input label, timestamp, and a compact result summary.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

HISTORY_FILE       = Path("./history.json")
LAST_ANALYSIS_FILE = Path("./last_analysis.json")


def _load_raw() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_raw(entries: list[dict]) -> None:
    try:
        HISTORY_FILE.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass   # read-only filesystem (e.g. Vercel serverless) — silently skip


def save(
    input_type: str,       # "url" | "pdf" | "text"
    input_label: str,      # URL, filename, or first 120 chars of pasted text
    result: dict,          # the AnalysisResult dict from the API response
) -> dict:
    """Append one entry and return it."""
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_type": input_type,
        "input_label": input_label[:120],
        "source": result.get("source", input_label)[:80],
        "overall_risk": result.get("overall_risk", "yellow"),
        "tldr": result.get("tldr", ""),
        "counts": {
            "rights_given_up": len(result.get("rights_given_up", [])),
            "obligations":      len(result.get("obligations", [])),
            "benefits":         len(result.get("benefits", [])),
            "unusual_clauses":  len(result.get("unusual_clauses", [])),
        },
    }
    entries = _load_raw()
    entries.insert(0, entry)   # newest first
    _save_raw(entries)
    return entry


def load() -> list[dict]:
    """Return all history entries, newest first."""
    return _load_raw()


def delete(entry_id: str) -> bool:
    """Remove a single entry by id. Returns True if found and removed."""
    entries = _load_raw()
    filtered = [e for e in entries if e["id"] != entry_id]
    if len(filtered) == len(entries):
        return False
    _save_raw(filtered)
    return True


def clear() -> int:
    """Delete all entries. Returns the count that was removed."""
    count = len(_load_raw())
    _save_raw([])
    return count


def save_last_analysis(data: dict) -> None:
    """Persist the full AnalyzeResponse dict so the UI can pre-load it on startup."""
    try:
        LAST_ANALYSIS_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass   # read-only filesystem (e.g. Vercel serverless) — silently skip


def load_last_analysis() -> dict | None:
    """Return the last full analysis, or None if not available."""
    if not LAST_ANALYSIS_FILE.exists():
        return None
    try:
        return json.loads(LAST_ANALYSIS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
