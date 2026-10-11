"""components.rhythm: telling rows apart by line spacing (wrap leading vs row pitch)."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Any

import pytest

from helpers.synth import COL_X, make_page, run
from hwsets.columns.legend import Legend
from hwsets.components.parse import ParsedRows, parse_rows
from hwsets.components.rhythm import Rhythm, estimate_rhythm, opens_block
from hwsets.components.rows import ColumnModel, line_starts_row

WRAP = 11.5
PITCH = 14.5
ROLES6 = ("qty", "unit", "description", "catalog", "finish", "mfr")
MODEL = ColumnModel(xs=COL_X, roles=ROLES6, margins=(0.8,) * 6)
SPACED = dataclasses.replace(MODEL, rhythm=Rhythm(leading=WRAP, pitch=PITCH))
# Quantity printed inside the description cell ("1 Surface Closer"): no quantity column.
X_SHARED = (72.0, 270.0, 450.0, 500.0)
SHARED = ColumnModel(
    xs=X_SHARED,
    roles=("description", "catalog", "finish", "mfr"),
    margins=(0.8,) * 4,
    rhythm=Rhythm(leading=WRAP, pitch=PITCH),
)


def _at(rows: Sequence[tuple[str, float]]) -> list[tuple[str, dict[str, Any]]]:
    """Rows placed by cumulative vertical offsets (pt) from the first row."""
    out: list[tuple[str, dict[str, Any]]] = []
    y = 120.0
    for text, dy in rows:
        y += dy
        out.append((text, {"y": y}))
    return out


def _parse(rows: Sequence[tuple[str, float]], model: ColumnModel = SPACED) -> ParsedRows:
    sp = make_page(1, _at(rows), model.xs)
    return parse_rows(sp.lines(), sp.toks, model, Legend())


def _notes_text(parsed: ParsedRows, rows: Sequence[tuple[str, float]], model: ColumnModel) -> str:
    sp = make_page(1, _at(rows), model.xs)
    text = {t.id: t.text for t in sp.tokens}
    return " ".join(text[i] for i in parsed.set_note_tokens)


def _spaced_table(n_single: int = 6) -> list[tuple[str, float]]:
    """Single-line rows a pitch apart, plus three wrapped rows (wraps a leading apart; the next
    row a pitch below the wrap)."""
    rows: list[tuple[str, float]] = [("1|EA|HINGE|5BB1|652|IVE", 0.0)]
    rows += [(f"1|EA|ITEM {k}|CAT{k}|626|SCH", PITCH) for k in range(n_single)]
    for k in range(3):
        rows += [(f"1|EA|CLOSER {k}|4040XP SERIES|689|LCN", PITCH), ("|||WITH CUSH ARM", WRAP)]
    rows.append(("1|EA|SEAL|188S|BK|ZER", PITCH))
    return rows


TABLE = [
    ("1|EA|HINGE|5BB1 4.5 X 4.5|652|IVE", 0.0),
    ("1|EA|LOCKSET|ND50PD RHO|626|SCH", PITCH),
    ("1|EA|ELECTRIFIED MORTISE LOCK|L9080EU|626|SCH", PITCH),
]


def test_estimate_measures_both_spacings() -> None:
    sp = make_page(1, _at(_spaced_table()), MODEL.xs)
    lines = sp.lines()
    rhythm = estimate_rhythm(
        [lines], sp.toks, MODEL.role_of, lambda ln: line_starts_row(ln, sp.toks, MODEL)
    )
    assert rhythm is not None
    assert rhythm.leading == pytest.approx(WRAP, abs=0.2)
    assert rhythm.pitch == pytest.approx(PITCH, abs=0.2)


def test_no_rhythm_when_wraps_and_rows_share_one_spacing() -> None:
    rows = [("1|EA|HINGE|5BB1|652|IVE", 0.0)]
    for k in range(8):
        rows.append((f"1|EA|ITEM{k}|CAT{k} SERIES|626|SCH", PITCH))
        rows.append(("|||MORE TEXT", PITCH))
    sp = make_page(1, _at(rows), MODEL.xs)
    rhythm = estimate_rhythm(
        [sp.lines()], sp.toks, MODEL.role_of, lambda ln: line_starts_row(ln, sp.toks, MODEL)
    )
    assert rhythm is None


def test_opens_block_ignores_large_holes() -> None:
    rhythm = Rhythm(leading=WRAP, pitch=PITCH)
    sp = make_page(1, _at([("A", 0.0), ("B", PITCH), ("C", WRAP), ("D", 3 * PITCH)]))
    a, b, c, d = sp.lines()
    assert opens_block(a, b, rhythm)
    assert not opens_block(b, c, rhythm)  # a wrap
    assert not opens_block(c, d, rhythm)  # a hole left by removed (struck) lines
    assert not opens_block(a, b, None)


def test_wrapped_line_stays_in_its_cell() -> None:
    parsed = _parse([*TABLE, ("||KEY ON INTERIOR SIDE", WRAP)])
    desc = parsed.components[-1].description.value
    assert desc == "ELECTRIFIED MORTISE LOCK KEY ON INTERIOR SIDE"


def test_remark_a_row_below_is_a_set_note() -> None:
    rows = [*TABLE, ("||Key on lobby side", PITCH)]
    parsed = _parse(rows)
    assert parsed.components[-1].description.value == "ELECTRIFIED MORTISE LOCK"
    assert _notes_text(parsed, rows, SPACED) == "Key on lobby side"


def test_remark_block_keeps_its_own_wrap() -> None:
    rows = [*TABLE, ("|||SEALS PROVIDED WITH", PITCH), ("|||STOREFRONT FRAME", WRAP)]
    parsed = _parse(rows)
    assert parsed.components[-1].catalog_number.value == "L9080EU"
    assert _notes_text(parsed, rows, SPACED) == "SEALS PROVIDED WITH STOREFRONT FRAME"


def test_item_without_quantity_in_its_own_row() -> None:
    parsed = _parse([*TABLE, ("||DIAGRAMS|PROVIDE WIRING DIAGRAMS", PITCH)])
    assert len(parsed.components) == 4
    last = parsed.components[-1]
    assert last.qty.value is None
    assert (last.description.value, last.catalog_number.value) == (
        "DIAGRAMS",
        "PROVIDE WIRING DIAGRAMS",
    )


def test_bullet_continues_the_cell_above() -> None:
    parsed = _parse([*TABLE, ("|||- provide shims", PITCH)])
    assert len(parsed.components) == 3
    assert parsed.components[-1].catalog_number.value == "L9080EU - provide shims"


def test_without_rhythm_the_old_rules_apply() -> None:
    parsed = _parse([*TABLE, ("||KEY ON LOBBY SIDE", PITCH)], model=MODEL)
    assert parsed.components[-1].description.value == "ELECTRIFIED MORTISE LOCK KEY ON LOBBY SIDE"


def test_revision_tag_is_not_a_remark_row() -> None:
    rows = [*TABLE, ("|||[BULLETIN 023,", PITCH), ("|||251218]", WRAP)]
    parsed = _parse(rows)
    # The tag annotates the row above (kept only on revised, bold rows); never a value, never a
    # set remark, and never split in half between the two.
    assert parsed.components[-1].catalog_number.value == "L9080EU"
    assert _notes_text(parsed, rows, SPACED) == ""


def test_centred_quantity_is_the_quantity() -> None:
    rows = [
        ("1 Fail Safe Exit Device|PE8875 ETMI|630|SAR", 0.0),
        ("Surface Closer (Mounted on stairwell", PITCH),
        ("1|7500|689|NOR", WRAP / 2),
        ("side of door)", WRAP / 2),
        ("1 Kick Plate|K1050|630|RO", PITCH),
    ]
    sp = make_page(1, [(t, {**o, "x": 81.0}) if t[0].isalpha() else (t, o)
                       for t, o in _at(rows)], X_SHARED)  # fmt: skip
    parsed = parse_rows(sp.lines(), sp.toks, SHARED, Legend())
    closer = parsed.components[1]
    assert closer.qty.value == 1
    assert closer.description.value == "Surface Closer (Mounted on stairwell side of door)"
    assert closer.catalog_number.value == "7500"


def test_pipeline_reports_rhythm_and_keeps_remarks_out_of_items() -> None:
    rows: list[tuple[str, dict[str, Any]]] = [("HARDWARE SET NO. 1", {"bold": True, "y": 100.0})]
    body = [*_spaced_table(), ("||Hardware by door supplier", PITCH)]
    body[0] = (body[0][0], 20.0)
    y = 100.0
    for text, dy in body:
        y += dy
        rows.append((text, {"y": y}))
    result = run([make_page(1, rows)])
    assert any("rhythm" in k for k in result.column_roles)
    comps = result.sets[0].components
    assert [c.description.value for c in comps][-1] == "SEAL"
    assert "Hardware by door supplier" in (result.sets[0].notes.value or "")
