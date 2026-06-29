from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any, TypeVar

from openai import AsyncOpenAI, RateLimitError
from pydantic import BaseModel, ValidationError

from core.config import FactorySwarmConfig, load_config


ModelT = TypeVar("ModelT", bound=BaseModel)

_PROVIDER_BASE_URLS: dict[str, str] = {
    "cerebras": "https://api.cerebras.ai/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai/",
}


@dataclass(frozen=True)
class CerebrasCallResult:
    success: bool
    content: str | None
    latency_seconds: float
    error_message: str | None = None


class StructuredOutputError(ValueError):
    pass


def _schema_response_format(model: type[BaseModel]) -> dict[str, Any]:
    schema = _sanitize_json_schema(model.model_json_schema())
    return {
        "type": "json_schema",
        "json_schema": {
            "name": model.__name__,
            "schema": schema,
            "strict": True,
        },
    }


# JSON Schema validation keywords that OpenAI strict mode rejects outright.
# We strip them all; Pydantic re-validates the response after parsing anyway.
_UNSUPPORTED_SCHEMA_KEYWORDS = {
    "minLength", "maxLength",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minItems", "maxItems",
    "minProperties", "maxProperties",
    "pattern",
}


def _sanitize_json_schema(value: Any) -> Any:
    """Adapt a Pydantic JSON schema for use as an API response_format.

    OpenAI strict mode has two extra requirements beyond standard JSON Schema:
    - every key in `properties` must appear in `required` (even nullable fields);
    - validation constraint keywords (minimum, maxLength, …) are rejected.
    Both are handled here so the same sanitisation works for all providers.
    """
    if isinstance(value, dict):
        cleaned = {
            key: _sanitize_json_schema(item)
            for key, item in value.items()
            if key not in _UNSUPPORTED_SCHEMA_KEYWORDS
        }
        # OpenAI strict mode forbids sibling keywords alongside $ref (e.g. "default").
        if "$ref" in cleaned and len(cleaned) > 1:
            cleaned = {"$ref": cleaned["$ref"]}
        # Ensure required covers every property (Pydantic omits defaulted fields).
        if "properties" in cleaned:
            cleaned["required"] = list(cleaned["properties"].keys())
        return cleaned
    if isinstance(value, list):
        return [_sanitize_json_schema(item) for item in value]
    return value


def _rate_limit_wait(exc: RateLimitError, attempt: int) -> float:
    """Return how long to sleep after a 429, honouring the provider's suggestion."""
    floor = min(60.0, 5.0 * (2 ** attempt))
    # The error message body reliably contains "Please try again in 5.78s."
    match = re.search(r"try again in (\d+(?:\.\d+)?)s", str(exc))
    if match:
        return max(floor, float(match.group(1)))
    # Fallback: standard retry-after header (and OpenAI's x-ratelimit-reset-* headers).
    try:
        for name in ("retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
            raw = exc.response.headers.get(name, "")
            if raw:
                return max(floor, float(raw))
    except (AttributeError, ValueError, TypeError):
        pass
    return floor


def sanitize_error(exc: BaseException, api_key: str | None = None) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    if api_key:
        message = message.replace(api_key, "[redacted]")
    return message[:500]


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise StructuredOutputError("Model returned an empty response.")

    # Strip markdown code fences (```json … ``` or ``` … ```) that some models add.
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:]  # drop opening fence line (```json, ```, etc.)
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]  # drop closing fence
        stripped = "\n".join(lines).strip()

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            print(text, file=__import__("sys").stderr, flush=True)
            raise StructuredOutputError("Model response did not contain a JSON object.")
        candidate = stripped[start : end + 1]
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError("Model response contained malformed JSON.") from exc

    if not isinstance(parsed, dict):
        raise StructuredOutputError("Model response must be a JSON object.")
    return parsed


def parse_json_model(text: str, model: type[ModelT]) -> ModelT:
    try:
        return model.model_validate(extract_json_object(text))
    except ValidationError as exc:
        raise StructuredOutputError(str(exc)) from exc


class CerebrasClient:
    def __init__(self, config: FactorySwarmConfig | None = None) -> None:
        self.config = config or load_config(require_api_key=True)
        if not self.config.api_key:
            raise RuntimeError(
                f"API key is missing for provider '{self.config.provider}'."
            )
        base_url = _PROVIDER_BASE_URLS.get(
            self.config.provider, _PROVIDER_BASE_URLS["cerebras"]
        )
        self._client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=base_url,
            timeout=self.config.timeout_seconds,
            max_retries=0,  # Manual retry loop below handles retries.
        )

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        response_model: type[BaseModel] | None = None,
        max_completion_tokens: int | None = None,
        temperature: float | None = None,
    ) -> CerebrasCallResult:
        start = time.perf_counter()
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_completion_tokens": max_completion_tokens
            or self.config.max_completion_tokens,
            "temperature": self.config.temperature if temperature is None else temperature,
        }
        # reasoning_effort is a Cerebras-specific extension.
        if self.config.reasoning_effort and self.config.provider == "cerebras":
            kwargs["reasoning_effort"] = self.config.reasoning_effort
        if response_model is not None and self.config.use_json_schema:
            kwargs["response_format"] = _schema_response_format(response_model)
        elif response_model is not None:
            # json_object mode: API guarantees valid JSON without enforcing the full schema.
            # Pydantic validates the structure on our side after parsing.
            kwargs["response_format"] = {"type": "json_object"}

        attempts = max(1, self.config.retry_count + 1)
        last_error: BaseException | None = None
        for attempt in range(attempts):
            try:
                response = await self._client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content
                latency = time.perf_counter() - start
                if not content:
                    return CerebrasCallResult(
                        success=False,
                        content=None,
                        latency_seconds=latency,
                        error_message="The model returned an empty response.",
                    )
                return CerebrasCallResult(
                    success=True,
                    content=content,
                    latency_seconds=latency,
                )
            except asyncio.CancelledError:
                raise
            except RateLimitError as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    await asyncio.sleep(_rate_limit_wait(exc, attempt))
            except Exception as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.5 * (attempt + 1))

        return CerebrasCallResult(
            success=False,
            content=None,
            latency_seconds=time.perf_counter() - start,
            error_message=sanitize_error(
                last_error or RuntimeError("Unknown API error"), self.config.api_key
            ),
        )


_CLIENT: CerebrasClient | None = None


def get_cerebras_client() -> CerebrasClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = CerebrasClient()
    return _CLIENT


def reset_client() -> None:
    global _CLIENT
    _CLIENT = None
