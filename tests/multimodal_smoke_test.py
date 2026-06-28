import base64
import mimetypes
import os
from pathlib import Path

import pytest
from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_PATH = PROJECT_ROOT / "sample_cases" / "test.jpg"


def image_to_data_uri(image_path: Path) -> str:
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    mime_type, _ = mimetypes.guess_type(image_path.name)
    if mime_type not in {"image/jpeg", "image/png"}:
        raise ValueError("Only JPEG and PNG images are supported.")

    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def run_live_multimodal_smoke() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("CEREBRAS_API_KEY")
    model = os.getenv("CEREBRAS_MODEL", "gemma-4-31b")

    if not api_key:
        raise RuntimeError("CEREBRAS_API_KEY is missing.")

    image_data_uri = image_to_data_uri(IMAGE_PATH)
    client = Cerebras(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a manufacturing visual-inspection assistant. "
                    "Describe only visible evidence and clearly state uncertainty."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Inspect this image. List the visible object, possible "
                            "surface abnormalities, and anything that cannot be "
                            "determined from the image."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": image_data_uri}},
                ],
            },
        ],
        max_completion_tokens=500,
        temperature=0.2,
    )

    print(response.choices[0].message.content)


@pytest.mark.integration
def test_live_multimodal_smoke() -> None:
    if os.getenv("RUN_LIVE_API_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_API_TESTS=1 to run live Cerebras smoke tests.")
    run_live_multimodal_smoke()


if __name__ == "__main__":
    run_live_multimodal_smoke()
