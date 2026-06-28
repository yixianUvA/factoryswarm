import argparse
from pathlib import Path

import cv2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--mask", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--padding", type=int, default=50)
    args = parser.parse_args()

    reference = cv2.imread(str(args.reference))
    inspection = cv2.imread(str(args.inspection))
    mask = cv2.imread(str(args.mask), cv2.IMREAD_GRAYSCALE)

    if reference is None:
        raise FileNotFoundError(f"Cannot read reference: {args.reference}")

    if inspection is None:
        raise FileNotFoundError(f"Cannot read inspection: {args.inspection}")

    if mask is None:
        raise FileNotFoundError(f"Cannot read mask: {args.mask}")

    if reference.shape[:2] != inspection.shape[:2]:
        raise ValueError(
            "Reference and inspection images must have the same dimensions."
        )

    if mask.shape[:2] != inspection.shape[:2]:
        raise ValueError(
            "Mask and inspection image must have the same dimensions."
        )

    points = cv2.findNonZero(mask)

    if points is None:
        raise RuntimeError("The mask does not contain an anomaly region.")

    x, y, width, height = cv2.boundingRect(points)

    image_height, image_width = inspection.shape[:2]
    padding = args.padding

    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(image_width, x + width + padding)
    y2 = min(image_height, y + height + padding)

    reference_crop = reference[y1:y2, x1:x2]
    inspection_crop = inspection[y1:y2, x1:x2]

    args.output.mkdir(parents=True, exist_ok=True)

    cv2.imwrite(
        str(args.output / "reference_roi.jpg"),
        reference_crop,
    )
    cv2.imwrite(
        str(args.output / "inspection_roi.jpg"),
        inspection_crop,
    )

    overlay = inspection.copy()
    cv2.rectangle(
        overlay,
        (x1, y1),
        (x2, y2),
        (0, 0, 255),
        5,
    )

    cv2.imwrite(
        str(args.output / "inspection_roi_overlay.jpg"),
        overlay,
    )

    print("Anomaly bounding box:", (x1, y1, x2 - x1, y2 - y1))
    print("Files saved to:", args.output.resolve())


if __name__ == "__main__":
    main()