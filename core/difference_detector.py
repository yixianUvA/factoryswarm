from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class DifferenceResult:
    aligned_inspection: np.ndarray
    heatmap: np.ndarray
    overlay: np.ndarray
    bounding_boxes: list[tuple[int, int, int, int]]


def load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))

    if image is None:
        raise FileNotFoundError(f"Could not read image: {path}")

    return image


def align_image(
    reference: np.ndarray,
    inspection: np.ndarray,
) -> np.ndarray:
    reference_gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
    inspection_gray = cv2.cvtColor(inspection, cv2.COLOR_BGR2GRAY)

    orb = cv2.ORB_create(nfeatures=4000)

    keypoints_ref, descriptors_ref = orb.detectAndCompute(
        reference_gray,
        None,
    )
    keypoints_ins, descriptors_ins = orb.detectAndCompute(
        inspection_gray,
        None,
    )

    if descriptors_ref is None or descriptors_ins is None:
        raise RuntimeError("Not enough visual features for alignment.")

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = matcher.match(descriptors_ins, descriptors_ref)
    matches = sorted(matches, key=lambda match: match.distance)

    good_matches = matches[: min(500, len(matches))]

    if len(good_matches) < 10:
        raise RuntimeError("Not enough reliable matches for alignment.")

    inspection_points = np.float32(
        [keypoints_ins[m.queryIdx].pt for m in good_matches]
    ).reshape(-1, 1, 2)

    reference_points = np.float32(
        [keypoints_ref[m.trainIdx].pt for m in good_matches]
    ).reshape(-1, 1, 2)

    homography, _ = cv2.findHomography(
        inspection_points,
        reference_points,
        cv2.RANSAC,
        5.0,
    )

    if homography is None:
        raise RuntimeError("Image alignment failed.")

    height, width = reference.shape[:2]

    return cv2.warpPerspective(
        inspection,
        homography,
        (width, height),
    )


def detect_differences(
    reference_path: Path,
    inspection_path: Path,
    minimum_area: int = 250,
) -> DifferenceResult:
    reference = load_image(reference_path)
    inspection = load_image(inspection_path)

    aligned = align_image(reference, inspection)

    reference_gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
    aligned_gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)

    difference = cv2.absdiff(reference_gray, aligned_gray)
    difference = cv2.GaussianBlur(difference, (7, 7), 0)

    _, binary = cv2.threshold(
        difference,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )

    kernel = np.ones((5, 5), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(
        binary,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    boxes = []

    for contour in contours:
        if cv2.contourArea(contour) < minimum_area:
            continue

        boxes.append(cv2.boundingRect(contour))

    boxes.sort(key=lambda box: box[2] * box[3], reverse=True)

    heatmap = cv2.applyColorMap(difference, cv2.COLORMAP_JET)
    overlay = aligned.copy()

    for x, y, width, height in boxes[:5]:
        cv2.rectangle(
            overlay,
            (x, y),
            (x + width, y + height),
            (0, 0, 255),
            4,
        )

    return DifferenceResult(
        aligned_inspection=aligned,
        heatmap=heatmap,
        overlay=overlay,
        bounding_boxes=boxes[:5],
    )