"""Pydantic schemas for the compliance RAG output."""

from enum import Enum
from pydantic import BaseModel, Field


class ComplianceStatus(str, Enum):
    compliant    = "COMPLIANT"
    gap          = "GAP"
    partial      = "PARTIAL"
    not_applicable = "N/A"


class ComplianceGap(BaseModel):
    regulation:      str = Field(description="Regulation name, e.g. 'GDPR'")
    article:         str = Field(description="Specific article or section, e.g. 'Art. 17'")
    requirement:     str = Field(description="What the regulation requires")
    tc_clause:       str = Field(description="Relevant clause from the T&C being reviewed")
    status:          ComplianceStatus
    gap_description: str = Field(description="What is missing or non-compliant; empty if COMPLIANT")
    severity:        str = Field(description="HIGH | MEDIUM | LOW — only meaningful for GAP/PARTIAL")


class RegulationResult(BaseModel):
    regulation: str
    status:     ComplianceStatus
    gaps:       list[ComplianceGap]
    summary:    str


class ComplianceReport(BaseModel):
    overall:     ComplianceStatus
    regulations: list[RegulationResult]
    summary:     str
    tc_source:   str
