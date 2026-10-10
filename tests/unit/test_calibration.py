"""Isotonic confidence calibration."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from hwsets.calibration import Calibration, FieldMap, apply, fit, isotonic
from hwsets.models import (
    Component,
    DocumentResult,
    Field,
    HardwareSet,
    Location,
    PageRegion,
)


@given(st.lists(st.tuples(st.floats(0, 1), st.booleans()), min_size=1, max_size=300))
def test_isotonic_map_is_monotone_and_bounded(points: list[tuple[float, bool]]) -> None:
    fmap = isotonic(points, min_block=5)
    assert list(fmap.ys) == sorted(fmap.ys)
    assert list(fmap.xs) == sorted(fmap.xs)
    assert all(0.0 <= y <= 1.0 for y in fmap.ys)
    assert fmap.n == len(points)


def test_map_learns_accuracy_by_score() -> None:
    low = [(0.5, i % 2 == 0) for i in range(40)]  # 50% accurate
    high = [(0.9, True) for _ in range(40)]  # 100% accurate
    fmap = isotonic(low + high, min_block=20)
    assert fmap(0.5) == 0.5
    assert fmap(0.9) == 1.0
    assert 0.5 < fmap(0.7) < 1.0  # interpolated between breakpoints
    assert fmap(0.1) == 0.5 and fmap(0.99) == 1.0  # clamped outside the fitted range


def _result(conf: float) -> DocumentResult:
    comp = Component(
        qty=Field[int | str](value=1, token_ids=["p1_w0"], confidence=conf),
        description=Field[str](value="HINGE", token_ids=["p1_w1"], confidence=conf),
        catalog_number=Field[str](value="5BB1", token_ids=["p1_w2"], confidence=conf),
        mfr=Field[str](value="IVE", token_ids=["p1_w3"], confidence=conf, source="human"),
        finish=Field[str](value="652", token_ids=["p1_w4"], confidence=conf),
        notes=Field[str](),
    )
    hs = HardwareSet(
        set_number=Field[str](value="1", token_ids=["p1_w5"], confidence=0.9),
        description=Field[str](),
        location=Location(regions=[PageRegion(page=1, bbox=(0, 0, 10, 10))], line_range=("a", "b")),
        components=[comp],
    )
    return DocumentResult(source_pdf="x.pdf", hardware_pages=[1], column_roles={}, sets=[hs])


def test_apply_maps_rule_fields_and_keeps_human_fields() -> None:
    cal = Calibration(fields={
        "description": FieldMap(xs=(0.5, 1.0), ys=(0.2, 0.6), n=10),
        "mfr": FieldMap(xs=(0.5, 1.0), ys=(0.1, 0.1), n=10),
    })  # fmt: skip
    out = apply(_result(0.75), cal)
    c = out.sets[0].components[0]
    assert c.description.confidence == 0.4  # interpolated
    assert c.mfr.confidence == 0.75  # human-sourced fields are never recalibrated
    assert c.catalog_number.confidence == 0.75  # no map for this field: unchanged


def test_no_calibration_is_identity() -> None:
    r = _result(0.66)
    assert apply(r, None) == r


def test_fit_ignores_unknown_fields() -> None:
    cal = fit({"description": [(0.5, True)] * 3, "bogus": [(0.5, False)]})
    assert set(cal.fields) == {"description"}
