from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from core.config import PROJECT_ROOT


PCB4_IMAGE_ROOT = PROJECT_ROOT / "data" / "pcb4" / "Data" / "Images"
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


class DatasetQueueError(ValueError):
    pass


@dataclass(frozen=True)
class DatasetInspectionItem:
    path: Path
    category: str
    item_id: str


@dataclass(frozen=True)
class DatasetInspectionQueue:
    reference_path: Path
    items: tuple[DatasetInspectionItem, ...]


def natural_sort_key(path: Path) -> tuple[object, ...]:
    parts = re.split(r"(\d+)", path.name.lower())
    return tuple(int(part) if part.isdigit() else part for part in parts)


def _valid_image_paths(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    paths = [
        path
        for path in directory.iterdir()
        if path.is_file()
        and not path.name.startswith(".")
        and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
    ]
    return sorted(paths, key=natural_sort_key)


def _item_id(root: Path, path: Path, category: str) -> str:
    try:
        relative = path.relative_to(root / category)
    except ValueError:
        relative = path.name
    return f"PCB4 / {category} / {Path(relative).stem}"


def discover_pcb4_queue(root: Path = PCB4_IMAGE_ROOT) -> DatasetInspectionQueue:
    if not root.exists():
        raise DatasetQueueError("PCB4 dataset not found. Expected: data/pcb4/Data/Images")

    normal_dir = root / "Normal"
    anomaly_dir = root / "Anomaly"
    normal_paths = _valid_image_paths(normal_dir)
    if not normal_paths:
        raise DatasetQueueError(
            "PCB4 queue cannot start because no normal reference image was found."
        )

    reference_path = normal_paths[0].resolve()
    seen: set[Path] = set()
    items: list[DatasetInspectionItem] = []
    for category, paths in (
        ("Anomaly", _valid_image_paths(anomaly_dir)),
        ("Normal", normal_paths),
    ):
        for path in paths:
            resolved = path.resolve()
            if resolved == reference_path or resolved in seen:
                continue
            seen.add(resolved)
            items.append(
                DatasetInspectionItem(
                    path=resolved,
                    category=category,
                    item_id=_item_id(root, path, category),
                )
            )

    return DatasetInspectionQueue(reference_path=reference_path, items=tuple(items))
