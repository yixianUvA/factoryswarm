from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.dataset_queue import (
    DatasetInspectionItem,
    DatasetInspectionQueue,
    DatasetQueueError,
    discover_pcb4_queue,
    natural_sort_key,
)
from ui import dataset_queue as queue_ui
from ui.state import (
    DEFAULT_AGENT_STATUSES,
    initialize_ui_state,
)


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not decoded in discovery tests")


def fake_image(data_uri: str):
    return SimpleNamespace(data_uri=data_uri)


def test_discover_pcb4_queue_orders_images_and_excludes_reference(tmp_path: Path) -> None:
    root = tmp_path / "Images"
    touch(root / "Normal" / "010.JPG")
    touch(root / "Normal" / "002.JPG")
    touch(root / "Normal" / "readme.txt")
    touch(root / "Normal" / ".hidden.JPG")
    touch(root / "Anomaly" / "011.png")
    touch(root / "Anomaly" / "002.JPG")
    touch(root / "Anomaly" / "001.jpeg")

    queue = discover_pcb4_queue(root)

    assert queue.reference_path == (root / "Normal" / "002.JPG").resolve()
    assert [item.item_id for item in queue.items] == [
        "PCB4 / Anomaly / 001",
        "PCB4 / Anomaly / 002",
        "PCB4 / Anomaly / 011",
        "PCB4 / Normal / 010",
    ]
    assert [item.category for item in queue.items] == [
        "Anomaly",
        "Anomaly",
        "Anomaly",
        "Normal",
    ]


def test_natural_sort_key_handles_numeric_names() -> None:
    paths = [Path("10.JPG"), Path("2.JPG"), Path("001.JPG")]

    assert [path.name for path in sorted(paths, key=natural_sort_key)] == [
        "001.JPG",
        "2.JPG",
        "10.JPG",
    ]


def test_discover_pcb4_queue_missing_and_no_reference(tmp_path: Path) -> None:
    with pytest.raises(DatasetQueueError, match="PCB4 dataset not found"):
        discover_pcb4_queue(tmp_path / "missing")

    root = tmp_path / "Images"
    touch(root / "Anomaly" / "001.JPG")

    with pytest.raises(DatasetQueueError, match="no normal reference image"):
        discover_pcb4_queue(root)


def install_fake_queue(monkeypatch, items: tuple[DatasetInspectionItem, ...]) -> None:
    queue = DatasetInspectionQueue(reference_path=Path("/repo/ref.JPG"), items=items)
    monkeypatch.setattr(queue_ui, "discover_pcb4_queue", lambda: queue)
    monkeypatch.setattr(
        queue_ui,
        "load_image_from_path",
        lambda path, label, max_bytes: fake_image(f"data:{label}:{Path(path).name}"),
    )


def test_operator_initialization_loads_first_image_and_marks_inspection(monkeypatch) -> None:
    item = DatasetInspectionItem(Path("/repo/a001.JPG"), "Anomaly", "PCB4 / Anomaly / 001")
    install_fake_queue(monkeypatch, (item,))
    state = {}
    initialize_ui_state(state)

    queue_ui.initialize_operator_pcb4_workflow(state, 100)

    assert state["reference_image"].data_uri == "data:Reference:ref.JPG"
    assert state["inspection_image"].data_uri == "data:Inspection:a001.JPG"
    assert state["operator_mode_initialized"] is True
    assert state["operator_current_image_index"] == 0
    assert state["operator_needs_inspection"] is True
    assert state["result"] is None


def test_operator_navigation_resets_result_and_moves_by_index(monkeypatch) -> None:
    items = (
        DatasetInspectionItem(Path("/repo/a001.JPG"), "Anomaly", "PCB4 / Anomaly / 001"),
        DatasetInspectionItem(Path("/repo/a002.JPG"), "Anomaly", "PCB4 / Anomaly / 002"),
    )
    install_fake_queue(monkeypatch, items)
    state = {"result": object()}
    initialize_ui_state(state)

    queue_ui.initialize_operator_pcb4_workflow(state, 100)
    state["result"] = object()
    state["agent_statuses"] = {"Visual Difference Inspector": "completed"}

    queue_ui.navigate_operator_pcb4(state, 1, 100)

    assert state["result"] is None
    assert state["agent_statuses"] == DEFAULT_AGENT_STATUSES
    assert state["reference_image"].data_uri == "data:Reference:ref.JPG"
    assert state["inspection_image"].data_uri == "data:Inspection:a002.JPG"
    assert state["operator_current_image_index"] == 1
    assert state["operator_needs_inspection"] is True

    queue_ui.navigate_operator_pcb4(state, -1, 100)

    assert state["inspection_image"].data_uri == "data:Inspection:a001.JPG"
    assert state["operator_current_image_index"] == 0


def test_operator_navigation_boundaries(monkeypatch) -> None:
    items = (
        DatasetInspectionItem(Path("/repo/a001.JPG"), "Anomaly", "PCB4 / Anomaly / 001"),
        DatasetInspectionItem(Path("/repo/a002.JPG"), "Anomaly", "PCB4 / Anomaly / 002"),
    )
    install_fake_queue(monkeypatch, items)
    state = {}
    initialize_ui_state(state)

    queue_ui.initialize_operator_pcb4_workflow(state, 100)

    assert queue_ui.operator_navigation_bounds(state) == (True, True)
    state["operator_needs_inspection"] = False
    assert queue_ui.operator_navigation_bounds(state) == (True, False)

    queue_ui.navigate_operator_pcb4(state, 1, 100)
    state["operator_needs_inspection"] = False

    assert queue_ui.operator_navigation_bounds(state) == (False, True)


def test_operator_empty_queue_reports_completion(monkeypatch) -> None:
    install_fake_queue(monkeypatch, ())
    state = {}
    initialize_ui_state(state)

    queue_ui.initialize_operator_pcb4_workflow(state, 100)

    assert state["pcb4_queue_complete"] is True
    assert state["pcb4_queue_index"] == 0
    assert queue_ui.operator_navigation_bounds(state) == (True, True)


def test_operator_claim_runs_exactly_once_until_index_changes(monkeypatch) -> None:
    items = (
        DatasetInspectionItem(Path("/repo/a001.JPG"), "Anomaly", "PCB4 / Anomaly / 001"),
        DatasetInspectionItem(Path("/repo/a002.JPG"), "Anomaly", "PCB4 / Anomaly / 002"),
    )
    install_fake_queue(monkeypatch, items)
    state = {}
    initialize_ui_state(state)

    queue_ui.initialize_operator_pcb4_workflow(state, 100)

    first_claim = queue_ui.claim_operator_inspection(state)

    assert first_claim is not None
    assert queue_ui.claim_operator_inspection(state) is None

    queue_ui.finish_operator_inspection(state, first_claim, completed=True)

    assert queue_ui.claim_operator_inspection(state) is None

    queue_ui.navigate_operator_pcb4(state, 1, 100)
    second_claim = queue_ui.claim_operator_inspection(state)

    assert second_claim is not None
    assert second_claim != first_claim


def test_manual_upload_override_cancels_pending_autorun() -> None:
    state = {
        "pcb4_pending_autorun": True,
        "pcb4_autorun_in_progress": True,
        "pcb4_current_item": DatasetInspectionItem(
            Path("/repo/a001.JPG"), "Anomaly", "PCB4 / Anomaly / 001"
        ),
    }
    initialize_ui_state(state)

    queue_ui.cancel_pcb4_pending_autorun(state)
    state["pcb4_current_item"] = None

    assert state["pcb4_pending_autorun"] is False
    assert state["pcb4_autorun_in_progress"] is False
    assert queue_ui.current_pcb4_item(state) is None
