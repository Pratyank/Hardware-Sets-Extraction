"""segment.sets: stream -> spans, and line classification inside a span."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from helpers.synth import make_page
from hwsets.models import Line, Token
from hwsets.segment.headers import HeaderParse, parse_header
from hwsets.segment.sets import Kind, Span, classify, is_door_list, split_spans

H: dict[str, Any] = {"bold": True}


def _stream(
    rows: Sequence[str | tuple[str, dict[str, Any]]], page: int = 1
) -> tuple[list[Line], dict[str, Token], dict[str, HeaderParse]]:
    sp = make_page(page, rows)
    lines = sp.lines()
    headers = {ln.id: h for ln in lines if (h := parse_header(ln, sp.toks)) is not None}
    return lines, sp.toks, headers


def _kinds(rows: Sequence[str | tuple[str, dict[str, Any]]]) -> list[tuple[str, Kind]]:
    lines, toks, headers = _stream(rows)
    (span,) = split_spans(lines, headers)
    return list(zip([ln.text for ln in span.lines], classify(span, toks), strict=True))


def test_split_at_headers_and_skip_preamble() -> None:
    lines, _, headers = _stream(
        [
            "Preamble text before the first set",
            ("HARDWARE SET NO. 1", H),
            "3|EA|HINGE|5BB1|652|IVE",
            ("HARDWARE SET NO. 2", H),
            "1|EA|CLOSER|4040XP|689|LCN",
        ]
    )
    spans = split_spans(lines, headers)
    assert [s.set_id for s in spans] == ["1", "2"]
    assert [len(s.lines) for s in spans] == [2, 2]
    assert spans[0].lines[0].text == "HARDWARE SET NO. 1"


def test_multi_id_header_yields_one_span_per_id_sharing_lines() -> None:
    lines, toks, headers = _stream(
        [("Hardware Group/Set #B1 and #B2 \u2013 Bedrooms", H), "3|EA|HINGE|5BB1|652|IVE"]
    )
    spans = split_spans(lines, headers)
    assert [s.set_id for s in spans] == ["B1", "B2"]
    assert spans[0].lines == spans[1].lines
    assert [toks[i].text for i in spans[0].id_token_ids] == ["#B1"]
    assert [toks[i].text for i in spans[1].id_token_ids] == ["#B2"]


def test_end_of_section_terminates_the_last_span() -> None:
    lines, _, headers = _stream(
        [("HARDWARE SET NO. 1", H), "3|EA|HINGE|5BB1|652|IVE", "END OF SECTION", "Trailing text"]
    )
    (span,) = split_spans(lines, headers)
    assert span.terminated_by == "END OF SECTION"
    assert [ln.text for ln in span.lines] == ["HARDWARE SET NO. 1", "3 EA HINGE 5BB1 652 IVE"]


def test_page_break_is_not_a_boundary() -> None:
    a = make_page(1, [("HARDWARE SET NO. 1", H), "3|EA|HINGE|5BB1|652|IVE"])
    b = make_page(2, ["1|EA|CLOSER|4040XP|689|LCN"])
    lines = a.lines() + b.lines()
    toks = {**a.toks, **b.toks}
    headers = {ln.id: h for ln in lines if (h := parse_header(ln, toks)) is not None}
    (span,) = split_spans(lines, headers)
    assert [ln.page for ln in span.lines] == [1, 1, 2]


def test_classify_set_level_lines() -> None:
    kinds = _kinds(
        [
            ("HARDWARE SET NO. 1", H),
            "ENTRANCE DOORS",
            "Doors: 101, 102, 103",
            "Provide each pair with the following:",
            "QTY|UNIT|DESCRIPTION|CATALOG NUMBER|FINISH|MFR",
            "3|EA|HINGE|5BB1|652|IVE",
            "Operation: door is normally closed and latched",
        ]
    )
    assert [k for _, k in kinds] == [
        Kind.HEADER,
        Kind.DESCRIPTION,
        Kind.SET_LEVEL,
        Kind.SET_LEVEL,
        Kind.COLUMN_HEADER,
        Kind.ROW,
        Kind.SET_LEVEL,
    ]


def test_bare_door_number_list_before_rows_is_set_level() -> None:
    kinds = _kinds([("HARDWARE SET NO. 1", H), "101A, 102, 103 & 104", "3|EA|HINGE|5BB1|652|IVE"])
    assert [k for _, k in kinds] == [Kind.HEADER, Kind.SET_LEVEL, Kind.ROW]


def test_is_door_list() -> None:
    lines, toks, _ = _stream(["101, 102 thru 110", "3 EA HINGE 5BB1 652 IVE", "Doors and frames"])
    assert [is_door_list(ln, toks) for ln in lines] == [True, False, False]


def test_not_used_on_first_line_after_header() -> None:
    kinds = _kinds([("HARDWARE SET NO. 3", H), "NOT USED"])
    assert kinds[1] == ("NOT USED", Kind.NOT_USED)


def test_not_used_after_description_line() -> None:
    kinds = _kinds([("HARDWARE SET NO. 3", H), "STAIR DOORS", "(N/A)"])
    assert [k for _, k in kinds] == [Kind.HEADER, Kind.DESCRIPTION, Kind.NOT_USED]


def test_na_deep_inside_a_set_is_not_a_not_used_marker() -> None:
    kinds = _kinds(
        [
            ("HARDWARE SET NO. 4", H),
            "3|EA|HINGE|5BB1|652|IVE",
            "1|EA|CLOSER|4040XP|689|LCN",
            ("N/A", {"x": 140}),
        ]
    )
    assert Kind.NOT_USED not in [k for _, k in kinds]


def test_notes_before_rows_are_set_level_after_rows_are_row_notes() -> None:
    kinds = _kinds(
        [
            ("HARDWARE SET NO. 1", H),
            "Notes: all doors to be keyed alike",
            "3|EA|HINGE|5BB1|652|IVE",
            "Note: hinges to be non-removable pin",
        ]
    )
    assert [k for _, k in kinds] == [Kind.HEADER, Kind.SET_LEVEL, Kind.ROW, Kind.ROW]


def test_description_label_line() -> None:
    kinds = _kinds([("HARDWARE SET NO. 1", H), "Description: Office", "3|EA|HINGE|5BB1|652|IVE"])
    assert kinds[1] == ("Description: Office", Kind.DESCRIPTION)


def test_span_kinds_are_stored() -> None:
    lines, toks, headers = _stream([("HARDWARE SET NO. 1", H), "3|EA|HINGE|5BB1|652|IVE"])
    span: Span = split_spans(lines, headers)[0]
    classify(span, toks)
    assert span.kinds == [Kind.HEADER, Kind.ROW]


# ---------------------------------------------------------------------------
# Known bugs (xfail, strict): description-first layouts.
# ---------------------------------------------------------------------------

_DESC_FIRST = (60.0, 150.0, 240.0, 340.0, 450.0, 530.0)  # description, qty, unit, cat, fin, mfr


@pytest.mark.xfail(
    strict=True,
    reason="BUG: sets._SET_LEVEL_RE matches '^doors?\\b' on the line text, so in a layout whose "
    "first column is the description, a 'DOOR SWEEP' / 'DOOR CLOSER' row becomes set-level text",
)
def test_door_item_row_in_description_first_layout_is_a_row() -> None:
    sp = make_page(
        1,
        [
            ("HARDWARE SET NO. 1", H),
            "HINGE|3|EA|5BB1 4.5 X 4.5|652|IVE",
            "DOOR SWEEP|1|EA|315CN|626|IVE",
        ],
        _DESC_FIRST,
    )
    lines = sp.lines()
    headers = {ln.id: h for ln in lines if (h := parse_header(ln, sp.toks)) is not None}
    (span,) = split_spans(lines, headers)
    assert classify(span, sp.toks) == [Kind.HEADER, Kind.ROW, Kind.ROW]


@pytest.mark.xfail(
    strict=True,
    reason="BUG: sets.classify takes the first line after a header as the set DESCRIPTION when it "
    "is upper case with no lexicon hits; a description-first row whose codes are all collisions "
    "('THRESHOLD 1 EA 171A AL PE') is swallowed as the set description",
)
def test_first_row_with_only_collision_codes_is_not_a_description() -> None:
    sp = make_page(
        1,
        [("HARDWARE SET NO. 1", H), "THRESHOLD|1|EA|171A|AL|PE", "HINGE|3|EA|5BB1|652|IVE"],
        _DESC_FIRST,
    )
    lines = sp.lines()
    headers = {ln.id: h for ln in lines if (h := parse_header(ln, sp.toks)) is not None}
    (span,) = split_spans(lines, headers)
    assert classify(span, sp.toks) == [Kind.HEADER, Kind.ROW, Kind.ROW]
