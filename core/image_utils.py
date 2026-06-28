from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png"}
SUPPORTED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png"}
EXIF_ORIENTATION_TAG = 274


class ImageValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedImage:
    label: str
    filename: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    image: Image.Image
    data_uri: str


@dataclass(frozen=True)
class InspectionImageSet:
    reference: ValidatedImage
    inspection: ValidatedImage
    reference_roi: ValidatedImage | None = None
    inspection_roi: ValidatedImage | None = None

    @property
    def has_roi_pair(self) -> bool:
        return self.reference_roi is not None and self.inspection_roi is not None


def _mime_from_name(filename: str) -> str | None:
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type


def _encode_image(image: Image.Image, mime_type: str) -> bytes:
    buffer = BytesIO()
    if mime_type == "image/jpeg":
        image.save(buffer, format="JPEG", quality=95, optimize=True)
    elif mime_type == "image/png":
        image.save(buffer, format="PNG", optimize=True)
    else:
        raise ImageValidationError("Only JPEG and PNG images are supported.")
    return buffer.getvalue()


def _to_data_uri(data: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def validate_image_bytes(
    data: bytes,
    filename: str,
    label: str,
    max_bytes: int,
    declared_mime_type: str | None = None,
) -> ValidatedImage:
    if not data:
        raise ImageValidationError(f"{label} image is empty.")
    if len(data) > max_bytes:
        limit_mb = max_bytes / (1024 * 1024)
        raise ImageValidationError(
            f"{label} image is too large. Maximum allowed size is {limit_mb:.1f} MB."
        )

    guessed_mime = declared_mime_type or _mime_from_name(filename)
    if guessed_mime not in SUPPORTED_MIME_TYPES:
        raise ImageValidationError(
            f"{label} image must be JPEG or PNG. Received {guessed_mime or 'unknown type'}."
        )

    try:
        with Image.open(BytesIO(data)) as opened:
            opened.load()
            detected_mime = SUPPORTED_FORMATS.get(opened.format or "")
            if detected_mime not in SUPPORTED_MIME_TYPES:
                raise ImageValidationError(
                    f"{label} image content is not a supported JPEG or PNG file."
                )
            if declared_mime_type and declared_mime_type not in SUPPORTED_MIME_TYPES:
                raise ImageValidationError(
                    f"{label} image has unsupported MIME type {declared_mime_type}."
                )

            orientation = opened.getexif().get(EXIF_ORIENTATION_TAG, 1)
            normalized = ImageOps.exif_transpose(opened)
            normalized = normalized.convert("RGB")
            output_mime = detected_mime
            if orientation != 1 or opened.mode != "RGB":
                encoded = _encode_image(normalized, output_mime)
            else:
                encoded = data
    except UnidentifiedImageError as exc:
        raise ImageValidationError(f"{label} image is corrupt or unreadable.") from exc
    except OSError as exc:
        raise ImageValidationError(f"{label} image is corrupt or unreadable.") from exc

    return ValidatedImage(
        label=label,
        filename=filename,
        mime_type=output_mime,
        size_bytes=len(data),
        width=normalized.width,
        height=normalized.height,
        image=normalized.copy(),
        data_uri=_to_data_uri(encoded, output_mime),
    )


def load_image_from_path(path: Path, label: str, max_bytes: int) -> ValidatedImage:
    if not path.exists():
        raise ImageValidationError(f"{label} image not found: {path}")
    return validate_image_bytes(
        data=path.read_bytes(),
        filename=path.name,
        label=label,
        max_bytes=max_bytes,
        declared_mime_type=_mime_from_name(path.name),
    )


def crop_validated_image(
    source: ValidatedImage,
    box: dict[str, int],
    label: str,
    filename: str,
) -> ValidatedImage:
    required = {"x", "y", "width", "height"}
    if set(box) != required:
        raise ImageValidationError(f"{label} crop box must contain x, y, width, and height.")
    x = box["x"]
    y = box["y"]
    width = box["width"]
    height = box["height"]
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ImageValidationError(f"{label} crop box must have positive dimensions.")
    if x + width > source.width or y + height > source.height:
        raise ImageValidationError(f"{label} crop box extends outside the source image.")

    crop = source.image.crop((x, y, x + width, y + height)).convert("RGB")
    encoded = _encode_image(crop, source.mime_type)
    return ValidatedImage(
        label=label,
        filename=filename,
        mime_type=source.mime_type,
        size_bytes=len(encoded),
        width=crop.width,
        height=crop.height,
        image=crop,
        data_uri=_to_data_uri(encoded, source.mime_type),
    )


def validate_uploaded_image(uploaded_file, label: str, max_bytes: int) -> ValidatedImage:
    return validate_image_bytes(
        data=uploaded_file.getvalue(),
        filename=uploaded_file.name,
        label=label,
        max_bytes=max_bytes,
        declared_mime_type=getattr(uploaded_file, "type", None),
    )


def build_inspection_image_set(
    reference: ValidatedImage,
    inspection: ValidatedImage,
    reference_roi: ValidatedImage | None = None,
    inspection_roi: ValidatedImage | None = None,
) -> InspectionImageSet:
    if (reference_roi is None) != (inspection_roi is None):
        raise ImageValidationError(
            "Reference ROI and inspection ROI must be provided together as corresponding crops."
        )
    return InspectionImageSet(
        reference=reference,
        inspection=inspection,
        reference_roi=reference_roi,
        inspection_roi=inspection_roi,
    )


def create_mask_overlay(
    inspection_image: Image.Image,
    mask_image: Image.Image,
    alpha: float = 0.45,
) -> Image.Image:
    if inspection_image.size != mask_image.size:
        raise ImageValidationError(
            "Annotation mask dimensions must match the inspection image before overlay."
        )

    base = inspection_image.convert("RGBA")
    mask = mask_image.convert("L")
    red = Image.new("RGBA", base.size, (255, 0, 0, 0))
    scaled_alpha = mask.point(lambda pixel: int((pixel / 255) * 255 * alpha))
    red.putalpha(scaled_alpha)
    return Image.alpha_composite(base, red).convert("RGB")
