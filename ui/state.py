from __future__ import annotations

import hashlib
from collections.abc import MutableMapping
from typing import Any

from core.image_utils import ValidatedImage


OPERATOR_MODE = "Operator Mode"
EXPERT_MODE = "Expert Mode"


DEFAULT_AGENT_STATUSES = {
    "Visual Difference Inspector": "waiting",
    "Component and Layout Inspector": "waiting",
    "Quality and Risk Assessor": "waiting",
    "Factory Action Planner": "waiting",
    "Final Verification": "waiting",
}


DEFAULT_STATE: dict[str, Any] = {
    "ui_mode": OPERATOR_MODE,
    "result": None,
    "reference_image": None,
    "inspection_image": None,
    "reference_roi_image": None,
    "inspection_roi_image": None,
    "mask_image": None,
    "use_sample": False,
    "show_mask": False,
    "item_identifier": "",
    "inspection_status": "waiting",
    "agent_statuses": DEFAULT_AGENT_STATUSES.copy(),
    "inspection_running": False,
    "auto_run_enabled": False,
    "current_queue_index": 0,
    "result_reference_fingerprint": None,
    "result_inspection_fingerprint": None,
    "last_auto_run_fingerprint": None,
    "inspection_uploader_version": 0,
}


def initialize_ui_state(state: MutableMapping[str, Any]) -> None:
    for key, default in DEFAULT_STATE.items():
        if key not in state:
            state[key] = default.copy() if isinstance(default, dict) else default


def image_fingerprint(image: ValidatedImage | None) -> str | None:
    if image is None:
        return None
    return hashlib.sha256(image.data_uri.encode("utf-8")).hexdigest()


def image_pair_fingerprint(
    reference: ValidatedImage | None,
    inspection: ValidatedImage | None,
) -> str | None:
    reference_fingerprint = image_fingerprint(reference)
    inspection_fingerprint = image_fingerprint(inspection)
    if reference_fingerprint is None or inspection_fingerprint is None:
        return None
    return f"{reference_fingerprint}:{inspection_fingerprint}"


def mark_result_for_current_images(state: MutableMapping[str, Any]) -> None:
    state["result_reference_fingerprint"] = image_fingerprint(state.get("reference_image"))
    state["result_inspection_fingerprint"] = image_fingerprint(state.get("inspection_image"))


def result_matches_current_images(state: MutableMapping[str, Any]) -> bool:
    if state.get("result") is None:
        return False
    return (
        state.get("result_reference_fingerprint")
        == image_fingerprint(state.get("reference_image"))
        and state.get("result_inspection_fingerprint")
        == image_fingerprint(state.get("inspection_image"))
    )


def clear_stale_result_if_needed(state: MutableMapping[str, Any]) -> bool:
    if state.get("result") is not None and not result_matches_current_images(state):
        clear_result_state(state)
        return True
    return False


def clear_result_state(state: MutableMapping[str, Any]) -> None:
    state["result"] = None
    state["show_mask"] = False
    state["inspection_status"] = "waiting"
    state["agent_statuses"] = DEFAULT_AGENT_STATUSES.copy()
    state["result_reference_fingerprint"] = None
    state["result_inspection_fingerprint"] = None


def set_running_state(state: MutableMapping[str, Any]) -> None:
    state["inspection_running"] = True
    state["inspection_status"] = "inspecting"
    state["agent_statuses"] = {
        agent_name: "running" for agent_name in DEFAULT_AGENT_STATUSES
    }


def set_completed_state(state: MutableMapping[str, Any], failed_agents: list[str]) -> None:
    failed = set(failed_agents)
    statuses = {}
    for agent_name in DEFAULT_AGENT_STATUSES:
        if agent_name == "Final Verification":
            statuses[agent_name] = "completed"
        else:
            statuses[agent_name] = "failed" if agent_name in failed else "completed"
    state["agent_statuses"] = statuses
    state["inspection_status"] = "partial success" if failed else "completed"
    state["inspection_running"] = False
    mark_result_for_current_images(state)


def set_failed_state(state: MutableMapping[str, Any]) -> None:
    state["inspection_status"] = "failed"
    state["inspection_running"] = False
    state["agent_statuses"] = {
        agent_name: "failed" if agent_name == "Final Verification" else "partial success"
        for agent_name in DEFAULT_AGENT_STATUSES
    }


def next_item(state: MutableMapping[str, Any], keep_reference: bool = True) -> None:
    reference_image = state.get("reference_image")
    reference_roi_image = state.get("reference_roi_image")
    clear_result_state(state)
    state["inspection_image"] = None
    state["inspection_roi_image"] = None
    state["mask_image"] = None
    state["use_sample"] = False
    state["item_identifier"] = ""
    state["last_auto_run_fingerprint"] = None
    state["inspection_uploader_version"] = int(state.get("inspection_uploader_version", 0)) + 1
    state["current_queue_index"] = int(state.get("current_queue_index", 0)) + 1
    if keep_reference:
        state["reference_image"] = reference_image
        state["reference_roi_image"] = reference_roi_image
    else:
        state["reference_image"] = None
        state["reference_roi_image"] = None


def should_auto_run(state: MutableMapping[str, Any]) -> bool:
    if not state.get("auto_run_enabled"):
        return False
    if state.get("inspection_running"):
        return False
    pair_fingerprint = image_pair_fingerprint(
        state.get("reference_image"),
        state.get("inspection_image"),
    )
    if pair_fingerprint is None:
        return False
    if state.get("result") is not None and result_matches_current_images(state):
        return False
    if state.get("last_auto_run_fingerprint") == pair_fingerprint:
        return False
    state["last_auto_run_fingerprint"] = pair_fingerprint
    return True
