from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class InspectionDecision(str, Enum):
    PASS = "pass"
    MANUAL_REVIEW = "manual_review"
    REWORK = "rework"
    REJECT = "reject"


class ReportStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


class Severity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Finding(StrictModel):
    finding: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    classification: Literal["observation", "hypothesis"]
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty: str = Field(min_length=1)
    region: str | None = None


class SpecialistReport(StrictModel):
    agent_name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    findings: list[Finding] = Field(default_factory=list)
    recommendation: str = Field(min_length=1)
    decision: InspectionDecision
    overall_confidence: float = Field(ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)
    status: ReportStatus = ReportStatus.COMPLETED
    error_message: str | None = None
    latency_seconds: float | None = Field(default=None, ge=0.0)


class FinalInspectionReport(StrictModel):
    incident_title: str = Field(min_length=1)
    decision: InspectionDecision
    severity: Severity
    confirmed_observations: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    agreements: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    unsupported_claims_removed: list[str] = Field(default_factory=list)
    immediate_actions: list[str] = Field(default_factory=list)
    follow_up_actions: list[str] = Field(default_factory=list)
    responsible_role: str = Field(min_length=1)
    additional_evidence_required: list[str] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    human_review_required: bool
    decision_rationale: str = Field(min_length=1)
    successful_agents: list[str] = Field(default_factory=list)
    failed_agents: list[str] = Field(default_factory=list)


class TimingMetrics(StrictModel):
    per_agent_latency_seconds: dict[str, float] = Field(default_factory=dict)
    parallel_stage_latency_seconds: float = Field(ge=0.0)
    verifier_latency_seconds: float = Field(ge=0.0)
    total_workflow_latency_seconds: float = Field(ge=0.0)
    estimated_sequential_specialist_latency_seconds: float = Field(ge=0.0)
    calculated_parallel_speedup: float = Field(ge=0.0)
    successful_request_count: int = Field(ge=0)
    failed_request_count: int = Field(ge=0)

    @field_validator("per_agent_latency_seconds")
    @classmethod
    def validate_per_agent_latency(cls, value: dict[str, float]) -> dict[str, float]:
        for agent_name, latency in value.items():
            if not agent_name:
                raise ValueError("Agent latency keys must be non-empty.")
            if latency < 0:
                raise ValueError("Agent latencies must be non-negative.")
        return value
