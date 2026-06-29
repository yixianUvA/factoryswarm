from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from agents import actions, components, quality, verifier, visual
from agents.common import specialist_failure_report
from core.cerebras_client import CerebrasClient, get_cerebras_client
from core.image_utils import ValidatedImage
from core.metrics import build_timing_metrics
from core.schemas import FinalInspectionReport, ReportStatus, SpecialistReport, TimingMetrics


@dataclass(frozen=True)
class WorkflowResult:
    specialist_reports: list[SpecialistReport]
    final_report: FinalInspectionReport
    timing: TimingMetrics


async def _run_agent_safely(
    runner,
    client: CerebrasClient,
    reference_data_uri: str,
    inspection_data_uri: str,
    reference_roi_data_uri: str | None,
    inspection_roi_data_uri: str | None,
    asset_type: str | None,
    inspection_stage: str | None,
    reported_symptom: str | None,
) -> SpecialistReport:
    try:
        return await runner(
            client=client,
            reference_data_uri=reference_data_uri,
            inspection_data_uri=inspection_data_uri,
            reference_roi_data_uri=reference_roi_data_uri,
            inspection_roi_data_uri=inspection_roi_data_uri,
            asset_type=asset_type,
            inspection_stage=inspection_stage,
            reported_symptom=reported_symptom,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        agent_name = getattr(runner, "__module__", "Unknown specialist").split(".")[-1]
        return specialist_failure_report(
            agent_name.replace("_", " ").title(),
            f"Unexpected specialist error: {exc.__class__.__name__}",
            0.0,
        )


async def run_inspection_workflow(
    reference_image: ValidatedImage,
    inspection_image: ValidatedImage,
    reference_roi_image: ValidatedImage | None = None,
    inspection_roi_image: ValidatedImage | None = None,
    asset_type: str | None = None,
    inspection_stage: str | None = None,
    reported_symptom: str | None = None,
    client: CerebrasClient | None = None,
) -> WorkflowResult:
    workflow_start = time.perf_counter()
    active_client = client or get_cerebras_client()
    if (reference_roi_image is None) != (inspection_roi_image is None):
        raise ValueError(
            "Reference ROI and inspection ROI must be provided together as corresponding crops."
        )
    reference_roi_data_uri = (
        reference_roi_image.data_uri if reference_roi_image is not None else None
    )
    inspection_roi_data_uri = (
        inspection_roi_image.data_uri if inspection_roi_image is not None else None
    )

    specialist_runners = [
        visual.run,
        components.run,
        quality.run,
        actions.run,
    ]

    semaphore = asyncio.Semaphore(max(1, active_client.config.max_concurrent_calls))

    async def _limited(runner):
        async with semaphore:
            return await _run_agent_safely(
                runner,
                active_client,
                reference_image.data_uri,
                inspection_image.data_uri,
                reference_roi_data_uri,
                inspection_roi_data_uri,
                asset_type,
                inspection_stage,
                reported_symptom,
            )

    parallel_start = time.perf_counter()
    gathered = await asyncio.gather(
        *[_limited(runner) for runner in specialist_runners],
        return_exceptions=True,
    )
    parallel_latency = time.perf_counter() - parallel_start

    reports: list[SpecialistReport] = []
    for index, item in enumerate(gathered):
        if isinstance(item, SpecialistReport):
            reports.append(item)
        elif isinstance(item, Exception):
            reports.append(
                specialist_failure_report(
                    specialist_runners[index].__module__.split(".")[-1].title(),
                    f"Specialist task failed: {item.__class__.__name__}",
                    0.0,
                )
            )

    failed_agents = [
        report.agent_name
        for report in reports
        if report.status == ReportStatus.FAILED
    ]

    final_report, verifier_latency, verifier_failed = await verifier.run(
        active_client,
        reports,
        failed_agents,
        reference_image.data_uri,
        inspection_image.data_uri,
        reference_roi_data_uri,
        inspection_roi_data_uri,
        asset_type,
        inspection_stage,
        reported_symptom,
    )

    total_latency = time.perf_counter() - workflow_start
    timing = build_timing_metrics(
        reports,
        parallel_latency,
        verifier_latency,
        total_latency,
        verifier_failed=verifier_failed,
    )

    return WorkflowResult(
        specialist_reports=reports,
        final_report=final_report,
        timing=timing,
    )
