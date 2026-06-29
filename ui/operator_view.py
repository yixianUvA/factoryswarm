from __future__ import annotations

import asyncio
import streamlit as st

from core.config import ConfigError, PROJECT_ROOT, load_config
from core.image_utils import (
    ImageValidationError,
    build_inspection_image_set,
    create_mask_overlay,
    validate_uploaded_image,
)
from core.orchestrator import WorkflowResult, run_inspection_workflow
from core.sample_cases import load_builtin_pcb_sample
from ui.components import (
    concise_result_summary,
    most_important_next_action,
    priority_warnings,
    render_agent_status,
    render_collapsible_report,
    render_priority_warnings,
    render_specialist_report_details,
    render_status_card,
    render_system_details,
    result_status_text,
)
from ui.state import (
    EXPERT_MODE,
    clear_result_state,
    clear_stale_result_if_needed,
    initialize_ui_state,
    mark_result_for_current_images,
    next_item,
    result_matches_current_images,
    set_completed_state,
    set_failed_state,
    set_running_state,
    should_auto_run,
)
from ui.formatters import html_escape
from ui.theme import (
    inject_global_theme,
    render_brand_header,
    render_panel_header,
    render_performance_bar,
)


SAMPLE_OVERLAY = PROJECT_ROOT / "sample_cases" / "generated" / "difference_overlay.jpg"


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


def _run_workflow(
    asset_type: str | None,
    inspection_stage: str | None,
    reported_symptom: str | None,
) -> WorkflowResult | None:
    try:
        load_config(require_api_key=True)
        set_running_state(st.session_state)
        with st.spinner("Inspection agents are analyzing this item..."):
            result = run_async(
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
        st.session_state.result = result
        set_completed_state(st.session_state, result.final_report.failed_agents)
        return result
    except (ConfigError, ImageValidationError) as exc:
        set_failed_state(st.session_state)
        st.session_state.operator_error = str(exc)
    except Exception as exc:
        set_failed_state(st.session_state)
        st.session_state.operator_error = f"Inspection failed: {exc.__class__.__name__}"
    return None


def _render_operator_styles() -> None:
    inject_global_theme()


def _load_sidebar_inputs() -> tuple[str, str, str]:
    config = load_config(require_api_key=False)
    state = st.session_state

    st.sidebar.markdown("### Inspection setup")
    state.auto_run_enabled = st.sidebar.checkbox(
        "Automatically inspect after image upload",
        value=state.auto_run_enabled,
        help="Runs once for each new reference and inspection image pair.",
    )

    if st.sidebar.button("Load Sample Case", width="stretch"):
        sample = load_builtin_pcb_sample(config.max_upload_bytes)
        state.reference_image = sample.image_set.reference
        state.inspection_image = sample.image_set.inspection
        state.reference_roi_image = sample.image_set.reference_roi
        state.inspection_roi_image = sample.image_set.inspection_roi
        state.item_identifier = sample.name
        state.use_sample = True
        state.show_mask = False
        clear_result_state(state)

    reference_upload = st.sidebar.file_uploader(
        "Golden reference",
        type=["jpg", "jpeg", "png"],
        key="operator_reference_upload",
    )
    if reference_upload is not None:
        state.reference_image = validate_uploaded_image(
            reference_upload,
            "Reference",
            config.max_upload_bytes,
        )
        state.reference_roi_image = None
        state.inspection_roi_image = None
        state.use_sample = False

    inspection_key = f"operator_inspection_upload_{state.inspection_uploader_version}"
    inspection_upload = st.sidebar.file_uploader(
        "Inspection image",
        type=["jpg", "jpeg", "png"],
        key=inspection_key,
    )
    if inspection_upload is not None:
        state.inspection_image = validate_uploaded_image(
            inspection_upload,
            "Inspection",
            config.max_upload_bytes,
        )
        state.inspection_roi_image = None
        if not state.use_sample:
            state.reference_roi_image = None
        state.use_sample = False

    state.item_identifier = st.sidebar.text_input(
        "Item identifier",
        value=state.item_identifier,
        placeholder="Serial, lot, or station ID",
    )
    asset_type = st.sidebar.text_input("Asset type")
    inspection_stage = st.sidebar.text_input("Inspection stage")
    reported_symptom = st.sidebar.text_input("Reported symptom")

    with st.sidebar.expander("Advanced inputs", expanded=False):
        st.caption("ROI crops are optional but must be supplied as a corresponding pair.")
        reference_roi_upload = st.file_uploader(
            "Golden-reference ROI crop",
            type=["jpg", "jpeg", "png"],
            key="operator_reference_roi_upload",
        )
        inspection_roi_upload = st.file_uploader(
            "Inspection ROI crop",
            type=["jpg", "jpeg", "png"],
            key="operator_inspection_roi_upload",
        )
        if reference_roi_upload is not None:
            state.reference_roi_image = validate_uploaded_image(
                reference_roi_upload,
                "Reference ROI",
                config.max_upload_bytes,
            )
            state.use_sample = False
        if inspection_roi_upload is not None:
            state.inspection_roi_image = validate_uploaded_image(
                inspection_roi_upload,
                "Inspection ROI",
                config.max_upload_bytes,
            )
            state.use_sample = False

        mask_upload = st.file_uploader(
            "Dataset annotation mask",
            type=["jpg", "jpeg", "png"],
            key="operator_mask_upload",
        )
        if mask_upload is not None:
            state.mask_image = validate_uploaded_image(
                mask_upload,
                "Annotation mask",
                config.max_upload_bytes,
            )
            state.show_mask = False

    if state.reference_image and state.inspection_image:
        build_inspection_image_set(
            state.reference_image,
            state.inspection_image,
            state.reference_roi_image,
            state.inspection_roi_image,
        )

    clear_stale_result_if_needed(state)
    return asset_type, inspection_stage, reported_symptom


def _render_reference_expander() -> None:
    state = st.session_state
    with st.expander("Reference and comparison images", expanded=False):
        if not state.reference_image:
            st.info("No golden reference loaded.")
            return
        cols = st.columns(2)
        cols[0].image(
            state.reference_image.image,
            caption="Image 1: Golden Reference",
            width="stretch",
        )
        if state.inspection_image:
            cols[1].image(
                state.inspection_image.image,
                caption="Image 2: Inspected Product",
                width="stretch",
            )

        if state.reference_roi_image and state.inspection_roi_image:
            st.markdown("**ROI comparison**")
            roi_cols = st.columns(2)
            roi_cols[0].image(
                state.reference_roi_image.image,
                caption="Image 3: Golden Reference ROI",
                width="stretch",
            )
            roi_cols[1].image(
                state.inspection_roi_image.image,
                caption="Image 4: Inspection ROI",
                width="stretch",
            )

        if SAMPLE_OVERLAY.exists() and state.use_sample:
            st.markdown("**Classical difference overlay**")
            st.caption("Alignment and lighting can create artifacts.")
            st.image(str(SAMPLE_OVERLAY), width="stretch")

        if state.mask_image is not None and state.inspection_image is not None:
            st.markdown("**Dataset annotation**")
            st.caption("Annotation metadata is not sent to the model.")
            if st.button("Reveal Dataset Annotation", key="operator_reveal_mask"):
                state.show_mask = True
            if state.show_mask:
                try:
                    overlay = create_mask_overlay(
                        state.inspection_image.image,
                        state.mask_image.image,
                    )
                    st.image(overlay, caption="Annotation overlay on inspected product")
                except ImageValidationError as exc:
                    st.warning(str(exc))


def _render_actions(can_run: bool) -> tuple[bool, bool, bool]:
    action_cols = st.columns([1, 1, 1])
    run_clicked = action_cols[0].button(
        "Run Inspection",
        disabled=not can_run,
        type="primary",
        width="stretch",
    )
    next_clicked = action_cols[1].button(
        "Next Item",
        disabled=st.session_state.inspection_running,
        width="stretch",
    )
    review_clicked = action_cols[2].button(
        "Mark for Review",
        disabled=st.session_state.inspection_running,
        width="stretch",
    )
    if st.button("Open Expert View", width="stretch"):
        st.session_state.pending_ui_mode = EXPERT_MODE
        st.rerun()
    return run_clicked, next_clicked, review_clicked


def render_operator_view() -> None:
    initialize_ui_state(st.session_state)
    _render_operator_styles()

    try:
        asset_type, inspection_stage, reported_symptom = _load_sidebar_inputs()
        display_config = load_config(require_api_key=False)
    except (ConfigError, ImageValidationError) as exc:
        st.error(str(exc))
        asset_type = inspection_stage = reported_symptom = ""
        display_config = None

    state = st.session_state
    result = state.result if result_matches_current_images(state) else None
    can_run = bool(state.reference_image and state.inspection_image)
    render_brand_header(
        "Operator Mode",
        model=getattr(display_config, "model", None),
        item_id=state.item_identifier or None,
        system_status="Inspecting" if state.inspection_running else "System Ready",
    )
    st.caption(
        "Decision support only - human verification required. Visual inspection cannot establish electrical functionality."
    )
    if result is not None:
        timing = result.timing
        render_performance_bar(
            timing.parallel_stage_latency_seconds,
            timing.verifier_latency_seconds,
            timing.total_workflow_latency_seconds,
            timing.estimated_sequential_specialist_latency_seconds,
            timing.calculated_parallel_speedup,
            timing.successful_request_count,
        )

    left, right = st.columns([2, 1], gap="small")
    with left:
        render_panel_header("INSPECTION EVIDENCE", "Current inspection item")
        meta = []
        if state.item_identifier:
            meta.append(f"Item: {state.item_identifier}")
        if asset_type:
            meta.append(f"Asset: {asset_type}")
        if state.reference_image:
            meta.append("Reference loaded")
        if state.current_queue_index:
            meta.append(f"Processed items: {state.current_queue_index}")
        if meta:
            st.markdown(
                '<div class="inspection-meta">'
                + "".join(
                    f'<span class="fs-chip">{html_escape(item)}</span>' for item in meta
                )
                + "</div>",
                unsafe_allow_html=True,
            )

        if state.inspection_image:
            st.image(
                state.inspection_image.image,
                caption="Current inspection image",
                width="stretch",
            )
        else:
            st.info("Load an inspection image to begin.")

    with right:
        render_panel_header("DECISION PANEL", "Operator workflow")
        confidence = result.final_report.overall_confidence if result else None
        human_review = result.final_report.human_review_required if result else None
        status_text = result_status_text(result, state.inspection_running)
        if state.inspection_status == "failed":
            status_text = "FAILED"
        render_status_card(
            status_text,
            concise_result_summary(result),
            confidence,
            human_review,
            most_important_next_action(result),
        )
        if result and result.final_report.failed_agents:
            st.warning(
                "Partial success: "
                + ", ".join(result.final_report.failed_agents)
                + " unavailable."
            )
        render_agent_status(
            result.specialist_reports if result else None,
            state.agent_statuses,
        )
        render_priority_warnings(priority_warnings(result))

        run_clicked, next_clicked, review_clicked = _render_actions(can_run)
        if review_clicked:
            st.info("Item marked for manual review in this session.")
        if next_clicked:
            next_item(state, keep_reference=True)
            st.rerun()

    if state.inspection_status == "failed":
        st.error(
            "Inspection unavailable\n\n"
            "The automated check could not be completed. Please retry or send this item for manual review."
        )
        with st.expander("Open technical details", expanded=False):
            st.write(state.get("operator_error", "No additional details available."))

    should_run_now = run_clicked or should_auto_run(state)
    if should_run_now and can_run:
        _run_workflow(asset_type, inspection_stage, reported_symptom)
        mark_result_for_current_images(state)
        st.rerun()

    _render_reference_expander()

    if result is not None:
        render_collapsible_report(result)
        with st.expander("Specialist reports", expanded=False):
            render_specialist_report_details(result.specialist_reports)
        render_system_details(result)

    with st.expander("Help", expanded=False):
        st.write(
            "Keyboard shortcuts are documented for workstation procedures, but this Streamlit MVP uses reliable button controls. "
            "Use Run Inspection, Next Item, Open Expert View, and Mark for Review from the operator panel."
        )
