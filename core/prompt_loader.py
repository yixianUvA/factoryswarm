from __future__ import annotations

from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPT_DIR = PROJECT_ROOT / "prompts"
ALLOWED_PROMPTS = {
    "visual": "visual.txt",
    "components": "components.txt",
    "quality": "quality.txt",
    "actions": "actions.txt",
    "verifier": "verifier.txt",
}


class PromptError(RuntimeError):
    pass


@lru_cache(maxsize=len(ALLOWED_PROMPTS))
def load_prompt(name: str) -> str:
    filename = ALLOWED_PROMPTS.get(name)
    if filename is None:
        raise PromptError(f"Unknown prompt: {name}")

    path = PROMPT_DIR / filename
    try:
        prompt = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise PromptError(f"Missing prompt file: {path}") from exc

    if not prompt:
        raise PromptError(f"Prompt file is empty: {path}")
    return prompt
