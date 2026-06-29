from __future__ import annotations

from collections.abc import MutableMapping
from pathlib import Path

from core.dataset_queue import (
    DatasetInspectionItem,
    DatasetQueueError,
    discover_pcb4_queue,
)
from core.image_utils import ImageValidationError, load_image_from_path
from ui.state import clear_result_state, image_pair_fingerprint


def get_pcb_image_paths() -> list[Path]:
    return [item.path for item in discover_pcb4_queue().items]


def initialize_pcb4_queue(state: MutableMapping, max_upload_bytes: int) -> None:
    queue = discover_pcb4_queue()
    state["pcb4_queue_items"] = list(queue.items)
    state["pcb4_queue_index"] = 0
    state["pcb4_reference_path"] = queue.reference_path
    state["pcb4_queue_initialized"] = True
    state["pcb4_first_manual_run_completed"] = False
    state["pcb4_pending_autorun"] = False
    state["pcb4_autorun_in_progress"] = False
    state["pcb4_last_autorun_fingerprint"] = None
    state["pcb4_queue_complete"] = len(queue.items) == 0
    state["pcb4_queue_error"] = None
    state["reference_image"] = load_image_from_path(
        queue.reference_path,
        "Reference",
        max_upload_bytes,
    )
    state["reference_roi_image"] = None
    if state["pcb4_queue_complete"]:
        state["pcb4_status_message"] = "PCB4 dataset queue complete."


def reset_operator_inspection_state(state: MutableMapping) -> None:
    clear_result_state(state)
    state["inspection_roi_image"] = None
    state["mask_image"] = None
    state["show_mask"] = False
    state["operator_needs_inspection"] = True
    state["operator_inspection_in_progress"] = False
    state["operator_inspected_image_id"] = None
    state["pcb4_pending_autorun"] = False
    state["pcb4_autorun_in_progress"] = False


def load_operator_image(
    state: MutableMapping,
    index: int,
    max_upload_bytes: int,
) -> None:
    if not state.get("pcb4_queue_initialized"):
        initialize_pcb4_queue(state, max_upload_bytes)

    items = state.get("pcb4_queue_items") or []
    if not items:
        state["pcb4_queue_complete"] = True
        state["pcb4_status_message"] = "PCB4 dataset queue complete."
        return

    bounded_index = max(0, min(index, len(items) - 1))
    item = items[bounded_index]
    reference_path = state.get("pcb4_reference_path")
    if reference_path is not None:
        state["reference_image"] = load_image_from_path(
            reference_path,
            "Reference",
            max_upload_bytes,
        )
    state["inspection_image"] = load_image_from_path(
        item.path,
        "Inspection",
        max_upload_bytes,
    )
    state["reference_roi_image"] = None
    state["inspection_roi_image"] = None
    state["use_sample"] = False
    state["item_identifier"] = item.item_id
    state["pcb4_current_item"] = item
    state["pcb4_queue_index"] = bounded_index
    state["operator_current_image_index"] = bounded_index
    state["operator_current_image_path"] = str(item.path)
    state["pcb4_queue_complete"] = False
    state["pcb4_queue_error"] = None
    state["pcb4_status_message"] = f"Loaded {item.item_id}."
    reset_operator_inspection_state(state)


def initialize_operator_pcb4_workflow(
    state: MutableMapping,
    max_upload_bytes: int,
) -> None:
    if state.get("operator_mode_initialized"):
        return
    try:
        initialize_pcb4_queue(state, max_upload_bytes)
        state["operator_mode_initialized"] = True
        if state.get("pcb4_queue_items"):
            load_operator_image(state, 0, max_upload_bytes)
        else:
            state["pcb4_queue_complete"] = True
            state["pcb4_status_message"] = "PCB4 dataset queue complete."
    except (DatasetQueueError, ImageValidationError) as exc:
        state["operator_mode_initialized"] = True
        state["pcb4_queue_error"] = str(exc)
        state["operator_needs_inspection"] = False
        state["operator_inspection_in_progress"] = False


def navigate_operator_pcb4(
    state: MutableMapping,
    direction: int,
    max_upload_bytes: int,
) -> None:
    try:
        if not state.get("operator_mode_initialized"):
            initialize_operator_pcb4_workflow(state, max_upload_bytes)
        items = state.get("pcb4_queue_items") or []
        if not items:
            state["pcb4_queue_complete"] = True
            return
        current_index = int(state.get("operator_current_image_index", 0))
        load_operator_image(state, current_index + direction, max_upload_bytes)
    except (DatasetQueueError, ImageValidationError) as exc:
        state["pcb4_queue_error"] = str(exc)
        state["operator_needs_inspection"] = False
        state["operator_inspection_in_progress"] = False


def operator_navigation_bounds(state: MutableMapping) -> tuple[bool, bool]:
    items = state.get("pcb4_queue_items") or []
    if not items:
        return True, True
    index = int(state.get("operator_current_image_index", 0))
    running = bool(
        state.get("inspection_running")
        or state.get("operator_inspection_in_progress")
        or state.get("operator_needs_inspection")
    )
    return running or index <= 0, running or index >= len(items) - 1


def current_operator_image_id(state: MutableMapping) -> str | None:
    path = state.get("operator_current_image_path")
    pair_fingerprint = image_pair_fingerprint(
        state.get("reference_image"),
        state.get("inspection_image"),
    )
    if path is None or pair_fingerprint is None:
        return None
    return f"{path}:{pair_fingerprint}"


def claim_operator_inspection(state: MutableMapping) -> str | None:
    if not state.get("operator_needs_inspection"):
        return None
    if state.get("inspection_running") or state.get("operator_inspection_in_progress"):
        return None
    image_id = current_operator_image_id(state)
    if image_id is None:
        return None
    if state.get("operator_inspected_image_id") == image_id:
        state["operator_needs_inspection"] = False
        return None
    state["operator_inspection_in_progress"] = True
    return image_id


def finish_operator_inspection(
    state: MutableMapping,
    image_id: str | None,
    *,
    completed: bool,
) -> None:
    state["operator_needs_inspection"] = False
    state["operator_inspection_in_progress"] = False
    if image_id is not None:
        state["operator_inspected_image_id"] = image_id
    if completed:
        state["pcb4_status_message"] = "Inspection complete for the selected PCB image."


def current_pcb4_item(state: MutableMapping) -> DatasetInspectionItem | None:
    item = state.get("pcb4_current_item")
    return item if isinstance(item, DatasetInspectionItem) else None


def pcb4_position_text(state: MutableMapping) -> str | None:
    item = current_pcb4_item(state)
    if item is None:
        return None
    total = len(state.get("pcb4_queue_items") or [])
    index = int(state.get("operator_current_image_index", state.get("pcb4_queue_index", 0)))
    return f"PCB4 Dataset | Item {index + 1} of {total} | Category: {item.category}"


def cancel_pcb4_pending_autorun(state: MutableMapping) -> None:
    state["pcb4_pending_autorun"] = False
    state["pcb4_autorun_in_progress"] = False


def load_next_pcb4_image(state: MutableMapping, max_upload_bytes: int) -> None:
    try:
        if not state.get("pcb4_queue_initialized"):
            initialize_pcb4_queue(state, max_upload_bytes)
        if state.get("pcb4_queue_complete"):
            state["pcb4_status_message"] = "PCB4 dataset queue complete."
            return

        items = state.get("pcb4_queue_items") or []
        index = int(state.get("pcb4_queue_index", 0))
        if index >= len(items):
            state["pcb4_queue_complete"] = True
            state["pcb4_status_message"] = "PCB4 dataset queue complete."
            return

        item = items[index]
        reference_path = state.get("pcb4_reference_path")
        if reference_path is not None:
            state["reference_image"] = load_image_from_path(
                reference_path,
                "Reference",
                max_upload_bytes,
            )
        state["inspection_image"] = load_image_from_path(
            item.path,
            "Inspection",
            max_upload_bytes,
        )
        state["inspection_roi_image"] = None
        state["reference_roi_image"] = None
        state["mask_image"] = None
        state["show_mask"] = False
        state["use_sample"] = False
        state["item_identifier"] = item.item_id
        state["pcb4_current_item"] = item
        state["pcb4_queue_index"] = index + 1
        state["operator_current_image_index"] = index
        state["operator_current_image_path"] = str(item.path)
        state["pcb4_queue_error"] = None
        clear_result_state(state)

        if state.get("pcb4_first_manual_run_completed"):
            state["pcb4_pending_autorun"] = True
            state["pcb4_status_message"] = "Loading and inspecting the next PCB4 item..."
        else:
            state["pcb4_pending_autorun"] = False
            state["pcb4_status_message"] = "PCB4 item loaded."
    except (DatasetQueueError, ImageValidationError) as exc:
        state["pcb4_queue_error"] = str(exc)
        state["pcb4_pending_autorun"] = False
        state["pcb4_autorun_in_progress"] = False


def pcb4_button_disabled(state: MutableMapping) -> bool:
    return bool(state.get("inspection_running") or state.get("pcb4_queue_complete"))


def pcb4_button_label(state: MutableMapping) -> str:
    if state.get("inspection_running") and state.get("pcb4_pending_autorun"):
        return "Loading and inspecting..."
    if state.get("pcb4_queue_complete"):
        return "PCB4 Queue Complete"
    return "Load Next PCB Image"
