from core.schemas import (
    FinalInspectionReport,
    Finding,
    InspectionDecision,
    ReportStatus,
    Severity,
    SpecialistReport,
)
from core.verifier_policy import apply_verifier_policy


def specialist(
    name: str,
    finding: str,
    evidence: str = "Image appearance is different.",
    status: ReportStatus = ReportStatus.COMPLETED,
) -> SpecialistReport:
    return SpecialistReport(
        agent_name=name,
        summary=finding,
        findings=[
            Finding(
                finding=finding,
                evidence=evidence,
                classification="hypothesis",
                confidence=0.8,
                uncertainty="Whole-image comparison is ambiguous.",
                region=None,
            )
        ]
        if status == ReportStatus.COMPLETED
        else [],
        recommendation="Manual review.",
        decision=InspectionDecision.MANUAL_REVIEW,
        overall_confidence=0.7,
        limitations=[],
        status=status,
        error_message="timeout" if status == ReportStatus.FAILED else None,
        latency_seconds=0.2,
    )


def final_report(
    decision: InspectionDecision = InspectionDecision.REJECT,
    confidence: float = 0.98,
    confirmed: list[str] | None = None,
    hypotheses: list[str] | None = None,
    contradictions: list[str] | None = None,
    failed_agents: list[str] | None = None,
) -> FinalInspectionReport:
    return FinalInspectionReport(
        incident_title="Inspection result",
        decision=decision,
        severity=Severity.HIGH,
        confirmed_observations=confirmed or ["Different IC package."],
        hypotheses=hypotheses or [],
        agreements=[],
        contradictions=contradictions or [],
        unsupported_claims_removed=[],
        immediate_actions=["Quarantine."],
        follow_up_actions=["Inspect."],
        responsible_role="Quality engineer",
        additional_evidence_required=[],
        overall_confidence=confidence,
        human_review_required=True,
        decision_rationale="Model consensus.",
        successful_agents=["A", "B", "C"],
        failed_agents=failed_agents or [],
    )


def test_repeated_unsupported_claims_do_not_become_confirmed_or_reject() -> None:
    reports = [
        specialist("A", "Different IC package"),
        specialist("B", "Different IC package"),
        specialist("C", "Different IC package"),
    ]

    result = apply_verifier_policy(final_report(), reports, has_corresponding_roi=True)

    assert not result.confirmed_observations
    assert any("Different IC package" in item for item in result.unsupported_claims_removed)
    assert result.decision != InspectionDecision.REJECT


def test_ambiguous_package_comparison_caps_confidence_and_manual_review() -> None:
    reports = [
        specialist(
            "A",
            "Possible different package",
            "Text legibility and scale make the package comparison ambiguous.",
        )
    ]

    result = apply_verifier_policy(final_report(), reports, has_corresponding_roi=True)

    assert result.decision == InspectionDecision.MANUAL_REVIEW
    assert result.overall_confidence <= 0.70


def test_invisible_electrical_failure_is_removed_and_cannot_justify_reject() -> None:
    report = final_report(
        confirmed=["The PCB has electrical failure."],
        hypotheses=["Electrical test is needed."],
    )

    result = apply_verifier_policy(report, [specialist("A", "Electrical failure")], has_corresponding_roi=True)

    assert "The PCB has electrical failure." not in result.confirmed_observations
    assert "The PCB has electrical failure." in result.unsupported_claims_removed
    assert result.decision != InspectionDecision.REJECT


def test_full_image_without_roi_caps_confidence() -> None:
    report = final_report(
        decision=InspectionDecision.MANUAL_REVIEW,
        confirmed=["Dark residue is visible around the central IC in Image 2."],
    )

    result = apply_verifier_policy(report, [specialist("A", "Dark residue")], has_corresponding_roi=False)

    assert result.overall_confidence <= 0.75


def test_no_localized_evidence_caps_confidence() -> None:
    report = final_report(
        decision=InspectionDecision.MANUAL_REVIEW,
        confirmed=["The boards look different."],
    )

    result = apply_verifier_policy(report, [specialist("A", "Boards differ")], has_corresponding_roi=True)

    assert result.overall_confidence <= 0.65


def test_contradiction_penalty_lowers_confidence() -> None:
    report = final_report(
        decision=InspectionDecision.REJECT,
        confirmed=["Dark residue is visible around the central IC in Image 2."],
        contradictions=["One agent reports a missing component while another says layout is consistent."],
    )

    result = apply_verifier_policy(report, [specialist("A", "Missing component")], has_corresponding_roi=True)

    assert result.contradictions
    assert result.overall_confidence <= 0.70
    assert result.decision == InspectionDecision.MANUAL_REVIEW


def test_one_failed_specialist_caps_confidence() -> None:
    report = final_report(
        decision=InspectionDecision.MANUAL_REVIEW,
        confidence=0.95,
        confirmed=["Dark residue is visible around the central IC in Image 2."],
        failed_agents=["B"],
    )
    reports = [
        specialist("A", "Dark residue"),
        specialist("B", "Failed", status=ReportStatus.FAILED),
        specialist("C", "Dark residue"),
        specialist("D", "Dark residue"),
    ]

    result = apply_verifier_policy(report, reports, has_corresponding_roi=True)

    assert "B" in result.failed_agents
    assert result.overall_confidence <= 0.80


def test_exact_part_number_claim_requires_clear_legibility() -> None:
    report = final_report(
        decision=InspectionDecision.MANUAL_REVIEW,
        confirmed=["The IC marking is 4056E SN2N1P."],
    )

    result = apply_verifier_policy(report, [specialist("A", "IC marking")], has_corresponding_roi=True)

    assert "The IC marking is 4056E SN2N1P." not in result.confirmed_observations
    assert "The IC marking is 4056E SN2N1P." in result.unsupported_claims_removed


def test_pcb_fixture_keeps_primary_material_observation_and_blocks_package_claim() -> None:
    report = final_report(
        decision=InspectionDecision.REJECT,
        confidence=0.98,
        confirmed=[
            "Dark material is visible around the central IC in Image 4 ROI.",
            "Additional surface discoloration is visible near the USB connector in Image 2.",
            "Different IC package.",
            "BOM violation.",
        ],
        hypotheses=[
            "Residue, contamination, coating disturbance, localized overheating, or rework-related damage.",
            "The central package and surrounding layout appear broadly consistent at this resolution.",
        ],
    )
    reports = [
        specialist(
            "Visual Difference Inspector",
            "Dark material around the central IC",
            "Dark material is visible around the central IC in Image 4 ROI.",
        ),
        specialist("Component and Layout Inspector", "Different IC package"),
        specialist("Quality and Risk Assessor", "BOM violation"),
        specialist("Factory Action Planner", "Manual optical review"),
    ]

    result = apply_verifier_policy(report, reports, has_corresponding_roi=True)

    confirmed_text = " ".join(result.confirmed_observations).lower()
    assert result.decision == InspectionDecision.MANUAL_REVIEW
    assert result.overall_confidence <= 0.70
    assert "dark material" in confirmed_text
    assert "usb connector" in confirmed_text
    assert "different ic package" not in confirmed_text
    assert "bom violation" not in confirmed_text
    assert any("Different IC package" in item for item in result.unsupported_claims_removed)


def test_obscured_markings_observation_is_not_treated_as_part_number_claim() -> None:
    report = final_report(
        decision=InspectionDecision.REJECT,
        confidence=0.95,
        confirmed=[
            "Thick, dark residue is visible around the central IC in Image 4 ROI, obscuring package markings.",
        ],
    )

    result = apply_verifier_policy(report, [specialist("A", "Dark residue")], has_corresponding_roi=True)

    assert result.confirmed_observations == [
        "Thick, dark residue is visible around the central IC in Image 4 ROI, obscuring package markings."
    ]
    assert not result.unsupported_claims_removed
    assert result.decision == InspectionDecision.MANUAL_REVIEW
