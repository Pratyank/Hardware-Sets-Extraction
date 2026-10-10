"""validate: invariants become warnings and lower confidence; nothing raises."""

from __future__ import annotations

from typing import Literal

import pytest

from helpers.synth import tok
from hwsets.models import (
    Component,
    DocumentResult,
    Field,
    HardwareSet,
    Location,
    PageRegion,
    Token,
)
from hwsets.validate import validate_document

TOKS: dict[str, Token] = {
    t.id: t
    for t in [
        tok("p1_w0", "3", (72, 100, 76, 109)),
        tok("p1_w1", "HINGE", (140, 100, 162, 109)),
        tok("p1_w2", "5BB1", (270, 100, 288, 109)),
        tok("p1_w3", "652", (450, 100, 463, 109)),
        tok("p1_w4", "IVE", (500, 100, 513, 109)),
        tok("p2_w0", "LCN", (500, 100, 513, 109), page=2),
    ]
}


def _f(value: str | None, *ids: str, conf: float = 0.9) -> Field[str]:
    return Field[str](value=value, token_ids=list(ids), confidence=conf)


def _component(**over: Field[str]) -> Component:
    fields = {
        "description": _f("HINGE", "p1_w1"),
        "catalog_number": _f("5BB1", "p1_w2"),
        "mfr": _f("IVE", "p1_w4"),
        "finish": _f("652", "p1_w3"),
        "notes": _f(None),
    }
    fields.update(over)
    return Component(qty=Field[int | str](value=3, token_ids=["p1_w0"], confidence=0.95), **fields)


def _set(
    number: str,
    components: list[Component],
    status: Literal["active", "not_used"] = "active",
    confidence: float = 0.8,
) -> HardwareSet:
    return HardwareSet(
        set_number=Field[str](value=number, token_ids=[], confidence=0.95),
        description=_f(None),
        status=status,
        location=Location(
            regions=[PageRegion(page=1, bbox=(72, 90, 513, 109))], line_range=("L1_0", "L1_1")
        ),
        components=components,
        confidence=confidence,
    )


def _doc(*sets: HardwareSet) -> DocumentResult:
    return DocumentResult(source_pdf="x.pdf", hardware_pages=[1], column_roles={}, sets=list(sets))


def test_clean_document_has_no_warnings() -> None:
    out = validate_document(_doc(_set("1", [_component()])), TOKS)
    assert out.warnings == []
    assert out.sets[0].components[0].description.confidence == 0.9
    assert out.sets[0].confidence == pytest.approx((0.95 + 0.9 * 4) / 5, abs=1e-3)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        (_f("HINGE BUTT", "p1_w1"), "value text differs from its tokens"),
        (_f("HINGE"), "value without tokens"),
        (_f("HINGE", "p9_w9"), "unknown tokens"),
        (_f("LCN", "p2_w0"), "token outside the set's pages"),
    ],
)
def test_grounding_violations_warn_and_lower_confidence(field: Field[str], message: str) -> None:
    doc = _doc(_set("1", [_component(description=field)]))
    out = validate_document(doc, TOKS)
    assert any("set 1 component 1: description" in w and message in w for w in out.warnings)
    assert out.sets[0].components[0].description.confidence == pytest.approx(0.45)
    # Validation never mutates its input.
    assert doc.sets[0].components[0].description.confidence == 0.9


def test_normalization_differences_are_not_violations() -> None:
    out = validate_document(_doc(_set("1", [_component(description=_f("hinge.", "p1_w1"))])), TOKS)
    assert out.warnings == []


def test_duplicate_set_numbers_are_flagged_not_merged() -> None:
    out = validate_document(_doc(_set("1", [_component()]), _set("1", [_component()])), TOKS)
    assert len(out.sets) == 2
    dup = [w for w in out.warnings if "duplicate set number" in w]
    assert len(dup) == 2
    assert all(s.set_number.confidence == pytest.approx(0.76) for s in out.sets)


def test_not_used_set_with_components_has_them_dropped() -> None:
    out = validate_document(_doc(_set("2", [_component()], status="not_used")), TOKS)
    assert out.sets[0].components == []
    assert any("NOT USED set has components; dropped" in w for w in out.warnings)


def test_active_set_without_components_is_flagged() -> None:
    out = validate_document(_doc(_set("3", [], confidence=0.9)), TOKS)
    assert any("active set has no components" in w for w in out.warnings)
    assert out.sets[0].confidence == 0.5


def test_qty_without_tokens_is_flagged() -> None:
    comp = _component()
    comp.qty = Field[int | str](value=3, token_ids=[], confidence=0.95)
    out = validate_document(_doc(_set("1", [comp])), TOKS)
    assert any("qty without tokens" in w for w in out.warnings)
    assert out.sets[0].components[0].qty.confidence == pytest.approx(0.475)


def test_non_integer_qty_is_flagged() -> None:
    comp = _component()
    comp.qty = Field[int | str](value="3", token_ids=["p1_w0"], confidence=0.95)
    out = validate_document(_doc(_set("1", [comp])), TOKS)
    assert any("qty is not an integer" in w for w in out.warnings)


def test_violation_lowers_set_confidence() -> None:
    good = validate_document(_doc(_set("1", [_component()])), TOKS).sets[0].confidence
    bad_comp = _component(mfr=_f("SCHLAGE", "p1_w4"))
    bad = validate_document(_doc(_set("1", [bad_comp])), TOKS).sets[0].confidence
    assert bad < good
