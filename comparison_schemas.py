from pydantic import BaseModel
from schemas import RiskLevel


class ClauseStance(BaseModel):
    present: bool
    risk: RiskLevel
    summary: str
    winner: bool = False


class TopicComparison(BaseModel):
    topic: str
    stances: dict[str, ClauseStance]   # company_name → stance


class CompanyScore(BaseModel):
    company: str
    score: int       # 0–100 user-friendliness
    label: str       # "Aggressive" | "Mixed" | "Fair" | "User-friendly"


class ComparisonResult(BaseModel):
    companies: list[str]
    topics: list[TopicComparison]
    scores: list[CompanyScore]
    overall_winner: str
    summary: str


class CompanyInput(BaseModel):
    name: str
    text: str | None = None
    url: str | None = None


class CompareRequest(BaseModel):
    companies: list[CompanyInput]   # 2–3 entries
