import pytest
from pydantic import ValidationError

from core.schemas import Finding, InspectionDecision, SpecialistReport


def test_invalid_confidence_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Finding(
            finding="Scratch",
            evidence="Visible mark",
            classification="observation",
            confidence=1.5,
            uncertainty="Image is clear.",
        )


def test_decision_enum_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        SpecialistReport(
            agent_name="Agent",
            summary="Summary",
            findings=[],
            recommendation="Review",
            decision="maybe",
            overall_confidence=0.5,
            limitations=[],
        )


def test_valid_specialist_report_defaults_to_completed() -> None:
    report = SpecialistReport(
        agent_name="Agent",
        summary="Summary",
        findings=[],
        recommendation="Review",
        decision=InspectionDecision.MANUAL_REVIEW,
        overall_confidence=0.5,
        limitations=[],
    )

    assert report.status.value == "completed"
