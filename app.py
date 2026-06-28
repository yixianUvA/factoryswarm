from __future__ import annotations

import asyncio
from pathlib import Path

import streamlit as st

from core.config import ConfigError, PROJECT_ROOT, load_config
from core.image_utils import (
    ImageValidationError,
    create_mask_overlay,
    load_image_from_path,
    validate_uploaded_image,
)
from core.orchestrator import WorkflowResult, run_inspection_workflow
from core.schemas import InspectionDecision, ReportStatus


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
    return decision.value.replace("_", " ").upper()


def render_status_cards(statuses: dict[str, str]) -> None:
    cols = st.columns(4)
    for index, agent_name in enumerate(AGENT_ORDER):
        status = statuses.get(agent_name, "waiting")
        with cols[index]:
            st.markdown(
                f"""
                <div class="agent-card status-{status}">
                    <div class="agent-name">{agent_name}</div>
                    <div class="agent-status">{status.upper()}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_final_report(result: WorkflowResult) -> None:
    report = result.final_report
    decision = decision_label(report.decision)
    st.subheader("Final Consensus")
    st.markdown(
        f"""
        <div class="decision decision-{report.decision.value}">
            <span>{decision}</span>
            <small>Confidence {report.overall_confidence:.0%}</small>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write(report.decision_rationale)

    if report.failed_agents:
        st.warning(
            "Confidence reduced because these agents failed: "
            + ", ".join(report.failed_agents)
        )

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Confirmed Observations**")
        st.write(report.confirmed_observations or ["No confirmed observations reported."])
        st.markdown("**Hypotheses**")
        st.write(report.hypotheses or ["No hypotheses reported."])
        st.markdown("**Contradictions**")
        st.write(report.contradictions or ["No contradictions reported."])
    with col_b:
        st.markdown("**Immediate Actions**")
        st.write(report.immediate_actions or ["No immediate actions reported."])
        st.markdown("**Follow-Up Actions**")
        st.write(report.follow_up_actions or ["No follow-up actions reported."])
        st.markdown("**Human Review**")
        st.write("Required" if report.human_review_required else "Not required by report")


def render_performance(result: WorkflowResult) -> None:
    timing = result.timing
    st.subheader("Performance")
    cols = st.columns(4)
    cols[0].metric("Parallel Stage", f"{timing.parallel_stage_latency_seconds:.2f}s")
    cols[1].metric("Verifier", f"{timing.verifier_latency_seconds:.2f}s")
    cols[2].metric("Total", f"{timing.total_workflow_latency_seconds:.2f}s")
    cols[3].metric("Estimated Speedup", f"{timing.calculated_parallel_speedup:.2f}x")

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
                st.write(report.findings or "No findings returned.")
                if report.limitations:
                    st.write("Limitations:", report.limitations)


def main() -> None:
    st.set_page_config(page_title="FactorySwarm", layout="wide")
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.5rem; }
        .notice { border-left: 4px solid #b45309; padding: .6rem .8rem; background: #fff7ed; color: #7c2d12; }
        .agent-card { border: 1px solid #d4d4d8; border-radius: 8px; padding: .8rem; min-height: 92px; background: #fafafa; }
        .agent-name { font-weight: 650; line-height: 1.2; min-height: 42px; }
        .agent-status { margin-top: .4rem; font-size: .78rem; font-weight: 700; letter-spacing: 0; }
        .status-waiting { border-color: #d4d4d8; }
        .status-running { border-color: #2563eb; background: #eff6ff; }
        .status-completed { border-color: #16a34a; background: #f0fdf4; }
        .status-failed { border-color: #dc2626; background: #fef2f2; }
        .decision { border-radius: 8px; padding: .9rem 1rem; margin: .5rem 0 1rem; display: flex; align-items: center; justify-content: space-between; }
        .decision span { font-size: 1.6rem; font-weight: 800; letter-spacing: 0; }
        .decision small { font-size: 1rem; }
        .decision-pass { background: #dcfce7; color: #14532d; }
        .decision-manual_review { background: #fef3c7; color: #78350f; }
        .decision-rework { background: #ffedd5; color: #7c2d12; }
        .decision-reject { background: #fee2e2; color: #7f1d1d; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("FactorySwarm")
    st.caption(
        "Multimodal specialist agents for fast manufacturing inspection on Cerebras."
    )
    st.markdown(
        '<div class="notice">Decision support only - human verification required. '
        "Visual inspection cannot establish electrical functionality.</div>",
        unsafe_allow_html=True,
    )

    try:
        display_config = load_config(require_api_key=False)
    except ConfigError as exc:
        st.error(str(exc))
        return

    for key, default in {
        "result": None,
        "reference_image": None,
        "inspection_image": None,
        "mask_image": None,
        "use_sample": False,
        "show_mask": False,
    }.items():
        st.session_state.setdefault(key, default)

    st.subheader("Inputs")
    sample_col, _ = st.columns([1, 3])
    with sample_col:
        if st.button("Load Sample Case", use_container_width=True):
            st.session_state.use_sample = True
            st.session_state.show_mask = False

    col_ref, col_ins = st.columns(2)
    with col_ref:
        reference_upload = st.file_uploader(
            "Golden-reference image",
            type=["jpg", "jpeg", "png"],
            key="reference_upload",
        )
    with col_ins:
        inspection_upload = st.file_uploader(
            "Inspection image",
            type=["jpg", "jpeg", "png"],
            key="inspection_upload",
        )

    context_col_a, context_col_b, context_col_c = st.columns(3)
    asset_type = context_col_a.text_input("Asset type")
    inspection_stage = context_col_b.text_input("Inspection stage")
    reported_symptom = context_col_c.text_input("Reported symptom")

    mask_upload = st.file_uploader(
        "Dataset annotation mask",
        type=["jpg", "jpeg", "png"],
        key="mask_upload",
    )

    try:
        if reference_upload is not None:
            st.session_state.reference_image = validate_uploaded_image(
                reference_upload,
                "Reference",
                display_config.max_upload_bytes,
            )
            st.session_state.use_sample = False
        elif st.session_state.use_sample:
            st.session_state.reference_image = load_image_from_path(
                SAMPLE_REFERENCE,
                "Reference",
                display_config.max_upload_bytes,
            )

        if inspection_upload is not None:
            st.session_state.inspection_image = validate_uploaded_image(
                inspection_upload,
                "Inspection",
                display_config.max_upload_bytes,
            )
            st.session_state.use_sample = False
        elif st.session_state.use_sample:
            st.session_state.inspection_image = load_image_from_path(
                SAMPLE_INSPECTION,
                "Inspection",
                display_config.max_upload_bytes,
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

    if st.session_state.reference_image and st.session_state.inspection_image:
        st.subheader("Images")
        img_col_a, img_col_b = st.columns(2)
        img_col_a.image(
            st.session_state.reference_image.image,
            caption="Image 1: Golden Reference",
            use_container_width=True,
        )
        img_col_b.image(
            st.session_state.inspection_image.image,
            caption="Image 2: Inspected Product",
            use_container_width=True,
        )

        if SAMPLE_OVERLAY.exists() and st.session_state.use_sample:
            with st.expander("Classical difference overlay", expanded=False):
                st.image(str(SAMPLE_OVERLAY), caption="Alignment and lighting can create artifacts.")

    st.subheader("Agent Execution")
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

    can_run = bool(st.session_state.reference_image and st.session_state.inspection_image)
    if st.button("Run Inspection", disabled=not can_run, type="primary"):
        try:
            load_config(require_api_key=True)
            running_statuses = {agent: "running" for agent in AGENT_ORDER}
            with status_placeholder.container():
                render_status_cards(running_statuses)
            with st.spinner("Specialists running concurrently, then verifier arbitrating..."):
                st.session_state.result = run_async(
                    run_inspection_workflow(
                        st.session_state.reference_image,
                        st.session_state.inspection_image,
                        asset_type or None,
                        inspection_stage or None,
                        reported_symptom or None,
                    )
                )
        except (ConfigError, ImageValidationError) as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Inspection could not complete safely: {exc.__class__.__name__}")

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
        render_final_report(result)
        render_specialist_reports(result)
        render_performance(result)

    if st.session_state.mask_image is not None and st.session_state.inspection_image is not None:
        st.subheader("Annotation")
        st.caption("Dataset annotation metadata is not model input.")
        if st.button("Reveal Dataset Annotation"):
            st.session_state.show_mask = True
        if st.session_state.show_mask:
            try:
                overlay = create_mask_overlay(
                    st.session_state.inspection_image.image,
                    st.session_state.mask_image.image,
                )
                st.image(overlay, caption="Annotation overlay on inspected product")
            except ImageValidationError as exc:
                st.warning(str(exc))


if __name__ == "__main__":
    main()
