import asyncio
import json

import pytest

from agents import visual
from core.cerebras_client import CerebrasCallResult
from core.image_utils import validate_image_bytes
from core.orchestrator import run_inspection_workflow
from core.schemas import InspectionDecision, ReportStatus, SpecialistReport


class FakeClient:
    def __init__(self, responses: list[CerebrasCallResult]) -> None:
        self.responses = responses
        self.calls = 0

    async def chat_completion(self, *args, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


def specialist_payload(agent_name: str = "Agent") -> str:
    return json.dumps(
        {
            "agent_name": agent_name,
            "summary": "Visible difference requires review.",
            "findings": [
                {
                    "finding": "Surface mark",
                    "evidence": "A dark mark is visible on Image 2.",
                    "classification": "observation",
                    "confidence": 0.8,
                    "uncertainty": "Lighting may exaggerate contrast.",
                    "region": "center",
                }
            ],
            "recommendation": "Manual optical inspection.",
            "decision": "manual_review",
            "overall_confidence": 0.7,
            "limitations": ["Image-only inspection."],
        }
    )


def final_payload(failed_agents: list[str] | None = None) -> str:
    return json.dumps(
        {
            "incident_title": "Visible anomaly requires review",
            "decision": "manual_review",
            "severity": "medium",
            "confirmed_observations": ["Surface mark is visible."],
            "hypotheses": ["Could be contamination or damage."],
            "agreements": ["Specialists recommend human review."],
            "contradictions": [],
            "unsupported_claims_removed": ["No electrical failure claimed."],
            "immediate_actions": ["Quarantine for manual inspection."],
            "follow_up_actions": ["Clean and reinspect if appropriate."],
            "responsible_role": "Quality engineer",
            "additional_evidence_required": ["Magnified image"],
            "overall_confidence": 0.7,
            "human_review_required": True,
            "decision_rationale": "Visible evidence is limited but sufficient for review.",
            "successful_agents": ["Visual Difference Inspector"],
            "failed_agents": failed_agents or [],
        }
    )


def tiny_validated_image(label: str):
    from io import BytesIO
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="PNG")
    return validate_image_bytes(
        buffer.getvalue(),
        filename=f"{label}.png",
        label=label,
        max_bytes=100_000,
        declared_mime_type="image/png",
    )


def test_specialist_repairs_malformed_json_once() -> None:
    client = FakeClient(
        [
            CerebrasCallResult(True, "not json", 0.2),
            CerebrasCallResult(True, specialist_payload("Visual Difference Inspector"), 0.3),
        ]
    )

    report = asyncio.run(
        visual.run(client, "data:image/png;base64,aa", "data:image/png;base64,bb")
    )

    assert report.status == ReportStatus.COMPLETED
    assert report.agent_name == "Visual Difference Inspector"
    assert report.latency_seconds == pytest.approx(0.5)
    assert client.calls == 2


def test_specialist_api_failure_returns_structured_failure() -> None:
    client = FakeClient([CerebrasCallResult(False, None, 0.2, "timeout")])

    report = asyncio.run(
        visual.run(client, "data:image/png;base64,aa", "data:image/png;base64,bb")
    )

    assert report.status == ReportStatus.FAILED
    assert report.decision == InspectionDecision.MANUAL_REVIEW
    assert "timeout" in (report.error_message or "")


def test_orchestrator_tolerates_one_failed_specialist() -> None:
    client = FakeClient(
        [
            CerebrasCallResult(True, specialist_payload("Visual Difference Inspector"), 0.4),
            CerebrasCallResult(False, None, 0.5, "rate limit"),
            CerebrasCallResult(True, specialist_payload("Quality and Risk Assessor"), 0.6),
            CerebrasCallResult(True, specialist_payload("Factory Action Planner"), 0.7),
            CerebrasCallResult(True, final_payload(["Component and Layout Inspector"]), 0.8),
        ]
    )

    result = asyncio.run(
        run_inspection_workflow(
            tiny_validated_image("reference"),
            tiny_validated_image("inspection"),
            client=client,
        )
    )

    failed = [
        report.agent_name
        for report in result.specialist_reports
        if report.status == ReportStatus.FAILED
    ]
    assert failed == ["Component and Layout Inspector"]
    assert result.final_report.decision == InspectionDecision.MANUAL_REVIEW
    assert result.timing.failed_request_count == 1
    assert client.calls == 5
