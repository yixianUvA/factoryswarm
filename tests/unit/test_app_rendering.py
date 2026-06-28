from app import display_items
from core.schemas import Finding


def test_display_items_returns_individual_items_not_python_list_repr() -> None:
    items = display_items(["finding one", "finding two"])

    assert items == ["finding one", "finding two"]
    assert str(items) not in items


def test_display_items_formats_findings_individually() -> None:
    finding = Finding(
        finding="Dark residue",
        evidence="Visible around the central IC.",
        classification="observation",
        confidence=0.8,
        uncertainty="Material composition unknown.",
        region="central IC",
    )

    assert display_items([finding]) == [
        "Dark residue (central IC): Visible around the central IC."
    ]
