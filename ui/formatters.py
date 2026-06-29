from __future__ import annotations

from html import escape
from typing import Any

from core.schemas import InspectionDecision


def html_escape(value: Any) -> str:
    return escape(str(value), quote=True)


def decision_label(decision: InspectionDecision | str) -> str:
    value = decision.value if isinstance(decision, InspectionDecision) else str(decision)
    return value.replace("_", " ").upper()


def format_confidence(confidence: float | None) -> str:
    if confidence is None:
        return "—"
    return f"{confidence:.0%}"


def format_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    return f"{seconds:.2f}s"


def format_speedup(speedup: float | None) -> str:
    if speedup is None:
        return "—"
    return f"{speedup:.2f}×"


def normalize_status(status: str) -> str:
    return status.lower().replace(" ", "-").replace("_", "-")
