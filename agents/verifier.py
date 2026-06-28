from __future__ import annotations

import json
from typing import Any

from core.cerebras_client import (
    CerebrasClient,
    StructuredOutputError,
    parse_json_model,
)
from core.prompt_loader import load_prompt
from core.schemas import (
    FinalInspectionReport,
    InspectionDecision,
    ReportStatus,
    Severity,
    SpecialistReport,
)

from agents.common import build_context_text


AGENT_NAME = "Verifier"


def fallback_final_report(
    reports: list[SpecialistReport],
    failed_agents: list[str],
    reason: str,
) -> FinalInspectionReport:
    successful_agents = [
        report.agent_name
        for report in reports
        if report.status == ReportStatus.COMPLETED
    ]
    all_failed = failed_agents + [AGENT_NAME]
    observations = [
        finding.finding
        for report in reports
        if report.status == ReportStatus.COMPLETED
        for finding in report.findings
        if finding.classification == "observation"
    ]
    hypotheses = [
        finding.finding
        for report in reports
        if report.status == ReportStatus.COMPLETED
        for finding in report.findings
        if finding.classification == "hypothesis"
    ]
    return FinalInspectionReport(
        incident_title="Manual review required after verifier failure",
        decision=InspectionDecision.MANUAL_REVIEW,
        severity=Severity.MEDIUM,
        confirmed_observations=observations[:8],
        hypotheses=hypotheses[:8],
        agreements=[],
        contradictions=[],
        unsupported_claims_removed=[
            "Automated consensus was not trusted because the verifier failed."
        ],
        immediate_actions=[
            "Quarantine the item until a qualified human inspector reviews the evidence."
        ],
        follow_up_actions=[
            "Rerun FactorySwarm after confirming API availability and image validity."
        ],
        responsible_role="Quality engineer",
        additional_evidence_required=[
            "Human visual inspection",
            "Any required electrical or dimensional test results",
        ],
        overall_confidence=0.0,
        human_review_required=True,
        decision_rationale=f"Verifier failed to produce a validated report: {reason}",
        successful_agents=successful_agents,
        failed_agents=all_failed,
    )


def _verifier_messages(
    prompt: str,
    reports: list[SpecialistReport],
    failed_agents: list[str],
    reference_data_uri: str,
    inspection_data_uri: str,
    context_text: str,
) -> list[dict[str, Any]]:
    payload = {
        "successful_specialist_reports": [
            report.model_dump(mode="json")
            for report in reports
            if report.status == ReportStatus.COMPLETED
        ],
        "failed_agents": failed_agents,
    }
    user_text = (
        "Image 1 is the golden reference. Image 2 is the inspected product.\n"
        "Arbitrate the specialist reports below. Return JSON only.\n\n"
        f"{json.dumps(payload, indent=2)}"
    )
    if context_text:
        user_text += f"\n\n{context_text}"
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


async def run(
    client: CerebrasClient,
    reports: list[SpecialistReport],
    failed_agents: list[str],
    reference_data_uri: str,
    inspection_data_uri: str,
    asset_type: str | None = None,
    inspection_stage: str | None = None,
    reported_symptom: str | None = None,
) -> tuple[FinalInspectionReport, float, bool]:
    prompt = load_prompt("verifier")
    context_text = build_context_text(asset_type, inspection_stage, reported_symptom)
    result = await client.chat_completion(
        messages=_verifier_messages(
            prompt,
            reports,
            failed_agents,
            reference_data_uri,
            inspection_data_uri,
            context_text,
        ),
        response_model=FinalInspectionReport,
    )
    if not result.success or result.content is None:
        reason = result.error_message or "Verifier API request failed."
        return fallback_final_report(reports, failed_agents, reason), result.latency_seconds, True

    try:
        report = parse_json_model(result.content, FinalInspectionReport)
    except StructuredOutputError as exc:
        repair = await client.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You repair JSON for a final inspection report. "
                        "Return one valid JSON object only."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Repair this response so it validates as FinalInspectionReport. "
                        "Preserve uncertainty and do not invent new visible evidence.\n\n"
                        f"Validation error:\n{exc}\n\nOriginal response:\n{result.content}"
                    ),
                },
            ],
            response_model=FinalInspectionReport,
        )
        total_latency = result.latency_seconds + repair.latency_seconds
        if not repair.success or repair.content is None:
            return (
                fallback_final_report(
                    reports,
                    failed_agents,
                    repair.error_message or "Verifier repair failed.",
                ),
                total_latency,
                True,
            )
        try:
            report = parse_json_model(repair.content, FinalInspectionReport)
        except StructuredOutputError as repair_exc:
            return (
                fallback_final_report(
                    reports,
                    failed_agents,
                    f"Verifier response did not validate after repair: {repair_exc}",
                ),
                total_latency,
                True,
            )
        return report, total_latency, False

    return report, result.latency_seconds, False
