from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.config import PROJECT_ROOT
from core.image_utils import (
    InspectionImageSet,
    build_inspection_image_set,
    crop_validated_image,
    load_image_from_path,
)


SAMPLE_CONFIG_PATH = PROJECT_ROOT / "sample_cases" / "sample_config.json"


@dataclass(frozen=True)
class SampleCase:
    name: str
    image_set: InspectionImageSet
    roi_description: str


def load_sample_config(path: Path = SAMPLE_CONFIG_PATH) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_builtin_pcb_sample(max_bytes: int) -> SampleCase:
    config = load_sample_config()
    reference = load_image_from_path(
        PROJECT_ROOT / config.get("reference_image", "sample_cases/reference.jpg"),
        "Reference",
        max_bytes,
    )
    inspection = load_image_from_path(
        PROJECT_ROOT / config.get("inspection_image", "sample_cases/inspection.jpg"),
        "Inspection",
        max_bytes,
    )
    boxes = config["roi_boxes"]
    reference_roi = crop_validated_image(
        reference,
        boxes["reference"],
        "Reference ROI",
        "reference_roi.jpg",
    )
    inspection_roi = crop_validated_image(
        inspection,
        boxes["inspection"],
        "Inspection ROI",
        "inspection_roi.jpg",
    )
    return SampleCase(
        name=config.get("name", "PCB sample"),
        image_set=build_inspection_image_set(
            reference,
            inspection,
            reference_roi=reference_roi,
            inspection_roi=inspection_roi,
        ),
        roi_description=config.get("roi_description", "Corresponding local ROI crops."),
    )
