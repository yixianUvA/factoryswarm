from core.metrics import build_timing_metrics, calculate_speedup
from core.schemas import InspectionDecision, ReportStatus, SpecialistReport


def report(name: str, latency: float, status: ReportStatus = ReportStatus.COMPLETED) -> SpecialistReport:
    return SpecialistReport(
        agent_name=name,
        summary="Summary",
        findings=[],
        recommendation="Review",
        decision=InspectionDecision.MANUAL_REVIEW,
        overall_confidence=0.5,
        limitations=[],
        status=status,
        latency_seconds=latency,
    )


def test_speedup_handles_zero_parallel_latency() -> None:
    assert calculate_speedup(10.0, 0.0) == 0.0


def test_timing_metrics_sum_agent_latencies_and_counts() -> None:
    metrics = build_timing_metrics(
        reports=[
            report("A", 1.0),
            report("B", 2.0, ReportStatus.FAILED),
        ],
        parallel_stage_latency=2.0,
        verifier_latency=0.5,
        total_workflow_latency=2.6,
    )

    assert metrics.estimated_sequential_specialist_latency_seconds == 3.0
    assert metrics.calculated_parallel_speedup == 1.5
    assert metrics.successful_request_count == 2
    assert metrics.failed_request_count == 1
