"""Property tests (Hypothesis) over synthetic books with known truth (PLAN section 6)."""

from __future__ import annotations

import re
from dataclasses import replace

from hypothesis import assume, given
from hypothesis import strategies as st

from helpers.books import (
    COLLISION_CODES,
    ROLES,
    BookSpec,
    Comp,
    Layout,
    SetSpec,
    books,
    render,
)
from helpers.synth import all_tokens, component_tuples, run
from hwsets.models import DocumentResult
from hwsets.pipeline import normalize_set_number

_NORM = re.compile(r"[^A-Z0-9]")


def _truth(book: BookSpec) -> list[list[tuple[object, ...]]]:
    return [[c.as_tuple() for c in s.components] for s in book.sets]


def _extract(book: BookSpec, layout: Layout | None = None) -> DocumentResult:
    return run(render(book, layout))


def _flat_rows(book: BookSpec) -> int:
    """Number of rows ``render`` emits (headers, NOT USED lines, components)."""
    return sum(1 + (1 if s.not_used else len(s.components)) for s in book.sets)


# ---------------------------------------------------------------------------
# Column roles
# ---------------------------------------------------------------------------


@given(book=books(), order=st.permutations(ROLES))
def test_column_permutation_invariance(book: BookSpec, order: list[str]) -> None:
    canonical = component_tuples(_extract(book))
    permuted = component_tuples(_extract(book, Layout(order=tuple(order))))
    assert permuted == canonical == _truth(book)


@st.composite
def _with_collisions(draw: st.DrawFn, role: str) -> BookSpec:
    """A book where some rows carry a collision code (PE / NO) in the ``role`` column."""
    book = draw(books(min_comps=3))
    sets = []
    for s in book.sets:
        comps = list(s.components)
        # At most a third of each set, so the column's lexicon evidence stays decisive.
        idx = draw(st.sets(st.integers(0, len(comps) - 1), min_size=1, max_size=len(comps) // 3))
        for i in idx:
            code = draw(st.sampled_from(COLLISION_CODES))
            comps[i] = (
                replace(comps[i], mfr=code) if role == "mfr" else replace(comps[i], finish=code)
            )
        sets.append(replace(s, components=tuple(comps)))
    return BookSpec(tuple(sets))


@given(book=_with_collisions("mfr"), order=st.permutations(ROLES))
def test_collision_codes_in_mfr_column_are_manufacturers(book: BookSpec, order: list[str]) -> None:
    result = _extract(book, Layout(order=tuple(order)))
    assert component_tuples(result) == _truth(book)
    names = {"PE": "Pemko", "NO": "Norton"}
    for s in result.sets:
        for c in s.components:
            if c.mfr.value in names:
                assert c.mfr_resolved == names[c.mfr.value]
                assert c.finish.value not in COLLISION_CODES


@given(book=_with_collisions("finish"), order=st.permutations(ROLES))
def test_collision_codes_in_finish_column_are_finishes(book: BookSpec, order: list[str]) -> None:
    result = _extract(book, Layout(order=tuple(order)))
    assert component_tuples(result) == _truth(book)
    for s in result.sets:
        for c in s.components:
            assert c.mfr.value not in COLLISION_CODES


# ---------------------------------------------------------------------------
# Set boundaries
# ---------------------------------------------------------------------------


@st.composite
def _book_and_inner_row(draw: st.DrawFn) -> tuple[BookSpec, int]:
    """A book and the flat index of a component row that is not the first row of its set.

    At least two component rows stay on the first page: a first page with a single row cannot
    yield column anchors (see ``test_single_row_first_page_keeps_its_component``)."""
    book = draw(books())
    inner: list[int] = []
    i = 0
    rows_before = 0
    for s in book.sets:
        i += 1  # header
        for k in range(len(s.components)):
            if k > 0 and rows_before >= 2:
                inner.append(i)
            i += 1
            rows_before += 1
    assume(inner)
    return book, draw(st.sampled_from(inner))


@given(case=_book_and_inner_row())
def test_page_break_inside_a_set_never_splits_it(case: tuple[BookSpec, int]) -> None:
    book, row = case
    pages = render(book, Layout(page_break_before=frozenset({row})))
    assert len(pages) == 2
    result = run(pages)
    assert len(result.sets) == len(book.sets)
    assert component_tuples(result) == _truth(book)
    spanning = [s for s in result.sets if len(s.location.regions) == 2]
    assert len(spanning) == 1
    assert [r.page for r in spanning[0].location.regions] == [1, 2]


@given(
    book=books(),
    gaps=st.sets(st.integers(0, 19), max_size=4),
    gap=st.floats(10.0, 40.0),
)
def test_blank_rows_inside_a_set_do_not_split_it(
    book: BookSpec, gaps: set[int], gap: float
) -> None:
    result = _extract(book, Layout(gap_before=frozenset(gaps), gap=gap))
    assert [s.set_number.value for s in result.sets] == [str(s.number) for s in book.sets]
    assert component_tuples(result) == _truth(book)


@given(book=books(min_sets=1, max_sets=1, min_comps=4, max_comps=6), cut=st.integers(1, 3))
def test_blank_row_followed_by_a_header_does_split(book: BookSpec, cut: int) -> None:
    (only,) = book.sets
    first = SetSpec(1, only.components[:cut])
    second = SetSpec(2, only.components[cut:])
    result = _extract(BookSpec((first, second)), Layout(gap_before=frozenset({cut}), gap=30.0))
    assert [s.set_number.value for s in result.sets] == ["1", "2"]
    assert [len(s.components) for s in result.sets] == [cut, len(only.components) - cut]


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


@given(book=books(allow_not_used=True))
def test_not_used_sets_have_zero_components(book: BookSpec) -> None:
    result = _extract(book)
    assert len(result.sets) == len(book.sets)
    for spec, got in zip(book.sets, result.sets, strict=True):
        if spec.not_used:
            assert got.status == "not_used"
            assert got.status_text == "NOT USED"
            assert got.components == []
        else:
            assert got.status == "active"


@given(book=books(allow_not_used=True, allow_missing_qty=True), order=st.permutations(ROLES))
def test_no_component_is_lost(book: BookSpec, order: list[str]) -> None:
    result = _extract(book, Layout(order=tuple(order)))
    assert sum(len(s.components) for s in result.sets) == book.n_component_rows()


@given(book=books(allow_missing_qty=True))
def test_missing_quantity_is_null(book: BookSpec) -> None:
    result = _extract(book)
    for spec, got in zip(book.sets, result.sets, strict=True):
        assert [c.qty.value for c in got.components] == [c.qty for c in spec.components]
        for c in got.components:
            if c.qty.value is None:
                assert c.qty.token_ids == []


def test_missing_quantity_example() -> None:
    comps = (
        Comp(3, "EA", "HINGE", "5BB1 4.5 X 4.5", "652", "IVE"),
        Comp(None, "EA", "SILENCER", "SR64", "626", "IVE"),
        Comp(1, "EA", "CLOSER", "4040XP", "689", "LCN"),
    )
    result = _extract(BookSpec((SetSpec(1, comps), SetSpec(2, comps))))
    assert [c.qty.value for c in result.sets[0].components] == [3, None, 1]


@given(
    book=books(allow_missing_qty=True, allow_not_used=True),
    order=st.permutations(ROLES),
    breaks=st.sets(st.integers(1, 20), max_size=2),
)
def test_every_value_is_grounded_in_its_tokens(
    book: BookSpec, order: list[str], breaks: set[int]
) -> None:
    breaks = {b for b in breaks if b < _flat_rows(book)}
    pages = render(book, Layout(order=tuple(order), page_break_before=frozenset(breaks)))
    toks = all_tokens(pages)
    result = run(pages)
    for s in result.sets:
        fields = [s.description, s.notes]
        for c in s.components:
            fields += [c.description, c.catalog_number, c.mfr, c.finish, c.notes]
            if c.qty.value is not None:
                assert [int(toks[i].text) for i in c.qty.token_ids] == [c.qty.value]
        for f in fields:
            if f.value is None:
                continue
            source = "".join(toks[i].text for i in f.token_ids)
            assert _NORM.sub("", f.value.upper()) == _NORM.sub("", source.upper())
        # Set numbers are display-normalized ("01" -> "1"); the raw id is in the tokens.
        raw = " ".join(toks[i].text for i in s.set_number.token_ids)
        assert s.set_number.value == normalize_set_number(raw)
