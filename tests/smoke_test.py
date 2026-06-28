import os

import pytest
from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv


def run_live_smoke() -> None:
    load_dotenv()

    api_key = os.getenv("CEREBRAS_API_KEY")
    model = os.getenv("CEREBRAS_MODEL", "gemma-4-31b")

    if not api_key:
        raise RuntimeError("CEREBRAS_API_KEY is missing.")

    client = Cerebras(api_key=api_key)

    stream = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a concise manufacturing inspection assistant.",
            },
            {
                "role": "user",
                "content": "Explain visual quality inspection in two sentences.",
            },
        ],
        stream=True,
        max_completion_tokens=256,
        temperature=0.2,
    )

    for chunk in stream:
        content = chunk.choices[0].delta.content
        if content:
            print(content, end="", flush=True)

    print()


@pytest.mark.integration
def test_live_text_generation_smoke() -> None:
    if os.getenv("RUN_LIVE_API_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_API_TESTS=1 to run live Cerebras smoke tests.")
    run_live_smoke()


if __name__ == "__main__":
    run_live_smoke()
