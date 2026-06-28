import base64
import mimetypes
import os
from pathlib import Path

import pytest
from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
REFERENCE_PATH = PROJECT_ROOT / "sample_cases" / "reference.jpg"
INSPECTION_PATH = PROJECT_ROOT / "sample_cases" / "inspection.jpg"


def validate_image(image_path: Path, label: str) -> None:
    if not image_path.exists():
        raise FileNotFoundError(f"{label} image not found: {image_path}")

    with Image.open(image_path) as image:
        print(
            f"{label}: "
            f"path={image_path.resolve()}, "
            f"size={image.size}, "
            f"format={image.format}"
        )


def image_to_data_uri(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(image_path.name)

    if mime_type not in {"image/jpeg", "image/png"}:
        raise ValueError(f"Unsupported image type for {image_path}: {mime_type}")

    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def run_live_pair_smoke() -> None:
    load_dotenv(ENV_PATH)
    validate_image(REFERENCE_PATH, "Reference")
    validate_image(INSPECTION_PATH, "Inspection")

    api_key = os.getenv("CEREBRAS_API_KEY")
    model = os.getenv("CEREBRAS_MODEL", "gemma-4-31b")

    if not api_key:
        raise RuntimeError(f"CEREBRAS_API_KEY was not loaded from {ENV_PATH}")

    client = Cerebras(api_key=api_key)
    reference_uri = image_to_data_uri(REFERENCE_PATH)
    inspection_uri = image_to_data_uri(INSPECTION_PATH)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a conservative industrial visual-inspection assistant. "
                    "Image 1 is a known-good golden reference. "
                    "Image 2 is an inspected product of the same design. "
                    "Report only visible evidence. "
                    "Clearly separate confirmed observations from hypotheses. "
                    "Do not infer electrical functionality, internal damage, "
                    "component specifications, or root causes unless directly "
                    "supported by the images."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Compare Image 1, the golden reference, with Image 2, "
                            "the inspected product.\n\n"
                            "Return the following sections:\n"
                            "1. Confirmed visible differences\n"
                            "2. Suspected anomaly regions\n"
                            "3. Possible interpretations, clearly marked as hypotheses\n"
                            "4. Severity: pass, manual review, rework, or reject\n"
                            "5. Recommended next inspection action\n"
                            "6. Uncertainty and limitations\n\n"
                            "Do not claim functional failure based only on appearance."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": reference_uri}},
                    {"type": "image_url", "image_url": {"url": inspection_uri}},
                ],
            },
        ],
        max_completion_tokens=1000,
        temperature=0.1,
    )

    print("\n=== Visual Inspection Report ===\n")
    print(response.choices[0].message.content)


@pytest.mark.integration
def test_live_pair_smoke() -> None:
    if os.getenv("RUN_LIVE_API_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_API_TESTS=1 to run live Cerebras smoke tests.")
    run_live_pair_smoke()


if __name__ == "__main__":
    run_live_pair_smoke()
