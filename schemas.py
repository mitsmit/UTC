from enum import Enum
from pydantic import BaseModel


class RiskLevel(str, Enum):
    red = "red"
    yellow = "yellow"
    green = "green"


class Clause(BaseModel):
    summary:    str
    risk:       RiskLevel
    unusual:    bool
    citation:   str
    data_topic: str | None = None   # topic tag (data/privacy or legal/commercial)

    # ── Extracted entities ────────────────────────────────────────────────────
    data_types:          list[str] = []   # email, location, biometrics, IP address…
    purposes:            list[str] = []   # advertising, analytics, fraud prevention…
    actors:              list[str] = []   # the company, advertisers, data brokers…
    legal_constructs:    list[str] = []   # indemnification, force majeure, liability cap…
    retention_duration:  str | None = None  # "90 days", "indefinitely", "until deletion"…
    consent_mechanism:   str | None = None  # "opt-in" | "opt-out" | "implied" | "none"
    monetization_signal: bool = False       # True if clause monetises user data


class AnalysisResult(BaseModel):
    source: str                        # URL, filename, or "pasted text"
    tldr: str
    overall_risk: RiskLevel
    rights_given_up: list[Clause]
    obligations: list[Clause]
    benefits: list[Clause]
    unusual_clauses: list[Clause]


class ClauseCounts(BaseModel):
    rights_given_up: int
    obligations: int
    benefits: int
    unusual_clauses: int


class HistoryEntry(BaseModel):
    id: str
    timestamp: str
    input_type: str        # "url" | "pdf" | "text"
    input_label: str
    source: str
    overall_risk: RiskLevel
    tldr: str
    counts: ClauseCounts


class AnalyzeRequest(BaseModel):
    text: str | None = None
    url: str | None = None


class AnalyzeResponse(BaseModel):
    result: AnalysisResult
    char_count: int
    chunk_count: int
