from __future__ import annotations

import json
from typing import Any

import streamlit as st

from core.orchestrator import WorkflowResult
from core.schemas import InspectionDecision, ReportStatus, SpecialistReport
from ui.formatters import decision_label
from ui.state import DEFAULT_AGENT_STATUSES
from ui.theme import (
    render_decision_card,
    render_performance_bar,
    render_warning_list,
)


AGENT_LABELS = {
    "Visual Difference Inspector": "Visual inspection",
    "Component and Layout Inspector": "Component check",
    "Quality and Risk Assessor": "Quality assessment",
    "Factory Action Planner": "Action planning",
    "Final Verification": "Final verification",
}


def result_status_text(result: WorkflowResult | None, inspection_running: bool = False) -> str:
    if inspection_running:
        return "INSPECTING"
    if result is None:
        return "INSPECTING"
    return decision_label(result.final_report.decision)


def concise_result_summary(result: WorkflowResult | None) -> str:
    if result is None:
        return "Load images and run inspection."
    report = result.final_report
    if report.decision == InspectionDecision.PASS:
        return "No significant visible nonconformance detected."
    if report.confirmed_observations:
        return report.confirmed_observations[0]
    if report.hypotheses:
        return report.hypotheses[0]
    return report.decision_rationale


def most_important_next_action(result: WorkflowResult | None) -> str:
    if result is None:
        return "Run inspection when the current item is ready."
    report = result.final_report
    if report.immediate_actions:
        return report.immediate_actions[0]
    if report.follow_up_actions:
        return report.follow_up_actions[0]
    if report.decision == InspectionDecision.PASS:
        return "Proceed to the next item."
    return "Send this item for manual review."


def priority_warnings(result: WorkflowResult | None, limit: int = 3) -> list[str]:
    if result is None or result.final_report.decision == InspectionDecision.PASS:
        return []
    report = result.final_report
    candidates = [
        *report.confirmed_observations,
        *report.hypotheses,
        *report.immediate_actions,
    ]
    warnings: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        normalized = item.strip()
        if normalized and normalized.lower() not in seen:
            warnings.append(normalized)
            seen.add(normalized.lower())
        if len(warnings) >= limit:
            break
    return warnings


def agent_rows(
    reports: list[SpecialistReport] | None,
    statuses: dict[str, str] | None,
) -> list[tuple[str, str, SpecialistReport | None]]:
    by_name = {report.agent_name: report for report in reports or []}
    rows: list[tuple[str, str, SpecialistReport | None]] = []
    for agent_name, default_status in DEFAULT_AGENT_STATUSES.items():
        report = by_name.get(agent_name)
        status = statuses.get(agent_name, default_status) if statuses else default_status
        if report is not None:
            status = "failed" if report.status == ReportStatus.FAILED else "completed"
        rows.append((AGENT_LABELS.get(agent_name, agent_name), status, report))
    return rows


def workflow_result_json(result: WorkflowResult) -> str:
    payload: dict[str, Any] = {
        "specialist_reports": [
            report.model_dump(mode="json") for report in result.specialist_reports
        ],
        "final_report": result.final_report.model_dump(mode="json"),
        "timing": result.timing.model_dump(mode="json"),
    }
    return json.dumps(payload, indent=2)


def render_status_card(
    status_text: str,
    summary: str,
    confidence: float | None,
    human_review_required: bool | None,
    next_action: str,
) -> None:
    decision_key = status_text.lower().replace(" ", "_")
    render_decision_card(
        decision_key,
        summary,
        confidence,
        human_review_required,
        next_action,
    )


def render_agent_status(
    reports: list[SpecialistReport] | None,
    statuses: dict[str, str] | None,
) -> None:
    st.markdown("**Inspection agents**")
    for label, status, report in agent_rows(reports, statuses):
        symbol = "✓" if status == "completed" else "!" if status == "failed" else "…"
        row_label = f"{symbol} {label} — {status.replace('_', ' ')}"
        with st.expander(row_label, expanded=False):
            if report is None:
                st.write("Waiting for this inspection step.")
                continue
            st.write(f"Full agent: {report.agent_name}")
            st.write(f"Status: {report.status.value}")
            if report.latency_seconds is not None:
                st.write(f"Latency: {report.latency_seconds:.2f}s")
            if report.status == ReportStatus.FAILED:
                st.error(report.error_message or "Agent unavailable.")
                continue
            st.write(report.summary)
            if report.findings:
                st.markdown("**Findings**")
                for finding in report.findings:
                    region = f" ({finding.region})" if finding.region else ""
                    st.markdown(f"- {finding.finding}{region}: {finding.evidence}")
            if report.limitations:
                st.markdown("**Limitations**")
                for limitation in report.limitations:
                    st.markdown(f"- {limitation}")


def render_priority_warnings(warnings: list[str]) -> None:
    if not warnings:
        return
    st.markdown("**Warnings**")
    render_warning_list(warnings)


def render_collapsible_report(result: WorkflowResult) -> None:
    report = result.final_report
    with st.expander("Detailed findings", expanded=False):
        sections = [
            ("Confirmed observations", report.confirmed_observations),
            ("Hypotheses", report.hypotheses),
            ("Contradictions", report.contradictions),
            ("Removed unsupported claims", report.unsupported_claims_removed),
            ("Evidence and missing context", report.additional_evidence_required),
        ]
        for title, items in sections:
            if not items:
                continue
            st.markdown(f"**{title}**")
            for item in items:
                st.markdown(f"- {item}")
        st.markdown("**Decision rationale**")
        st.write(report.decision_rationale)

    with st.expander("Download report", expanded=False):
        st.download_button(
            "Download JSON report",
            workflow_result_json(result),
            file_name="factoryswarm_report.json",
            mime="application/json",
            width="stretch",
        )


def render_specialist_report_details(reports: list[SpecialistReport]) -> None:
    for report in reports:
        st.markdown(f"**{report.agent_name}**")
        st.write(f"Status: {report.status.value}")
        if report.latency_seconds is not None:
            st.write(f"Latency: {report.latency_seconds:.2f}s")
        if report.status == ReportStatus.FAILED:
            st.error(report.error_message or "Agent unavailable.")
        else:
            st.write(report.summary)
            if report.findings:
                st.markdown("Findings")
                for finding in report.findings:
                    region = f" ({finding.region})" if finding.region else ""
                    st.markdown(f"- {finding.finding}{region}: {finding.evidence}")
            if report.limitations:
                st.markdown("Limitations")
                for limitation in report.limitations:
                    st.markdown(f"- {limitation}")
        st.divider()


def render_system_details(result: WorkflowResult) -> None:
    timing = result.timing
    with st.expander("System details", expanded=False):
        render_performance_bar(
            timing.parallel_stage_latency_seconds,
            timing.verifier_latency_seconds,
            timing.total_workflow_latency_seconds,
            timing.estimated_sequential_specialist_latency_seconds,
            timing.calculated_parallel_speedup,
            timing.successful_request_count,
        )
        st.caption("Sequential latency and speedup are estimates from per-agent timings.")
        st.table(
            {
                "Agent": list(timing.per_agent_latency_seconds.keys()),
                "Latency seconds": [
                    f"{latency:.2f}"
                    for latency in timing.per_agent_latency_seconds.values()
                ],
            }
        )
        st.write(
            "Estimated sequential specialist latency: "
            f"{timing.estimated_sequential_specialist_latency_seconds:.2f}s"
        )
