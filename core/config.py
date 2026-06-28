from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class FactorySwarmConfig:
    api_key: str | None
    model: str
    timeout_seconds: float
    max_completion_tokens: int
    temperature: float
    max_upload_bytes: int
    retry_count: int
    reasoning_effort: str | None
    debug: bool
    use_json_schema: bool


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer.") from exc
    if parsed < 0:
        raise ConfigError(f"{name} must be non-negative.")
    return parsed


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number.") from exc
    if parsed < 0:
        raise ConfigError(f"{name} must be non-negative.")
    return parsed


def load_config(require_api_key: bool = True) -> FactorySwarmConfig:
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("CEREBRAS_API_KEY")
    if require_api_key and not api_key:
        raise ConfigError(
            "CEREBRAS_API_KEY is missing. Add it to .env or export it before running FactorySwarm."
        )

    model = os.getenv("CEREBRAS_MODEL", "gemma-4-31b").strip()
    if not model:
        raise ConfigError("CEREBRAS_MODEL must not be empty.")

    reasoning_effort = os.getenv("CEREBRAS_REASONING_EFFORT") or None
    if reasoning_effort and reasoning_effort not in {"low", "medium", "high"}:
        raise ConfigError("CEREBRAS_REASONING_EFFORT must be low, medium, or high.")

    return FactorySwarmConfig(
        api_key=api_key,
        model=model,
        timeout_seconds=_float_env("FACTORYSWARM_TIMEOUT_SECONDS", 60.0),
        max_completion_tokens=_int_env("FACTORYSWARM_MAX_COMPLETION_TOKENS", 1400),
        temperature=_float_env("FACTORYSWARM_TEMPERATURE", 0.1),
        max_upload_bytes=_int_env("FACTORYSWARM_MAX_UPLOAD_BYTES", 8 * 1024 * 1024),
        retry_count=_int_env("FACTORYSWARM_RETRY_COUNT", 1),
        reasoning_effort=reasoning_effort,
        debug=_bool_env("FACTORYSWARM_DEBUG", False),
        use_json_schema=_bool_env("FACTORYSWARM_USE_JSON_SCHEMA", True),
    )
