"""layout.chrome: running headers/footers and column-header rows."""

from __future__ import annotations

from helpers.synth import PAGE_H, make_page
from hwsets.layout.chrome import (
    chrome_keys,
    header_row_roles,
    in_margin,
    is_chrome,
    normalize,
)
from hwsets.models import Line


def _book(n_pages: int, *, header_on_every_page: bool = True) -> dict[int, list[Line]]:
    by_page: dict[int, list[Line]] = {}
    for p in range(1, n_pages + 1):
        rows = [
            ("PROJECT 2024-117 ACME CLINIC", {"y": 30}),
            (f"HARDWARE GROUP NO. {p:02d}", {"y": 40}) if header_on_every_page else ("", {}),
            ("3|EA|HINGE|5BB1|652|IVE", {"y": 300}),
            (f"DOOR HARDWARE 08 71 00 - {p + 10}", {"y": 760}),
        ]
        by_page[p] = make_page(p, rows).lines()
    return by_page


def test_normalize_collapses_digits_case_and_spaces() -> None:
    assert normalize("  Door Hardware  08 71 00 - 19 ") == "door hardware # # # - #"
    assert normalize("PAGE 7") == normalize("page 123")


def test_in_margin_uses_top_and_bottom_bands() -> None:
    lines = make_page(1, [("TOP", {"y": 20}), ("MIDDLE", {"y": 400}), ("BOTTOM", {"y": 770})])
    assert [in_margin(ln, PAGE_H) for ln in lines.lines()] == [True, False, True]


def test_repeated_margin_lines_are_chrome_with_digits_normalized() -> None:
    by_page = _book(4)
    keys = chrome_keys(by_page, dict.fromkeys(by_page, PAGE_H))
    assert normalize("DOOR HARDWARE 08 71 00 - 11") in keys  # page numbers differ per page
    assert normalize("PROJECT 2024-117 ACME CLINIC") in keys
    body_line = by_page[1][2]
    assert body_line.text.startswith("3 EA HINGE")
    assert not is_chrome(body_line, PAGE_H, keys)  # body text is never chrome
    footer = by_page[3][-1]
    assert is_chrome(footer, PAGE_H, keys)


def test_set_headers_in_the_margin_also_normalize_alike_unless_protected() -> None:
    # "HARDWARE GROUP NO. 01/02/..." normalize to the same key and sit in the top band, so
    # without protection they would be dropped as chrome. Protected ids never count.
    by_page = _book(4)
    heights = dict.fromkeys(by_page, PAGE_H)
    header_key = normalize("HARDWARE GROUP NO. 01")
    assert header_key in chrome_keys(by_page, heights)
    protect = frozenset(ln.id for ls in by_page.values() for ln in ls if "GROUP" in ln.text)
    assert header_key not in chrome_keys(by_page, heights, protect)


def test_margin_line_on_a_minority_of_pages_is_not_chrome() -> None:
    by_page = _book(4)
    by_page[1] = [*by_page[1], *make_page(1, [("ONE-OFF NOTE", {"y": 775})]).lines()]
    keys = chrome_keys(by_page, dict.fromkeys(by_page, PAGE_H))
    assert normalize("ONE-OFF NOTE") not in keys


def test_single_page_has_no_chrome() -> None:
    by_page = _book(1)
    assert chrome_keys(by_page, {1: PAGE_H}) == set()


def test_header_row_roles_recognizes_column_headers() -> None:
    roles = header_row_roles(["QTY", "DESCRIPTION", "CATALOG", "NUMBER", "FINISH", "MFR"])
    assert roles == ["qty", "description", "catalog", None, "finish", "mfr"]
    assert header_row_roles(["Qty.", "Item", "Mfg.", "Fin."]) == [
        "qty",
        "description",
        "mfr",
        "finish",
    ]


def test_header_row_roles_rejects_ordinary_rows() -> None:
    assert header_row_roles(["3", "EA", "HINGE", "5BB1", "652", "IVE"]) == []
    # Two vocabulary words are not enough.
    assert header_row_roles(["FINISH", "HARDWARE", "NOTES"]) == []
    # Three hits drowned in prose (< 60% of the words) are not a header row.
    words = ["PROVIDE", "QTY", "OF", "ITEMS", "WITH", "FINISH", "AND", "NOTES", "AS", "SCHEDULED"]
    assert header_row_roles(words) == []
