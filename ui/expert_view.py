from __future__ import annotations

import asyncio
from typing import Any

import streamlit as st

from core.config import ConfigError, PROJECT_ROOT, load_config
from core.image_utils import (
    ImageValidationError,
    build_inspection_image_set,
    create_mask_overlay,
    load_image_from_path,
    validate_uploaded_image,
)
from core.orchestrator import WorkflowResult, run_inspection_workflow
from core.sample_cases import load_builtin_pcb_sample
from core.schemas import InspectionDecision, ReportStatus
from ui.components import workflow_result_json
from ui.dataset_queue import (
    cancel_pcb4_pending_autorun,
    current_pcb4_item,
    load_next_pcb4_image,
    pcb4_button_disabled,
    pcb4_button_label,
    pcb4_position_text,
)
from ui.formatters import decision_label as format_decision_label
from ui.state import (
    current_pcb4_fingerprint,
    finish_pcb4_autorun,
    mark_result_for_current_images,
    set_completed_state,
    set_failed_state,
    set_running_state,
    should_run_pcb4_autorun,
)
from ui.theme import (
    inject_global_theme,
    render_agent_card,
    render_brand_header,
    render_console,
    render_decision_card,
    render_panel_header,
    render_performance_bar,
)


SAMPLE_REFERENCE = PROJECT_ROOT / "sample_cases" / "reference.jpg"
SAMPLE_INSPECTION = PROJECT_ROOT / "sample_cases" / "inspection.jpg"
SAMPLE_OVERLAY = PROJECT_ROOT / "sample_cases" / "generated" / "difference_overlay.jpg"
AGENT_ORDER = [
    "Visual Difference Inspector",
    "Component and Layout Inspector",
    "Quality and Risk Assessor",
    "Factory Action Planner",
]


def run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def decision_label(decision: InspectionDecision) -> str:
    return format_decision_label(decision)


def display_items(items: list[Any] | tuple[Any, ...] | None) -> list[str]:
    if not items:
        return ["None reported."]
    rendered: list[str] = []
    for item in items:
        if hasattr(item, "finding") and hasattr(item, "evidence"):
            region = getattr(item, "region", None)
            region_text = f" ({region})" if region else ""
            rendered.append(f"{item.finding}{region_text}: {item.evidence}")
        else:
            rendered.append(str(item))
    return rendered


def render_bullet_list(title: str, items: list[Any] | tuple[Any, ...] | None) -> None:
    st.markdown(f"**{title}**")
    for item in display_items(items):
        st.markdown(f"- {item}")


def render_status_cards(statuses: dict[str, str]) -> None:
    cols = st.columns(4)
    for index, agent_name in enumerate(AGENT_ORDER):
        status = statuses.get(agent_name, "waiting")
        with cols[index]:
            render_agent_card(index + 1, agent_name, status)


def render_final_report(result: WorkflowResult) -> None:
    report = result.final_report
    render_panel_header("FINAL CONSENSUS", report.incident_title)
    render_decision_card(
        report.decision,
        report.decision_rationale,
        report.overall_confidence,
        report.human_review_required,
        report.immediate_actions[0] if report.immediate_actions else "Review final report.",
    )

    if report.failed_agents:
        st.warning(
            "Confidence reduced because these agents failed: "
            + ", ".join(report.failed_agents)
        )

    col_a, col_b = st.columns(2)
    with col_a:
        render_bullet_list("Confirmed Observations", report.confirmed_observations)
        render_bullet_list("Hypotheses", report.hypotheses)
        render_bullet_list("Contradictions", report.contradictions)
        render_bullet_list("Unsupported Claims Removed", report.unsupported_claims_removed)
    with col_b:
        render_bullet_list("Immediate Actions", report.immediate_actions)
        render_bullet_list("Follow-Up Actions", report.follow_up_actions)
        render_bullet_list("Missing Evidence", report.additional_evidence_required)
        render_bullet_list("Confidence-Cap Explanations", report.policy_notes)
        st.markdown("**Human Review**")
        st.write("Required" if report.human_review_required else "Not required by report")


def render_performance(result: WorkflowResult) -> None:
    timing = result.timing
    render_panel_header("SYSTEM PERFORMANCE", "Measured workflow timing")
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
        f"Estimated sequential specialist latency: "
        f"{timing.estimated_sequential_specialist_latency_seconds:.2f}s"
    )


def render_specialist_reports(result: WorkflowResult) -> None:
    st.subheader("Specialist Reports")
    for report in result.specialist_reports:
        with st.expander(report.agent_name, expanded=False):
            if report.status == ReportStatus.FAILED:
                st.error(report.error_message or "Agent failed.")
            else:
                st.write(report.summary)
                st.write(f"Decision: {decision_label(report.decision)}")
                st.write(f"Confidence: {report.overall_confidence:.0%}")
                render_bullet_list("Findings", report.findings)
                if report.limitations:
                    render_bullet_list("Limitations", report.limitations)


def render_expert_view() -> None:
    inject_global_theme()
    try:
        display_config = load_config(require_api_key=False)
    except ConfigError as exc:
        st.error(str(exc))
        return

    for key, default in {
        "result": None,
        "reference_image": None,
        "inspection_image": None,
        "reference_roi_image": None,
        "inspection_roi_image": None,
        "mask_image": None,
        "use_sample": False,
        "show_mask": False,
    }.items():
        st.session_state.setdefault(key, default)

    st.sidebar.markdown("### INSPECTION TARGET")
    if st.sidebar.button("Load Sample Case", width="stretch"):
        st.session_state.use_sample = True
        st.session_state.show_mask = False
        st.session_state.pcb4_current_item = None
        cancel_pcb4_pending_autorun(st.session_state)

    if st.sidebar.button(
        pcb4_button_label(st.session_state),
        disabled=pcb4_button_disabled(st.session_state),
        width="stretch",
    ):
        load_next_pcb4_image(st.session_state, display_config.max_upload_bytes)

    st.sidebar.markdown("### REFERENCE CONFIGURATION")
    reference_upload = st.sidebar.file_uploader(
        "Golden-reference image",
        type=["jpg", "jpeg", "png"],
        key="reference_upload",
    )
    inspection_upload = st.sidebar.file_uploader(
        "Inspection image",
        type=["jpg", "jpeg", "png"],
        key="inspection_upload",
    )

    st.sidebar.markdown("### FACTORY CONTEXT")
    asset_type = st.sidebar.text_input("Asset type")
    inspection_stage = st.sidebar.text_input("Inspection stage")
    reported_symptom = st.sidebar.text_input("Reported symptom")

    st.sidebar.markdown("### OPTIONAL EVIDENCE")
    with st.sidebar.expander("Corresponding ROI crops", expanded=False):
        st.caption(
            "Provide both crops together. They must show corresponding local regions; masks remain separate evaluation metadata."
        )
        reference_roi_upload = st.file_uploader(
            "Golden-reference ROI crop",
            type=["jpg", "jpeg", "png"],
            key="reference_roi_upload",
        )
        inspection_roi_upload = st.file_uploader(
            "Inspection ROI crop",
            type=["jpg", "jpeg", "png"],
            key="inspection_roi_upload",
        )

    mask_upload = st.sidebar.file_uploader(
        "Dataset annotation mask",
        type=["jpg", "jpeg", "png"],
        key="mask_upload",
    )

    try:
        sample_loaded = False
        if reference_upload is not None:
            st.session_state.reference_image = validate_uploaded_image(
                reference_upload,
                "Reference",
                display_config.max_upload_bytes,
            )
            st.session_state.use_sample = False
            st.session_state.reference_roi_image = None
            st.session_state.inspection_roi_image = None
            st.session_state.pcb4_current_item = None
            cancel_pcb4_pending_autorun(st.session_state)
        elif st.session_state.use_sample:
            sample = load_builtin_pcb_sample(display_config.max_upload_bytes)
            st.session_state.reference_image = sample.image_set.reference
            st.session_state.inspection_image = sample.image_set.inspection
            st.session_state.reference_roi_image = sample.image_set.reference_roi
            st.session_state.inspection_roi_image = sample.image_set.inspection_roi
            sample_loaded = True

        if inspection_upload is not None:
            st.session_state.inspection_image = validate_uploaded_image(
                inspection_upload,
                "Inspection",
                display_config.max_upload_bytes,
            )
            st.session_state.use_sample = False
            st.session_state.reference_roi_image = None
            st.session_state.inspection_roi_image = None
            st.session_state.pcb4_current_item = None
            cancel_pcb4_pending_autorun(st.session_state)
        elif st.session_state.use_sample and not sample_loaded:
            st.session_state.inspection_image = load_image_from_path(
                SAMPLE_INSPECTION,
                "Inspection",
                display_config.max_upload_bytes,
            )

        if reference_roi_upload is not None:
            st.session_state.reference_roi_image = validate_uploaded_image(
                reference_roi_upload,
                "Reference ROI",
                display_config.max_upload_bytes,
            )
            st.session_state.use_sample = False
        elif not st.session_state.use_sample:
            st.session_state.reference_roi_image = None

        if inspection_roi_upload is not None:
            st.session_state.inspection_roi_image = validate_uploaded_image(
                inspection_roi_upload,
                "Inspection ROI",
                display_config.max_upload_bytes,
            )
            st.session_state.use_sample = False
        elif not st.session_state.use_sample:
            st.session_state.inspection_roi_image = None

        if reference_roi_upload is not None or inspection_roi_upload is not None:
            st.session_state.use_sample = False

        if st.session_state.reference_image and st.session_state.inspection_image:
            build_inspection_image_set(
                st.session_state.reference_image,
                st.session_state.inspection_image,
                st.session_state.reference_roi_image,
                st.session_state.inspection_roi_image,
            )

        if mask_upload is not None:
            st.session_state.mask_image = validate_uploaded_image(
                mask_upload,
                "Annotation mask",
                display_config.max_upload_bytes,
            )
            st.session_state.show_mask = False
    except ImageValidationError as exc:
        st.error(str(exc))

    render_brand_header(
        "Expert Mode",
        model=display_config.model,
        item_id=st.session_state.get("item_identifier") or None,
        system_status="System Ready",
    )
    st.caption(
        "Decision support only - human verification required. Visual inspection cannot establish electrical functionality."
    )
    if st.session_state.get("pcb4_queue_error"):
        st.warning(st.session_state.pcb4_queue_error)
    else:
        queue_position = pcb4_position_text(st.session_state)
        if queue_position:
            st.caption(queue_position)
        if st.session_state.get("pcb4_status_message"):
            st.caption(st.session_state.pcb4_status_message)

    result = st.session_state.result
    if result is None:
        render_performance_bar(None, None, None, None, None, None)
    else:
        timing = result.timing
        render_performance_bar(
            timing.parallel_stage_latency_seconds,
            timing.verifier_latency_seconds,
            timing.total_workflow_latency_seconds,
            timing.estimated_sequential_specialist_latency_seconds,
            timing.calculated_parallel_speedup,
            timing.successful_request_count,
        )

    evidence_col, activity_col = st.columns([2, 1], gap="small")
    with evidence_col:
        render_panel_header("EVIDENCE WORKSPACE", "Reference, inspection, ROI, annotation")
        tabs = st.tabs(["Inspection", "Reference", "Side-by-side", "ROI", "Annotation"])
        with tabs[0]:
            if st.session_state.inspection_image:
                st.image(
                    st.session_state.inspection_image.image,
                    caption="Image 2: Inspected Product",
                    width="stretch",
                )
            else:
                st.info("Load an inspection image to begin.")
        with tabs[1]:
            if st.session_state.reference_image:
                st.image(
                    st.session_state.reference_image.image,
                    caption="Image 1: Golden Reference",
                    width="stretch",
                )
            else:
                st.info("No golden reference loaded.")
        with tabs[2]:
            if st.session_state.reference_image and st.session_state.inspection_image:
                img_col_a, img_col_b = st.columns(2)
                img_col_a.image(
                    st.session_state.reference_image.image,
                    caption="Image 1: Golden Reference",
                    width="stretch",
                )
                img_col_b.image(
                    st.session_state.inspection_image.image,
                    caption="Image 2: Inspected Product",
                    width="stretch",
                )
                if SAMPLE_OVERLAY.exists() and st.session_state.use_sample:
                    st.caption(
                        "Classical difference overlay: alignment and lighting can create artifacts."
                    )
                    st.image(str(SAMPLE_OVERLAY), caption="Visual aid only", width="stretch")
            else:
                st.info("Load both full images for side-by-side comparison.")
        with tabs[3]:
            if st.session_state.reference_roi_image and st.session_state.inspection_roi_image:
                st.caption(
                    "These crops show corresponding local regions. They provide local evidence while the full images provide global layout context."
                )
                roi_col_a, roi_col_b = st.columns(2)
                roi_col_a.image(
                    st.session_state.reference_roi_image.image,
                    caption="Image 3: Golden Reference ROI",
                    width="stretch",
                )
                roi_col_b.image(
                    st.session_state.inspection_roi_image.image,
                    caption="Image 4: Inspection ROI",
                    width="stretch",
                )
            else:
                st.info("Optional ROI crops are not loaded.")
        with tabs[4]:
            if st.session_state.mask_image is not None and st.session_state.inspection_image is not None:
                st.caption("Dataset annotation metadata is not model input.")
                if st.button("Reveal Dataset Annotation", key="expert_reveal_mask"):
                    st.session_state.show_mask = True
                if st.session_state.show_mask:
                    try:
                        overlay = create_mask_overlay(
                            st.session_state.inspection_image.image,
                            st.session_state.mask_image.image,
                        )
                        st.image(
                            overlay,
                            caption="Annotation overlay on inspected product",
                            width="stretch",
                        )
                    except ImageValidationError as exc:
                        st.warning(str(exc))
            else:
                st.info("No annotation mask loaded.")

    with activity_col:
        render_panel_header("INSPECTION ACTIVITY", "Execution console")
        if result is None:
            render_console(
                [
                    ("Pipeline Waiting", "Load evidence and run inspection."),
                    ("Verifier Waiting", "No final decision has been requested."),
                ]
            )
        else:
            entries = [
                (
                    f"{report.agent_name} {'Failed' if report.status == ReportStatus.FAILED else 'Complete'}",
                    report.error_message or report.summary,
                )
                for report in result.specialist_reports
            ]
            entries.append(("Verifier Complete", result.final_report.decision_rationale))
            render_console(entries)

    st.sidebar.markdown("### EXECUTION")
    can_run = bool(st.session_state.reference_image and st.session_state.inspection_image)
    run_clicked = st.sidebar.button(
        "Run Inspection",
        disabled=not can_run,
        type="primary",
        width="stretch",
    )
    if st.session_state.result is not None:
        st.sidebar.download_button(
            "Download Report JSON",
            workflow_result_json(st.session_state.result),
            file_name="factoryswarm_report.json",
            mime="application/json",
            width="stretch",
        )

    st.subheader("Agent Orchestration")
    status_placeholder = st.empty()
    with status_placeholder.container():
        if st.session_state.result is None:
            render_status_cards({agent: "waiting" for agent in AGENT_ORDER})
        else:
            render_status_cards(
                {
                    report.agent_name: (
                        "failed" if report.status == ReportStatus.FAILED else "completed"
                    )
                    for report in st.session_state.result.specialist_reports
                }
            )

    pcb4_autorun_fingerprint = None
    pcb4_autorun_requested = should_run_pcb4_autorun(st.session_state)
    if pcb4_autorun_requested:
        pcb4_autorun_fingerprint = current_pcb4_fingerprint(st.session_state)

    should_run_now = run_clicked or pcb4_autorun_requested
    if should_run_now:
        try:
            load_config(require_api_key=True)
            set_running_state(st.session_state)
            running_statuses = {agent: "running" for agent in AGENT_ORDER}
            with status_placeholder.container():
                render_status_cards(running_statuses)
            with st.spinner("Specialists running concurrently, then verifier arbitrating..."):
                st.session_state.result = run_async(
                    run_inspection_workflow(
                        reference_image=st.session_state.reference_image,
                        inspection_image=st.session_state.inspection_image,
                        reference_roi_image=st.session_state.reference_roi_image,
                        inspection_roi_image=st.session_state.inspection_roi_image,
                        asset_type=asset_type or None,
                        inspection_stage=inspection_stage or None,
                        reported_symptom=reported_symptom or None,
                    )
                )
            set_completed_state(
                st.session_state,
                st.session_state.result.final_report.failed_agents,
            )
            mark_result_for_current_images(st.session_state)
        except (ConfigError, ImageValidationError) as exc:
            set_failed_state(st.session_state)
            st.error(str(exc))
        except Exception as exc:
            set_failed_state(st.session_state)
            st.error(f"Inspection could not complete safely: {exc.__class__.__name__}")
        finally:
            if pcb4_autorun_requested:
                finish_pcb4_autorun(st.session_state, pcb4_autorun_fingerprint)
        st.rerun()

    result = st.session_state.result
    if result is not None:
        with status_placeholder.container():
            render_status_cards(
                {
                    report.agent_name: (
                        "failed" if report.status == ReportStatus.FAILED else "completed"
                    )
                    for report in result.specialist_reports
                }
            )
        st.divider()
        render_final_report(result)
        with st.expander("Specialist Reports", expanded=False):
            render_specialist_reports(result)
        with st.expander("System Performance", expanded=False):
            render_performance(result)


def main() -> None:
    st.set_page_config(page_title="FactorySwarm", layout="wide")
    render_expert_view()


if __name__ == "__main__":
    main()
