from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class ClaimInput(BaseModel):
    policy_number: str
    claimant_name: str
    claimant_email: EmailStr
    claim_type: str
    claim_amount: float = Field(gt=0)
    incident_date: date
    description: str


class CoverageResult(BaseModel):
    covered: bool
    reason: str
    clause: str | None = None


class DocumentClassification(BaseModel):
    document_type: Literal[
        "claim_form",
        "invoice",
        "medical_report",
        "identity",
        "supporting_document",
        "unknown",
    ]
    confidence: float = Field(ge=0, le=1)


class ExtractedFields(BaseModel):
    claimant_name: str | None = None
    policy_number: str | None = None
    amount: float | None = None
    incident_date: str | None = None
    provider_name: str | None = None
    additional_fields: dict[str, Any] = Field(default_factory=dict)


class CaseSummary(BaseModel):
    facts: list[str]
    evidence: list[str]
    missing_information: list[str]
    risks: list[str]
    policy_citations: list[str]
    next_action: str


class HumanDecision(BaseModel):
    decision: Literal["approve", "reject", "request_information"]
    rationale: str
    approver: str
