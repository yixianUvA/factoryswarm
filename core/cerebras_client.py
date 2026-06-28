from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, TypeVar

from cerebras.cloud.sdk import AsyncCerebras
from pydantic import BaseModel, ValidationError

from core.config import FactorySwarmConfig, load_config


ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True)
class CerebrasCallResult:
    success: bool
    content: str | None
    latency_seconds: float
    error_message: str | None = None


class StructuredOutputError(ValueError):
    pass


def _schema_response_format(model: type[BaseModel]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": model.__name__,
            "schema": model.model_json_schema(),
            "strict": True,
        },
    }


def sanitize_error(exc: BaseException, api_key: str | None = None) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    if api_key:
        message = message.replace(api_key, "[redacted]")
    return message[:500]


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise StructuredOutputError("Model returned an empty response.")

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
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
            raise RuntimeError("CEREBRAS_API_KEY is missing.")
        self._client = AsyncCerebras(
            api_key=self.config.api_key,
            timeout=self.config.timeout_seconds,
            max_retries=self.config.retry_count,
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
        if self.config.reasoning_effort:
            kwargs["reasoning_effort"] = self.config.reasoning_effort
        if response_model is not None and self.config.use_json_schema:
            kwargs["response_format"] = _schema_response_format(response_model)

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
            except Exception as exc:  # SDK errors vary by transport and response class.
                last_error = exc
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.5 * (attempt + 1))

        return CerebrasCallResult(
            success=False,
            content=None,
            latency_seconds=time.perf_counter() - start,
            error_message=sanitize_error(last_error or RuntimeError("Unknown API error"), self.config.api_key),
        )


_CLIENT: CerebrasClient | None = None


def get_cerebras_client() -> CerebrasClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = CerebrasClient()
    return _CLIENT
