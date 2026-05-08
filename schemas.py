from enum import Enum
from pydantic import BaseModel


class RiskLevel(str, Enum):
    red = "red"
    yellow = "yellow"
    green = "green"


class Clause(BaseModel):
    summary: str
    risk: RiskLevel
    unusual: bool
    citation: str


class AnalysisResult(BaseModel):
    source: str                        # URL, filename, or "pasted text"
    tldr: str
    overall_risk: RiskLevel
    rights_given_up: list[Clause]
    obligations: list[Clause]
    benefits: list[Clause]
    unusual_clauses: list[Clause]


class AnalyzeRequest(BaseModel):
    text: str | None = None
    url: str | None = None


class AnalyzeResponse(BaseModel):
    result: AnalysisResult
    char_count: int
    chunk_count: int
