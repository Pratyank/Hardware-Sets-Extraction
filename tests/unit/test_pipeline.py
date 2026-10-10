"""pipeline.extract end to end on a synthetic two-page book."""

from __future__ import annotations

from typing import Any

import pytest

from helpers.synth import SynthPage, all_tokens, make_page, run
from hwsets.layout.lines import union_bbox
from hwsets.models import DocumentResult, Field, HardwareSet
from hwsets.pipeline import normalize_set_number

H: dict[str, Any] = {"bold": True, "gap": 12}
RUNNING_HEADER = ("ACME CLINIC  PROJECT 2417", {"y": 36})


def _footer(page: int) -> tuple[str, dict[str, Any]]:
    return (f"DOOR HARDWARE 08 71 00 - {page + 20}", {"y": 760})


def _book() -> list[SynthPage]:
    p1 = make_page(
        1,
        [
            RUNNING_HEADER,
            ("HARDWARE SET NO. 01", {"bold": True, "y": 110}),
            "ENTRANCE DOORS",
            "Doors: 101, 102",
            "QTY|UNIT|DESCRIPTION|CATALOG NUMBER|FINISH|MFR",
            "3|EA|HINGE|5BB1 4.5 X 4.5|652|IVE",
            "1|EA|LOCKSET|ND50PD RHO|626|SCH",
            "1|EA|CLOSER|4040XP|689|LCN",
            "1|EA|THRESHOLD|171A|AL|PE",
            ("HARDWARE SET NO. 02", H),
            "OFFICE",
            "3|EA|HINGE|5BB1 4.5 X 4.5|652|IVE",
            "1|EA|OFFICE LOCK|ND50PD RHO|626|SCH",
            _footer(1),
        ],
    )
    p2 = make_page(
        2,
        [
            RUNNING_HEADER,
            ("1|EA|STOP|WS406|630|IVE", {"y": 110}),
            "3|EA|SILENCER|SR64|GRY|IVE",
            ("HARDWARE SET NO. 03", H),
            "NOT USED",
            ("HARDWARE SET NO. 04", H),
            "3|EA|HINGE|5BB1 4.5 X 4.5|652|IVE",
            "1|EA|CLOSER|4040XP|689|LCN",
            "1|EA|SWEEP|315CN|AL|PE",
            _footer(2),
        ],
    )
    return [p1, p2]


@pytest.fixture(scope="module")
def book() -> list[SynthPage]:
    return _book()


@pytest.fixture(scope="module")
def result(book: list[SynthPage]) -> DocumentResult:
    return run(book)


def _set(result: DocumentResult, number: str) -> HardwareSet:
    (s,) = [s for s in result.sets if s.set_number.value == number]
    return s


def test_all_sets_found_in_order(result: DocumentResult) -> None:
    assert [s.set_number.value for s in result.sets] == ["1", "2", "3", "4"]
    assert [s.status for s in result.sets] == ["active", "active", "not_used", "active"]
    assert [len(s.components) for s in result.sets] == [4, 4, 0, 3]
    assert result.hardware_pages == [1, 2]
    assert result.source_pdf == "synthetic.pdf"


def test_descriptions_and_set_notes(result: DocumentResult) -> None:
    assert _set(result, "1").description.value == "ENTRANCE DOORS"
    assert _set(result, "2").description.value == "OFFICE"
    assert _set(result, "1").notes.value == "Doors: 101, 102"
    assert _set(result, "3").status_text == "NOT USED"


def test_components_are_read_by_column(result: DocumentResult) -> None:
    first = _set(result, "1").components
    assert [(c.qty.value, c.description.value, c.finish.value, c.mfr.value) for c in first] == [
        (3, "HINGE", "652", "IVE"),
        (1, "LOCKSET", "626", "SCH"),
        (1, "CLOSER", "689", "LCN"),
        (1, "THRESHOLD", "AL", "PE"),
    ]
    assert first[3].mfr_resolved == "Pemko"


def test_set_spanning_a_page_break_is_one_set_with_two_regions(result: DocumentResult) -> None:
    s2 = _set(result, "2")
    assert [c.description.value for c in s2.components] == [
        "HINGE",
        "OFFICE LOCK",
        "STOP",
        "SILENCER",
    ]
    assert [r.page for r in s2.location.regions] == [1, 2]
    assert s2.location.line_range[0].startswith("L1_")
    assert s2.location.line_range[1].startswith("L2_")


def test_location_bbox_covers_the_sets_lines(result: DocumentResult, book: list[SynthPage]) -> None:
    toks = all_tokens(book)
    for s in result.sets:
        cited = [
            toks[i]
            for c in s.components
            for f in (c.qty, c.description, c.catalog_number, c.mfr, c.finish, c.notes)
            for i in f.token_ids
        ] + [toks[i] for i in s.set_number.token_ids]
        for page in {t.page for t in cited}:
            (region,) = [r for r in s.location.regions if r.page == page]
            x0, y0, x1, y1 = region.bbox
            for t in (t for t in cited if t.page == page):
                assert x0 <= t.bbox[0] and t.bbox[2] <= x1 + 0.1
                assert y0 <= t.bbox[1] and t.bbox[3] <= y1 + 0.1


def test_set_region_is_tight_on_a_single_page_set(
    result: DocumentResult, book: list[SynthPage]
) -> None:
    s4 = _set(result, "4")
    (region,) = s4.location.regions
    p2 = book[1]
    rows = p2.row_token_ids[5:9]  # header + 3 components
    expected = union_bbox(p2.toks[i].bbox for ids in rows for i in ids)
    assert region.bbox == pytest.approx(expected, abs=0.1)
    assert s4.location.line_range == ("L2_5", "L2_8")


def test_running_header_and_footer_never_reach_the_output(result: DocumentResult) -> None:
    def texts(f: Field[str]) -> str:
        return f.value or ""

    for s in result.sets:
        blob = " ".join(
            texts(f)
            for c in s.components
            for f in (c.description, c.catalog_number, c.notes, c.finish, c.mfr)
        ) + texts(s.notes)
        assert "ACME" not in blob and "08 71 00" not in blob


def test_column_role_diagnostics(result: DocumentResult) -> None:
    roles = [v.split()[0] for v in result.column_roles.values()]
    assert roles == ["qty", "unit", "description", "catalog", "finish", "mfr"]
    assert all("margin" in v for v in result.column_roles.values())
    assert all(k.startswith("p1-2 x\u2248") for k in result.column_roles)


def test_every_valued_field_cites_existing_tokens(
    result: DocumentResult, book: list[SynthPage]
) -> None:
    toks = all_tokens(book)
    for s in result.sets:
        fields = [s.set_number, s.description, s.notes]
        for c in s.components:
            fields += [c.description, c.catalog_number, c.mfr, c.finish, c.notes]
            if c.qty.value is not None:
                assert c.qty.token_ids and all(i in toks for i in c.qty.token_ids)
        for f in fields:
            if f.value is not None:
                assert f.token_ids, f
                assert all(i in toks for i in f.token_ids)


def test_no_validation_warnings_on_a_clean_book(result: DocumentResult) -> None:
    assert result.warnings == []
    assert all(0.0 < s.confidence <= 1.0 for s in result.sets)


def test_document_without_headers() -> None:
    out = run([make_page(1, ["Section 08 71 00 - Door Hardware", "Part 1 General"])])
    assert out.sets == [] and out.hardware_pages == []
    assert "no hardware set headers found" in out.warnings


def test_duplicate_set_numbers_survive_with_a_warning() -> None:
    page = make_page(
        1,
        [
            ("HARDWARE SET NO. 5", H),
            "3|EA|HINGE|5BB1|652|IVE",
            "1|EA|CLOSER|4040XP|689|LCN",
            ("HARDWARE SET NO. 5", H),
            "3|EA|HINGE|5BB1|652|IVE",
            "1|EA|STOP|WS406|630|IVE",
        ],
    )
    out = run([page])
    assert [s.set_number.value for s in out.sets] == ["5", "5"]
    assert any("duplicate set number" in w for w in out.warnings)


@pytest.mark.parametrize(
    ("raw", "display"),
    [("001", "1"), ("01A", "1A"), ("EX-01.0", "EX-1.0"), ("103a", "103A"), ("AL  01", "AL 1"),
     ("10", "10")],
)  # fmt: skip
def test_normalize_set_number(raw: str, display: str) -> None:
    assert normalize_set_number(raw) == display
