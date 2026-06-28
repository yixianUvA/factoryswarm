from __future__ import annotations

from typing import Any

from core.cerebras_client import (
    CerebrasCallResult,
    CerebrasClient,
    StructuredOutputError,
    parse_json_model,
)
from core.prompt_loader import load_prompt
from core.schemas import InspectionDecision, ReportStatus, SpecialistReport


def build_context_text(
    asset_type: str | None = None,
    inspection_stage: str | None = None,
    reported_symptom: str | None = None,
) -> str:
    lines = []
    if asset_type:
        lines.append(f"Asset type: {asset_type}")
    if inspection_stage:
        lines.append(f"Inspection stage: {inspection_stage}")
    if reported_symptom:
        lines.append(f"Reported symptom: {reported_symptom}")
    if not lines:
        return ""
    return "Optional factory context:\n" + "\n".join(lines)


def specialist_failure_report(
    agent_name: str,
    error_message: str,
    latency_seconds: float | None = None,
) -> SpecialistReport:
    return SpecialistReport(
        agent_name=agent_name,
        summary="The specialist could not produce a validated report.",
        findings=[],
        recommendation="Escalate to manual review because this specialist failed.",
        decision=InspectionDecision.MANUAL_REVIEW,
        overall_confidence=0.0,
        limitations=[error_message],
        status=ReportStatus.FAILED,
        error_message=error_message,
        latency_seconds=latency_seconds,
    )


def _specialist_messages(
    prompt: str,
    reference_data_uri: str,
    inspection_data_uri: str,
    context_text: str,
) -> list[dict[str, Any]]:
    user_text = (
        "Image 1 is the golden reference. Image 2 is the inspected product.\n"
        "Analyze only visible evidence in these images. Return JSON only.\n"
    )
    if context_text:
        user_text += f"\n{context_text}\n"

    return [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": reference_data_uri}},
                {"type": "image_url", "image_url": {"url": inspection_data_uri}},
            ],
        },
    ]


async def _repair_specialist_response(
    client: CerebrasClient,
    agent_name: str,
    bad_content: str,
    validation_error: str,
) -> CerebrasCallResult:
    return await client.chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "You repair JSON for a manufacturing inspection report. "
                    "Return one valid JSON object only. Do not add markdown."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Repair this {agent_name} response so it validates as SpecialistReport. "
                    "Keep only supported content from the original response.\n\n"
                    f"Validation error:\n{validation_error}\n\n"
                    f"Original response:\n{bad_content}"
                ),
            },
        ],
        response_model=SpecialistReport,
    )


async def run_specialist(
    *,
    client: CerebrasClient,
    agent_name: str,
    prompt_name: str,
    reference_data_uri: str,
    inspection_data_uri: str,
    asset_type: str | None = None,
    inspection_stage: str | None = None,
    reported_symptom: str | None = None,
) -> SpecialistReport:
    prompt = load_prompt(prompt_name)
    context_text = build_context_text(asset_type, inspection_stage, reported_symptom)
    result = await client.chat_completion(
        messages=_specialist_messages(
            prompt,
            reference_data_uri,
            inspection_data_uri,
            context_text,
        ),
        response_model=SpecialistReport,
    )
    if not result.success or result.content is None:
        return specialist_failure_report(
            agent_name,
            result.error_message or "API request failed.",
            result.latency_seconds,
        )

    try:
        report = parse_json_model(result.content, SpecialistReport)
    except StructuredOutputError as exc:
        repair = await _repair_specialist_response(
            client,
            agent_name,
            result.content,
            str(exc),
        )
        if not repair.success or repair.content is None:
            return specialist_failure_report(
                agent_name,
                repair.error_message or "Structured-output repair failed.",
                result.latency_seconds + repair.latency_seconds,
            )
        try:
            report = parse_json_model(repair.content, SpecialistReport)
        except StructuredOutputError as repair_exc:
            return specialist_failure_report(
                agent_name,
                f"Response did not validate after one repair attempt: {repair_exc}",
                result.latency_seconds + repair.latency_seconds,
            )
        return report.model_copy(
            update={
                "agent_name": agent_name,
                "status": ReportStatus.COMPLETED,
                "error_message": None,
                "latency_seconds": result.latency_seconds + repair.latency_seconds,
            }
        )

    return report.model_copy(
        update={
            "agent_name": agent_name,
            "status": ReportStatus.COMPLETED,
            "error_message": None,
            "latency_seconds": result.latency_seconds,
        }
    )
