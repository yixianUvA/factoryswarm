from __future__ import annotations

from dataclasses import dataclass
import re

from core.schemas import FinalInspectionReport, InspectionDecision, ReportStatus, SpecialistReport


UNSUPPORTED_CLAIM_TERMS = {
    "bom violation",
    "counterfeit",
    "electrical failure",
    "electrically fail",
    "functional failure",
    "internal damage",
    "thermal history",
    "root cause",
}
COMPONENT_CLAIM_TERMS = {
    "missing component",
    "missing passive",
    "missing resistor",
    "missing capacitor",
    "replaced component",
    "different component",
    "different package",
    "different ic package",
    "wrong package",
    "package mismatch",
    "rotated component",
}
OUTLINE_EVIDENCE_TERMS = {"outline", "package outline", "body outline", "footprint"}
PIN_PAD_EVIDENCE_TERMS = {
    "pin count",
    "pad count",
    "pin-count",
    "pad-count",
    "pins",
    "pads",
    "leads",
}
PART_NUMBER_TERMS = {"part number", "marking", "top mark", "silkscreen code"}
CLEARLY_LEGIBLE_TERMS = {"clearly legible", "legible in image", "readable in image"}
LOCATION_TERMS = {
    "central",
    "center",
    "usb",
    "connector",
    "ic",
    "region",
    "around",
    "near",
    "left",
    "right",
    "top",
    "bottom",
    "upper",
    "lower",
    "image 2",
    "inspection image",
}
VISIBLE_FEATURE_TERMS = {
    "visible",
    "dark",
    "discolor",
    "residue",
    "melt",
    "char",
    "burn",
    "contamin",
    "coating",
    "corrosion",
    "surface",
    "mark",
    "material",
    "damage",
}
AMBIGUITY_TERMS = {
    "ambiguous",
    "uncertain",
    "lighting",
    "scale",
    "perspective",
    "focus",
    "legibility",
    "alignment",
    "orientation",
}
SEVERE_VISIBLE_DAMAGE_TERMS = {"burn", "char", "melt", "severe visible damage"}


@dataclass(frozen=True)
class PolicyResult:
    report: FinalInspectionReport
    confidence_cap: float
    notes: list[str]


def _norm(text: str) -> str:
    return text.lower()


def _contains_any(text: str, terms: set[str]) -> bool:
    normalized = _norm(text)
    return any(term in normalized for term in terms)


def _is_localized_visual_statement(text: str) -> bool:
    return _contains_any(text, LOCATION_TERMS) and _contains_any(text, VISIBLE_FEATURE_TERMS)


def _is_exact_part_number_claim(text: str) -> bool:
    normalized = _norm(text)
    if any(term in normalized for term in ("obscur", "illegible", "not legible", "not readable")):
        return False
    if _contains_any(normalized, PART_NUMBER_TERMS):
        return not _contains_any(normalized, CLEARLY_LEGIBLE_TERMS)
    tokens = re.findall(r"\b(?=[a-z0-9]*[a-z])(?=[a-z0-9]*\d)[a-z0-9]{4,}\b", normalized)
    ignored = {"image1", "image2", "image3", "image4"}
    return any(token not in ignored for token in tokens) and not _contains_any(
        normalized,
        CLEARLY_LEGIBLE_TERMS,
    )


def _has_unambiguous_package_evidence(text: str, has_corresponding_roi: bool) -> bool:
    normalized = _norm(text)
    if not has_corresponding_roi:
        return False
    return (
        _contains_any(normalized, COMPONENT_CLAIM_TERMS)
        and _contains_any(normalized, LOCATION_TERMS)
        and _contains_any(normalized, OUTLINE_EVIDENCE_TERMS)
        and _contains_any(normalized, PIN_PAD_EVIDENCE_TERMS)
        and ("image 3" in normalized or "image 4" in normalized or "roi" in normalized or "crop" in normalized)
    )


def _is_unsupported_claim(text: str, has_corresponding_roi: bool) -> bool:
    normalized = _norm(text)
    if _contains_any(normalized, UNSUPPORTED_CLAIM_TERMS):
        return True
    if _contains_any(normalized, COMPONENT_CLAIM_TERMS):
        return not _has_unambiguous_package_evidence(normalized, has_corresponding_roi)
    if _is_exact_part_number_claim(normalized):
        return True
    return False


def _all_report_text(report: FinalInspectionReport, reports: list[SpecialistReport]) -> str:
    parts = [
        report.decision_rationale,
        *report.confirmed_observations,
        *report.hypotheses,
        *report.agreements,
        *report.contradictions,
        *report.unsupported_claims_removed,
    ]
    for specialist in reports:
        parts.extend(
            [
                specialist.summary,
                specialist.recommendation,
                *specialist.limitations,
                *(finding.finding for finding in specialist.findings),
                *(finding.evidence for finding in specialist.findings),
                *(finding.uncertainty for finding in specialist.findings),
            ]
        )
    return "\n".join(parts)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        normalized = item.strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            deduped.append(normalized)
    return deduped


def apply_verifier_policy(
    report: FinalInspectionReport,
    specialist_reports: list[SpecialistReport],
    *,
    has_corresponding_roi: bool,
) -> FinalInspectionReport:
    notes: list[str] = []
    unsupported = list(report.unsupported_claims_removed)
    confirmed: list[str] = []

    for observation in report.confirmed_observations:
        if _is_unsupported_claim(observation, has_corresponding_roi):
            unsupported.append(observation)
            notes.append("Removed unsupported confirmed observation: " + observation)
        else:
            confirmed.append(observation)

    failed_agents = [
        specialist.agent_name
        for specialist in specialist_reports
        if specialist.status == ReportStatus.FAILED
    ]
    localized_evidence = any(_is_localized_visual_statement(item) for item in confirmed)
    all_text = _all_report_text(report, specialist_reports)
    ambiguous_component_comparison = (
        _contains_any(all_text, COMPONENT_CLAIM_TERMS)
        and (
            _contains_any(all_text, AMBIGUITY_TERMS)
            or any(_contains_any(item, COMPONENT_CLAIM_TERMS) for item in unsupported)
        )
    )
    unsupported_claims_present = bool(unsupported)

    caps: list[tuple[float, str]] = []
    if not localized_evidence:
        caps.append((0.65, "no localized visual evidence"))
    if not has_corresponding_roi:
        caps.append((0.75, "full-image comparison without corresponding ROI crops"))
    if report.contradictions:
        caps.append((0.70, "unresolved contradiction"))
    if len(failed_agents) == 1:
        caps.append((0.80, "one failed specialist"))
    elif len(failed_agents) >= 2:
        caps.append((0.65, "two or more failed specialists"))
    if ambiguous_component_comparison:
        caps.append((0.70, "ambiguous component or package comparison"))
    if unsupported_claims_present:
        caps.append((0.70, "unsupported claims removed from final report"))

    confidence_cap = min([1.0, *(cap for cap, _ in caps)])
    confidence = min(max(report.overall_confidence, 0.0), confidence_cap)
    if caps and confidence < report.overall_confidence:
        notes.extend([f"Confidence capped at {cap:.2f}: {reason}." for cap, reason in caps])

    decision = report.decision
    severe_visible_damage = any(
        _contains_any(item, SEVERE_VISIBLE_DAMAGE_TERMS) and _is_localized_visual_statement(item)
        for item in confirmed
    )
    explicit_policy_context = any(
        phrase in _norm(all_text)
        for phrase in (
            "user-supplied policy",
            "explicit policy",
            "specification states",
            "bom context supplied",
            "approved revision supplied",
        )
    )
    if decision == InspectionDecision.REJECT and not (severe_visible_damage or explicit_policy_context):
        decision = InspectionDecision.MANUAL_REVIEW
        notes.append("Downgraded reject to manual_review because reject lacked localized severe visible evidence or explicit policy context.")

    if report.contradictions and decision == InspectionDecision.PASS:
        decision = InspectionDecision.MANUAL_REVIEW
        notes.append("Changed pass to manual_review because unresolved contradictions remain.")

    rationale = report.decision_rationale
    if notes:
        rationale = rationale.rstrip() + " Policy safeguards applied: " + " ".join(notes)

    return report.model_copy(
        update={
            "confirmed_observations": _dedupe(confirmed),
            "unsupported_claims_removed": _dedupe(unsupported),
            "overall_confidence": confidence,
            "decision": decision,
            "human_review_required": report.human_review_required
            or decision == InspectionDecision.MANUAL_REVIEW
            or bool(report.contradictions),
            "decision_rationale": rationale,
            "failed_agents": _dedupe([*report.failed_agents, *failed_agents]),
            "policy_notes": _dedupe(notes),
        }
    )
