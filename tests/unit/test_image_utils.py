from io import BytesIO

import pytest
from PIL import Image

from core.image_utils import (
    ImageValidationError,
    create_mask_overlay,
    validate_image_bytes,
)


def image_bytes(fmt: str = "PNG", size: tuple[int, int] = (16, 12)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (100, 120, 140)).save(buffer, format=fmt)
    return buffer.getvalue()


def test_valid_png_is_normalized_and_encoded() -> None:
    result = validate_image_bytes(
        image_bytes("PNG"),
        filename="part.png",
        label="Inspection",
        max_bytes=100_000,
        declared_mime_type="image/png",
    )

    assert result.width == 16
    assert result.height == 12
    assert result.image.mode == "RGB"
    assert result.data_uri.startswith("data:image/png;base64,")


def test_unsupported_mime_type_is_rejected() -> None:
    with pytest.raises(ImageValidationError):
        validate_image_bytes(
            b"GIF89a",
            filename="part.gif",
            label="Inspection",
            max_bytes=100_000,
            declared_mime_type="image/gif",
        )


def test_corrupt_image_is_rejected() -> None:
    with pytest.raises(ImageValidationError):
        validate_image_bytes(
            b"not an image",
            filename="part.png",
            label="Inspection",
            max_bytes=100_000,
            declared_mime_type="image/png",
        )


def test_oversized_image_is_rejected() -> None:
    with pytest.raises(ImageValidationError):
        validate_image_bytes(
            image_bytes("PNG"),
            filename="part.png",
            label="Inspection",
            max_bytes=2,
            declared_mime_type="image/png",
        )


def test_mask_overlay_requires_matching_dimensions() -> None:
    inspection = Image.new("RGB", (10, 10), "white")
    mask = Image.new("L", (8, 10), 255)

    with pytest.raises(ImageValidationError):
        create_mask_overlay(inspection, mask)
