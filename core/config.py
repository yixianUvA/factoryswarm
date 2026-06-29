from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]

VALID_PROVIDERS = {"cerebras", "google"}

_PROVIDER_MODEL_DEFAULTS: dict[str, str] = {
    "cerebras": "gemma-4-31b",
    # Google AI Studio OpenAI-compatible endpoint.
    # Use the model ID returned by the models list (without the "models/" prefix).
    "google": "gemma-4-31b-it",
}

# Google AI Studio's strict json_schema response_format is not fully compatible;
# use the JSON repair path instead (use_json_schema=False).
_PROVIDER_JSON_SCHEMA_DEFAULTS: dict[str, bool] = {
    "cerebras": True,
    "google": False,
}


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class FactorySwarmConfig:
    provider: str
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
    max_concurrent_calls: int


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

    provider = (os.getenv("FACTORYSWARM_PROVIDER") or "cerebras").strip().lower()
    if provider not in VALID_PROVIDERS:
        raise ConfigError(
            f"FACTORYSWARM_PROVIDER must be one of: {', '.join(sorted(VALID_PROVIDERS))}. Got: {provider!r}"
        )

    # API key: FACTORYSWARM_API_KEY overrides everything; then provider-specific key.
    # CEREBRAS_API_KEY is kept as a legacy alias when provider=cerebras.
    api_key = (
        os.getenv("FACTORYSWARM_API_KEY")
        or os.getenv(f"{provider.upper()}_API_KEY")
    ) or None

    if require_api_key and not api_key:
        provider_key_name = f"{provider.upper()}_API_KEY"
        raise ConfigError(
            f"No API key found for provider '{provider}'. "
            f"Set FACTORYSWARM_API_KEY or {provider_key_name} in .env or the environment."
        )

    # Model: FACTORYSWARM_MODEL overrides; then provider-specific env var; then built-in default.
    model = (
        os.getenv("FACTORYSWARM_MODEL")
        or os.getenv(f"{provider.upper()}_MODEL")
        or _PROVIDER_MODEL_DEFAULTS[provider]
    ).strip()
    if not model:
        raise ConfigError("Model name must not be empty.")

    reasoning_effort: str | None = None
    if provider == "cerebras":
        reasoning_effort = os.getenv("CEREBRAS_REASONING_EFFORT") or None
        if reasoning_effort and reasoning_effort not in {"low", "medium", "high"}:
            raise ConfigError("CEREBRAS_REASONING_EFFORT must be low, medium, or high.")

    use_json_schema_default = _PROVIDER_JSON_SCHEMA_DEFAULTS[provider]

    return FactorySwarmConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        timeout_seconds=_float_env("FACTORYSWARM_TIMEOUT_SECONDS", 60.0),
        max_completion_tokens=_int_env("FACTORYSWARM_MAX_COMPLETION_TOKENS", 1400),
        temperature=_float_env("FACTORYSWARM_TEMPERATURE", 0.1),
        max_upload_bytes=_int_env("FACTORYSWARM_MAX_UPLOAD_BYTES", 8 * 1024 * 1024),
        retry_count=_int_env("FACTORYSWARM_RETRY_COUNT", 1),
        reasoning_effort=reasoning_effort,
        debug=_bool_env("FACTORYSWARM_DEBUG", False),
        use_json_schema=_bool_env("FACTORYSWARM_USE_JSON_SCHEMA", use_json_schema_default),
        max_concurrent_calls=_int_env("FACTORYSWARM_MAX_CONCURRENT_CALLS", 4),
    )
