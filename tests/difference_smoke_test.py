from pathlib import Path

import cv2
import pytest

from core.difference_detector import detect_differences


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_difference_smoke() -> None:
    reference_path = PROJECT_ROOT / "sample_cases" / "reference.jpg"
    inspection_path = PROJECT_ROOT / "sample_cases" / "inspection.jpg"
    output_dir = PROJECT_ROOT / "sample_cases" / "generated"

    output_dir.mkdir(parents=True, exist_ok=True)

    result = detect_differences(
        reference_path=reference_path,
        inspection_path=inspection_path,
    )

    cv2.imwrite(str(output_dir / "aligned_inspection.jpg"), result.aligned_inspection)
    cv2.imwrite(str(output_dir / "difference_heatmap.jpg"), result.heatmap)
    cv2.imwrite(str(output_dir / "difference_overlay.jpg"), result.overlay)

    print("Detected regions:")
    for box in result.bounding_boxes:
        print(box)

    print(f"Results saved to: {output_dir}")


@pytest.mark.integration
def test_difference_smoke() -> None:
    pytest.skip("Run this manually with python tests/difference_smoke_test.py.")


if __name__ == "__main__":
    run_difference_smoke()
