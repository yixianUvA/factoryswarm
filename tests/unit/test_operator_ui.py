from __future__ import annotations

from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from core.orchestrator import WorkflowResult
from core.schemas import (
    FinalInspectionReport,
    InspectionDecision,
    ReportStatus,
    Severity,
    SpecialistReport,
    TimingMetrics,
)
from ui.components import (
    agent_rows,
    concise_result_summary,
    priority_warnings,
    result_status_text,
)
from ui.state import (
    DEFAULT_AGENT_STATUSES,
    OPERATOR_MODE,
    clear_stale_result_if_needed,
    image_pair_fingerprint,
    initialize_ui_state,
    next_item,
    result_matches_current_images,
    set_completed_state,
    should_auto_run,
)


def fake_image(data_uri: str = "data:image/png;base64,abc"):
    return SimpleNamespace(data_uri=data_uri)


def fake_result(
    decision: InspectionDecision = InspectionDecision.MANUAL_REVIEW,
    failed_agents: list[str] | None = None,
) -> WorkflowResult:
    final_report = FinalInspectionReport(
        incident_title="Visible material requires review",
        decision=decision,
        severity=Severity.MEDIUM if decision != InspectionDecision.PASS else Severity.NONE,
        confirmed_observations=["Dark material around central IC"],
        hypotheses=["USB connector surface discoloration"],
        agreements=["Specialists recommend review"],
        contradictions=[],
        unsupported_claims_removed=[],
        immediate_actions=["Inspect under magnification"],
        follow_up_actions=["Clean and reinspect if appropriate"],
        responsible_role="Quality engineer",
        additional_evidence_required=["Magnified optical image"],
        overall_confidence=0.68,
        human_review_required=decision != InspectionDecision.PASS,
        decision_rationale="Visible evidence warrants review.",
        successful_agents=["Visual Difference Inspector"],
        failed_agents=failed_agents or [],
    )
    specialist_report = SpecialistReport(
        agent_name="Component and Layout Inspector",
        summary="Component check unavailable." if failed_agents else "Visible issue found.",
        findings=[],
        recommendation="Manual review.",
        decision=InspectionDecision.MANUAL_REVIEW,
        overall_confidence=0.5,
        limitations=[],
        status=ReportStatus.FAILED if failed_agents else ReportStatus.COMPLETED,
        error_message="timeout" if failed_agents else None,
        latency_seconds=0.2,
    )
    timing = TimingMetrics(
        per_agent_latency_seconds={"Visual Difference Inspector": 0.2},
        parallel_stage_latency_seconds=0.3,
        verifier_latency_seconds=0.1,
        total_workflow_latency_seconds=0.4,
        estimated_sequential_specialist_latency_seconds=0.8,
        calculated_parallel_speedup=2.67,
        successful_request_count=4,
        failed_request_count=1 if failed_agents else 0,
    )
    return WorkflowResult([specialist_report], final_report, timing)


def test_default_ui_mode_is_operator_mode() -> None:
    state = {}

    initialize_ui_state(state)

    assert state["ui_mode"] == OPERATOR_MODE
    assert state["agent_statuses"] == DEFAULT_AGENT_STATUSES


def test_switching_modes_does_not_clear_existing_result() -> None:
    state = {"ui_mode": "Expert Mode", "result": fake_result()}

    initialize_ui_state(state)

    assert state["ui_mode"] == "Expert Mode"
    assert state["result"] is not None


def test_next_item_clears_stale_result_and_preserves_reference() -> None:
    reference = fake_image("data:image/png;base64,reference")
    inspection = fake_image("data:image/png;base64,inspection")
    state = {
        "reference_image": reference,
        "inspection_image": inspection,
        "reference_roi_image": fake_image("data:image/png;base64,refroi"),
        "inspection_roi_image": fake_image("data:image/png;base64,insroi"),
        "result": fake_result(),
        "show_mask": True,
        "current_queue_index": 0,
        "inspection_uploader_version": 0,
    }
    initialize_ui_state(state)
    set_completed_state(state, [])

    next_item(state, keep_reference=True)

    assert state["reference_image"] is reference
    assert state["inspection_image"] is None
    assert state["inspection_roi_image"] is None
    assert state["result"] is None
    assert state["inspection_uploader_version"] == 1
    assert state["current_queue_index"] == 1


def test_new_inspection_image_cannot_show_previous_report() -> None:
    state = {
        "reference_image": fake_image("data:image/png;base64,reference"),
        "inspection_image": fake_image("data:image/png;base64,old"),
        "result": fake_result(),
    }
    initialize_ui_state(state)
    set_completed_state(state, [])

    state["inspection_image"] = fake_image("data:image/png;base64,new")

    assert clear_stale_result_if_needed(state) is True
    assert state["result"] is None
    assert result_matches_current_images(state) is False


def test_auto_run_guard_prevents_duplicate_calls() -> None:
    state = {
        "auto_run_enabled": True,
        "reference_image": fake_image("data:image/png;base64,reference"),
        "inspection_image": fake_image("data:image/png;base64,inspection"),
    }
    initialize_ui_state(state)
    pair = image_pair_fingerprint(state["reference_image"], state["inspection_image"])

    assert should_auto_run(state) is True
    assert state["last_auto_run_fingerprint"] == pair
    assert should_auto_run(state) is False


def test_pass_result_renders_concise_status_without_warnings() -> None:
    result = fake_result(InspectionDecision.PASS)

    assert result_status_text(result) == "PASS"
    assert concise_result_summary(result) == "No significant visible nonconformance detected."
    assert priority_warnings(result) == []


def test_manual_review_limits_priority_warnings() -> None:
    result = fake_result(InspectionDecision.MANUAL_REVIEW)

    warnings = priority_warnings(result)

    assert warnings == [
        "Dark material around central IC",
        "USB connector surface discoloration",
        "Inspect under magnification",
    ]
    assert str(warnings) not in warnings


def test_failed_agent_is_visible_in_compact_rows() -> None:
    result = fake_result(failed_agents=["Component and Layout Inspector"])

    rows = agent_rows(result.specialist_reports, {})

    assert ("Component check", "failed", result.specialist_reports[0]) in rows


def test_open_expert_view_button_switches_without_session_state_error() -> None:
    app = AppTest.from_file("app.py")
    app.run(timeout=10)

    open_expert = next(
        button for button in app.button if button.label == "Open Expert View"
    )
    open_expert.click().run(timeout=10)

    assert len(app.exception) == 0
    assert app.sidebar.radio[0].value == "Expert Mode"
