"""components.parse: rows -> components, under known column roles."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from helpers.synth import COL_X, make_page
from hwsets.columns.legend import Legend, LegendEntry
from hwsets.components.parse import ParsedRows, parse_rows
from hwsets.components.rows import ColumnModel

ROLES6 = ("qty", "unit", "description", "catalog", "finish", "mfr")
MODEL = ColumnModel(xs=COL_X, roles=ROLES6, margins=(0.8,) * 6)
# qty, description, catalog, finish: no manufacturer column
X4 = (72.0, 110.0, 260.0, 460.0)
MODEL_NO_MFR = ColumnModel(xs=X4, roles=("qty", "description", "catalog", "finish"),
                           margins=(0.8,) * 4)  # fmt: skip


def _parse(
    rows: Sequence[str | tuple[str, dict[str, Any]]],
    model: ColumnModel = MODEL,
    legend: Legend | None = None,
) -> tuple[ParsedRows, dict[str, str]]:
    sp = make_page(1, rows, model.xs)
    parsed = parse_rows(sp.lines(), sp.toks, model, legend or Legend())
    return parsed, {t.id: t.text for t in sp.tokens}


def _words(ids: Sequence[str], text: dict[str, str]) -> str:
    return " ".join(text[i] for i in ids)


def test_one_row_per_quantity_line() -> None:
    parsed, _ = _parse(["3|EA|HINGE|5BB1 4.5 X 4.5|652|IVE", "1|EA|LOCKSET|ND50PD RHO|626|SCH"])
    assert len(parsed.components) == 2
    c = parsed.components[0]
    assert (c.qty.value, c.qty_unit) == (3, "EA")
    assert c.description.value == "HINGE"
    assert c.catalog_number.value == "5BB1 4.5 X 4.5"
    assert (c.finish.value, c.mfr.value, c.mfr_resolved) == ("652", "IVE", "Ives")
    assert parsed.set_note_tokens == []


def test_wrapped_continuation_merges_into_row_above() -> None:
    parsed, _ = _parse(
        [
            '1|EA|CONTINUOUS|224XY 83"|628|IVE',
            "||HINGE|EPT PREP",
            "1|EA|CLOSER|4040XP|689|LCN",
        ]
    )
    assert len(parsed.components) == 2
    hinge = parsed.components[0]
    assert hinge.description.value == "CONTINUOUS HINGE"
    assert hinge.catalog_number.value == '224XY 83" EPT PREP'
    assert parsed.components[1].description.value == "CLOSER"


def test_wrapped_hyphenated_finish_is_glued() -> None:
    parsed, _ = _parse(["1|EA|PUSH PLATE|8200 4 X 16|630-|IVE", "||||316"])
    (c,) = parsed.components
    assert c.finish.value == "630-316"
    assert len(c.finish.token_ids) == 2


def test_note_sub_lines_attach_to_the_component_above() -> None:
    parsed, text = _parse(
        [
            "1|EA|LOCKSET|ND50PD RHO|626|SCH",
            ("Note: provide with construction core", {"x": 152}),
            ("Properties: fire rated", {"x": 152}),
            "1|EA|CLOSER|4040XP|689|LCN",
        ]
    )
    lock, closer = parsed.components
    assert lock.notes.value == "Note: provide with construction core Properties: fire rated"
    assert _words(lock.notes.token_ids, text) == lock.notes.value
    assert closer.notes.value is None
    assert parsed.set_note_tokens == []


def test_notes_aligned_with_the_description_column_are_set_notes() -> None:
    """Only a note indented under an item belongs to it; one aligned with the description
    column is about the whole set (gold convention, see DECISIONS.md)."""
    parsed, text = _parse(
        [
            "1|EA|LOCKSET|ND50PD RHO|626|SCH",
            ("NOTE: FURNISH SEALS AT RATED DOORS", {"x": 140}),
        ]
    )
    (lock,) = parsed.components
    assert lock.notes.value is None
    assert _words(parsed.set_note_tokens, text) == "NOTE: FURNISH SEALS AT RATED DOORS"


def test_numbered_notes_are_set_notes() -> None:
    parsed, text = _parse(
        [
            "1|EA|LOCKSET|ND50PD RHO|626|SCH",
            ("Note: 1. Door contacts by security contractor", {"x": 140}),
        ]
    )
    (lock,) = parsed.components
    assert lock.notes.value is None
    assert _words(parsed.set_note_tokens, text) == "Note: 1. Door contacts by security contractor"


def test_prose_lines_go_to_set_notes() -> None:
    parsed, text = _parse(
        [
            ("Balance of hardware to be furnished by the door supplier", {"x": 40}),
            "3|EA|HINGE|5BB1 4.5 X 4.5|652|IVE",
        ]
    )
    assert len(parsed.components) == 1
    assert _words(parsed.set_note_tokens, text).startswith("Balance of hardware")


def test_decimal_quantity_is_an_integer() -> None:
    parsed, _ = _parse(["3.0|EA|HINGE|5BB1|652|IVE"])
    assert parsed.components[0].qty.value == 3


def test_quantity_with_unit_in_one_cell() -> None:
    parsed, text = _parse(["1 Ea.||LOCKSET|ND50PD RHO|626|SCH"])
    (c,) = parsed.components
    assert (c.qty.value, c.qty_unit) == (1, "EA")
    assert _words(c.qty.token_ids, text) == "1"


def test_as_required_quantity_is_null() -> None:
    parsed, _ = _parse(["As Req||SILENCER|SR64|GRY|IVE"])
    (c,) = parsed.components
    assert (c.qty.value, c.qty_unit) == (None, None)
    assert c.qty.token_ids == []
    assert c.description.value == "SILENCER"


def test_missing_quantity_is_null_never_one() -> None:
    parsed, _ = _parse(["3|EA|HINGE|5BB1 4.5 X 4.5|652|IVE", "||SILENCER|SR64|GRY|IVE"])
    assert len(parsed.components) == 2
    silencer = parsed.components[1]
    assert silencer.qty.value is None
    assert silencer.qty_unit is None
    assert silencer.description.value == "SILENCER"


def test_unit_without_number() -> None:
    parsed, _ = _parse(["3|EA|HINGE|5BB1|652|IVE", "|PR|FLUSH BOLT|FB458|626|IVE"])
    bolt = parsed.components[1]
    assert (bolt.qty.value, bolt.qty_unit) == (None, "PR")


def test_merged_manufacturer_and_catalog_split_without_mfr_column() -> None:
    parsed, text = _parse(["3|HINGES|IVES \u2013 5BB1 4.5 x 4.5|652"], MODEL_NO_MFR)
    (c,) = parsed.components
    assert c.mfr.value == "IVES"
    assert c.mfr_resolved == "Ives"
    assert c.catalog_number.value == "5BB1 4.5 x 4.5"
    assert "\u2013" not in _words(c.catalog_number.token_ids, text)  # separator dropped
    assert c.finish.value == "652"


def test_merged_manufacturer_split_with_ascii_hyphen_token() -> None:
    parsed, _ = _parse(["3|HINGES|IVES - 5BB1 4.5 x 4.5|652"], MODEL_NO_MFR)
    (c,) = parsed.components
    assert (c.mfr.value, c.catalog_number.value) == ("IVES", "5BB1 4.5 x 4.5")


def test_standalone_hyphen_token_keeps_its_spacing() -> None:
    parsed, _ = _parse(["1|PLATE|KICK - 8400 10 x 34|630"], MODEL_NO_MFR)
    assert parsed.components[0].catalog_number.value == "KICK - 8400 10 x 34"


def test_merged_split_needs_a_known_manufacturer() -> None:
    parsed, _ = _parse(["1|PLATE|KICK \u2013 8400 10 x 34|630"], MODEL_NO_MFR)
    (c,) = parsed.components
    assert c.mfr.value is None
    assert c.catalog_number.value == "KICK \u2013 8400 10 x 34"


def test_merged_split_accepts_legend_codes() -> None:
    legend = Legend(mfr={"ZZX": LegendEntry("ZZX", "Acme Widgets", "mfr", ())})
    parsed, _ = _parse(["1|WIDGET|ZZX \u2013 W100|630"], MODEL_NO_MFR, legend)
    (c,) = parsed.components
    assert (c.mfr.value, c.mfr_resolved) == ("ZZX", "Acme Widgets")
    assert c.catalog_number.value == "W100"


def test_note_rows_become_set_notes() -> None:
    parsed, text = _parse(["3|EA|HINGE|5BB1|652|IVE", "1||NOTE|BALANCE OF HARDWARE BY DOOR MFR"])
    assert len(parsed.components) == 1
    assert _words(parsed.set_note_tokens, text) == "1 NOTE BALANCE OF HARDWARE BY DOOR MFR"


def test_description_and_catalog_split_when_one_column_holds_both() -> None:
    model = ColumnModel(xs=(72.0, 110.0, 460.0), roles=("qty", "description", "mfr"),
                        margins=(0.8,) * 3, split_merged=True)  # fmt: skip
    parsed, _ = _parse(["1|DOOR CLOSER 4040XP REG ARM|LCN"], model)
    (c,) = parsed.components
    assert c.description.value == "DOOR CLOSER"
    assert c.catalog_number.value == "4040XP REG ARM"


def test_legend_resolves_collision_code_with_higher_confidence() -> None:
    legend = Legend(mfr={"PE": LegendEntry("PE", "Pemko Mfg.", "mfr", ())})
    weak = ColumnModel(xs=COL_X, roles=ROLES6, margins=(0.1,) * 6)  # keep below the 1.0 cap
    plain, _ = _parse(["1|EA|THRESHOLD|171A|AL|PE"], weak)
    with_legend, _ = _parse(["1|EA|THRESHOLD|171A|AL|PE"], weak, legend)
    assert plain.components[0].mfr_resolved == "Pemko"
    assert with_legend.components[0].mfr_resolved == "Pemko Mfg."
    assert with_legend.components[0].mfr.confidence > plain.components[0].mfr.confidence


def test_finish_code_in_manufacturer_column_warns() -> None:
    parsed, _ = _parse(["1|EA|STOP|WS406|630|626"])
    assert any("finish-like code" in w for w in parsed.warnings)


# qty, description, catalog, finish, notes: a table with its own notes column
X_NOTES = (72.0, 110.0, 230.0, 380.0, 430.0)
MODEL_NOTES = ColumnModel(xs=X_NOTES, roles=("qty", "description", "catalog", "finish", "notes"),
                          margins=(0.8,) * 5)  # fmt: skip


def test_notes_column_remark_after_a_row_without_a_note_is_a_set_note() -> None:
    parsed, text = _parse(
        [
            "1|PIVOT HINGE|CLEAR VIEW|613|FULL HEIGHT STYLE",
            "1|FLOOR STOP|446|613",
            "||||COORDINATE W/ ENTRANCE MFR.",
        ],
        model=MODEL_NOTES,
    )
    assert [c.notes.value for c in parsed.components] == ["FULL HEIGHT STYLE", None]
    assert _words(parsed.set_note_tokens, text) == "COORDINATE W/ ENTRANCE MFR."


def test_wrapped_note_continues_the_row_note() -> None:
    parsed, _ = _parse(
        [
            "1|MORTISE LOCK|L9092EU|613|ELECTRIC UNLOCKING; COORDINATE W/",
            "||||SECURITY VENDOR",
        ],
        model=MODEL_NOTES,
    )
    assert parsed.components[0].notes.value == "ELECTRIC UNLOCKING; COORDINATE W/ SECURITY VENDOR"
    assert parsed.set_note_tokens == []
