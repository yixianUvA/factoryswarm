from __future__ import annotations

from core.schemas import ReportStatus, SpecialistReport, TimingMetrics


def calculate_speedup(
    estimated_sequential_latency: float,
    parallel_stage_latency: float,
) -> float:
    if estimated_sequential_latency <= 0 or parallel_stage_latency <= 0:
        return 0.0
    return estimated_sequential_latency / parallel_stage_latency


def build_timing_metrics(
    reports: list[SpecialistReport],
    parallel_stage_latency: float,
    verifier_latency: float,
    total_workflow_latency: float,
    verifier_failed: bool = False,
) -> TimingMetrics:
    per_agent = {
        report.agent_name: report.latency_seconds or 0.0
        for report in reports
    }
    estimated_sequential = sum(per_agent.values())
    successful_specialists = sum(
        1 for report in reports if report.status == ReportStatus.COMPLETED
    )
    failed_specialists = sum(
        1 for report in reports if report.status == ReportStatus.FAILED
    )

    return TimingMetrics(
        per_agent_latency_seconds=per_agent,
        parallel_stage_latency_seconds=parallel_stage_latency,
        verifier_latency_seconds=verifier_latency,
        total_workflow_latency_seconds=total_workflow_latency,
        estimated_sequential_specialist_latency_seconds=estimated_sequential,
        calculated_parallel_speedup=calculate_speedup(
            estimated_sequential,
            parallel_stage_latency,
        ),
        successful_request_count=successful_specialists + (0 if verifier_failed else 1),
        failed_request_count=failed_specialists + (1 if verifier_failed else 0),
    )
