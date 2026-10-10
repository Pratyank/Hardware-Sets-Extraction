"""segment.headers: the permissive header grammar and per-document signature induction."""

from __future__ import annotations

import pytest

from helpers.synth import line_of, make_page
from hwsets.segment.headers import (
    NOT_USED_RE,
    canonical_keyword,
    induce_headers,
    looks_like_component,
    parse_header,
)


def _parse(text: str) -> tuple[tuple[str, ...], list[str], str] | None:
    """(set ids, description words, canonical keyword) or None."""
    ln, toks = line_of(text)
    h = parse_header(ln, toks)
    if h is None:
        return None
    return h.set_ids, [toks[i].text for i in h.desc_token_ids], h.keyword


@pytest.mark.parametrize(
    ("text", "ids", "desc", "keyword"),
    [
        ("Hardware Group No. 01", ("01",), [], "group hardware no"),
        ("HARDWARE GROUP NO. 103A", ("103A",), [], "group hardware no"),
        ("PART 60 - HARDWARE GROUP NO. C00.EXT", ("C00.EXT",), [], "group hardware no"),
        ("Set: EX-1.0", ("EX-1.0",), [], "set"),
        ("Set #AL 01", ("AL 01",), [], "# set"),
        ("Set #CR38CLHO", ("CR38CLHO",), [], "# set"),
        ("Heading #17", ("17",), [], "# heading"),
        (
            "HW 02A Interior Single - Classroom",
            ("02A",),
            ["Interior", "Single", "-", "Classroom"],
            "hw",
        ),
        (
            "Hardware Group/Set #B1 and #B2 \u2013 Bedrooms",
            ("B1", "B2"),
            ["Bedrooms"],
            "# group hardware set",
        ),
        ("Hardware Group No.263", ("263",), [], "group hardware no"),
        ("Set: MISC", ("MISC",), [], "set"),
        ("HARDWARE SET NO. 3 - NOT USED", ("3",), ["NOT", "USED"], "hardware no set"),
    ],
)
def test_parse_header_real_world_shapes(
    text: str, ids: tuple[str, ...], desc: list[str], keyword: str
) -> None:
    assert _parse(text) == (ids, desc, keyword)


@pytest.mark.parametrize(
    "text",
    [
        "DOOR HARDWARE 08 71 00 - 19",  # running footer: keyword does not name a set
        "Hardware Sets:",  # no id
        "SET SCREWS SHALL BE",  # an id needs a digit unless introduced by '#' or ':'
        "3.6 HARDWARE SETS",  # article heading
        "Hardware Group No.",  # keyword only
        "3 EA HINGE 5BB1 652 IVE",  # component row
    ],
)
def test_parse_header_rejects_non_headers(text: str) -> None:
    assert _parse(text) is None


def test_id_tokens_and_keyword_tokens_are_grounded() -> None:
    ln, toks = line_of("Hardware Group/Set #B1 and #B2 \u2013 Bedrooms")
    h = parse_header(ln, toks)
    assert h is not None
    assert [[toks[i].text for i in grp] for grp in h.id_token_ids] == [["#B1"], ["#B2"]]
    assert [toks[i].text for i in h.keyword_token_ids][:2] == ["Hardware", "Group/Set"]
    assert h.line_id == ln.id
    assert h.x0 == toks[ln.token_ids[0]].bbox[0]


def test_typography_is_recorded() -> None:
    ln, toks = line_of("HARDWARE SET NO. 4", bold=True, size=11)
    h = parse_header(ln, toks)
    assert h is not None
    assert h.bold and h.font_size == 11


def test_canonical_keyword_is_an_order_free_bag() -> None:
    assert canonical_keyword("Hardware Groups No.") == canonical_keyword("GROUP HARDWARE NUMBER")
    assert canonical_keyword("Door Hardware Set #") == "# hardware set"
    assert canonical_keyword("HDWE Headings") == "hardware heading"


def test_not_used_regex_is_standalone_only() -> None:
    for text in ("NOT USED", "N/A", "NA", "Omitted", "DELETED", "void", "Not In Contract"):
        assert NOT_USED_RE.search(text), text
    for text in ("NATIONAL", "AVOIDANCE", "CANADA", "UNUSED"):
        assert not NOT_USED_RE.search(text), text


def test_looks_like_component() -> None:
    row, toks = line_of("3 EA HINGE 5BB1 4.5 X 4.5 652 IVE")
    assert looks_like_component(row, toks)
    codes, toks2 = line_of("CLOSER 4040XP 689 LCN")
    assert looks_like_component(codes, toks2)  # two lexicon hits
    prose, toks3 = line_of("Provide hardware as scheduled")
    assert not looks_like_component(prose, toks3)


# ---------------------------------------------------------------------------
# induce_headers
# ---------------------------------------------------------------------------

_ROWS = [
    "3|EA|HINGE|5BB1 4.5 X 4.5|652|IVE",
    "1|EA|LOCKSET|ND50PD RHO|626|SCH",
    "1|EA|CLOSER|4040XP|689|LCN",
]


def _header(text: str) -> tuple[str, dict[str, object]]:
    return (text, {"bold": True, "gap": 10})


def test_dominant_signature_is_chosen_over_stray_candidates() -> None:
    rows: list[str | tuple[str, dict[str, object]]] = [
        "Group 1 openings shall comply with the following requirements",
        "Contractor shall verify all dimensions in the field before ordering",
    ]
    for n in (1, 2, 3, 4):
        rows += [_header(f"HARDWARE GROUP NO. {n:02d}"), *_ROWS]
    sp = make_page(1, rows)
    ind = induce_headers(sp.lines(), sp.toks)
    assert ind.signature is not None
    assert ind.signature.keyword == "group hardware no"
    assert ind.signature.bold
    assert ind.signature.support == 4
    assert [h.set_ids for h in ind.headers] == [("01",), ("02",), ("03",), ("04",)]
    assert ind.candidates == 5  # the prose line was a candidate, then outvoted
    assert ind.warnings == []


def test_spec_prose_candidates_without_component_rows_are_rejected() -> None:
    prose = [
        "Set 1 of keys shall be delivered to the Owner",
        "Furnish keys in sealed envelopes labeled by door number",
        "Set 2 of keys shall be retained by the Contractor",
        "Coordinate with the Owner's security consultant",
        "Set 3 of keys shall be destroyed after acceptance",
        "Refer to Division 01 for closeout requirements",
    ]
    sp = make_page(1, prose)
    ind = induce_headers(sp.lines(), sp.toks)
    assert ind.candidates == 3
    assert ind.signature is None
    assert ind.headers == []


def test_low_support_book_is_still_found_when_followed_by_components() -> None:
    sp = make_page(1, [_header("HARDWARE SET NO. 1"), *_ROWS])
    ind = induce_headers(sp.lines(), sp.toks)
    assert ind.signature is not None
    assert [h.set_ids for h in ind.headers] == [("1",)]
    assert any("low support" in w for w in ind.warnings)


def test_not_used_header_needs_no_component_evidence() -> None:
    sp = make_page(
        1,
        [
            _header("HARDWARE SET NO. 1"),
            *_ROWS,
            _header("HARDWARE SET NO. 2"),
            "NOT USED",
            _header("HARDWARE SET NO. 3"),
            *_ROWS,
        ],
    )
    ind = induce_headers(sp.lines(), sp.toks)
    assert [h.set_ids for h in ind.headers] == [("1",), ("2",), ("3",)]


def test_no_candidates() -> None:
    sp = make_page(1, _ROWS)
    ind = induce_headers(sp.lines(), sp.toks)
    assert ind.signature is None and ind.candidates == 0
