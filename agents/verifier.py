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
from core.verifier_policy import apply_verifier_policy

from agents.common import build_context_text


AGENT_NAME = "Verifier"

_VERIFIER_JSON_HINT = """
Output a JSON object with EXACTLY these field names — no other keys are permitted:
{
  "incident_title": "string",
  "decision": "pass OR manual_review OR rework OR reject",
  "severity": "none OR low OR medium OR high OR critical",
  "confirmed_observations": [],
  "hypotheses": [],
  "agreements": [],
  "contradictions": [],
  "unsupported_claims_removed": [],
  "immediate_actions": [],
  "follow_up_actions": [],
  "responsible_role": "string",
  "additional_evidence_required": [],
  "overall_confidence": 0.0,
  "human_review_required": true,
  "decision_rationale": "string",
  "successful_agents": [],
  "failed_agents": [],
  "policy_notes": []
}"""


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
    reference_roi_data_uri: str | None,
    inspection_roi_data_uri: str | None,
    context_text: str,
) -> list[dict[str, Any]]:
    has_roi = reference_roi_data_uri is not None and inspection_roi_data_uri is not None
    payload = {
        "successful_specialist_reports": [
            report.model_dump(mode="json")
            for report in reports
            if report.status == ReportStatus.COMPLETED
        ],
        "failed_agents": failed_agents,
    }
    user_text = (
        "Image 1: complete golden-reference product.\n"
        "Image 2: complete inspected product.\n"
        "Arbitrate the specialist reports below. Return JSON only.\n\n"
        f"{json.dumps(payload, indent=2)}"
    )
    if has_roi:
        user_text = (
            "Image 1: complete golden-reference product.\n"
            "Image 2: complete inspected product.\n"
            "Image 3: golden-reference crop of the suspicious region.\n"
            "Image 4: corresponding inspection crop of the same physical region.\n"
            "Use full images for global layout context and crops for local evidence. "
            "ROI localization is an inspection aid, not proof of a defect.\n\n"
            f"{json.dumps(payload, indent=2)}"
        )
    if context_text:
        user_text += f"\n\n{context_text}"
    content: list[dict[str, Any]] = [
        {"type": "text", "text": user_text},
        {"type": "text", "text": "Image 1: complete golden-reference product."},
        {"type": "image_url", "image_url": {"url": reference_data_uri}},
        {"type": "text", "text": "Image 2: complete inspected product."},
        {"type": "image_url", "image_url": {"url": inspection_data_uri}},
    ]
    if has_roi:
        content.extend(
            [
                {
                    "type": "text",
                    "text": "Image 3: golden-reference crop of the suspicious region.",
                },
                {"type": "image_url", "image_url": {"url": reference_roi_data_uri}},
                {
                    "type": "text",
                    "text": "Image 4: corresponding inspection crop of the same physical region.",
                },
                {"type": "image_url", "image_url": {"url": inspection_roi_data_uri}},
            ]
        )
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": content},
    ]


async def run(
    client: CerebrasClient,
    reports: list[SpecialistReport],
    failed_agents: list[str],
    reference_data_uri: str,
    inspection_data_uri: str,
    reference_roi_data_uri: str | None = None,
    inspection_roi_data_uri: str | None = None,
    asset_type: str | None = None,
    inspection_stage: str | None = None,
    reported_symptom: str | None = None,
) -> tuple[FinalInspectionReport, float, bool]:
    prompt = load_prompt("verifier")
    if not client.config.use_json_schema:
        prompt = prompt + _VERIFIER_JSON_HINT
    context_text = build_context_text(asset_type, inspection_stage, reported_symptom)
    result = await client.chat_completion(
        messages=_verifier_messages(
            prompt,
            reports,
            failed_agents,
            reference_data_uri,
            inspection_data_uri,
            reference_roi_data_uri,
            inspection_roi_data_uri,
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
                        "Return one valid JSON object only. Do not add markdown."
                        + (_VERIFIER_JSON_HINT if not client.config.use_json_schema else "")
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
        return (
            apply_verifier_policy(
                report,
                reports,
                has_corresponding_roi=reference_roi_data_uri is not None
                and inspection_roi_data_uri is not None,
            ),
            total_latency,
            False,
        )

    return (
        apply_verifier_policy(
            report,
            reports,
            has_corresponding_roi=reference_roi_data_uri is not None
            and inspection_roi_data_uri is not None,
        ),
        result.latency_seconds,
        False,
    )
