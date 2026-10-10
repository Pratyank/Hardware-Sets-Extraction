"""Synthetic hardware-set books with known ground truth, plus Hypothesis strategies.

A ``BookSpec`` is the truth (sets and their components); ``render`` lays it out as pages of
tokens in a given column order, optionally with a page break or a blank gap at chosen rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hypothesis import strategies as st

from helpers.synth import SynthPage, make_page

ROLES: tuple[str, ...] = ("qty", "unit", "description", "catalog", "finish", "mfr")
# Evenly spaced cell starts wide enough for every lexicon value below.
SLOTS: tuple[float, ...] = (60.0, 150.0, 240.0, 340.0, 450.0, 530.0)

UNITS = ("EA", "PR")
DESCRIPTIONS = (
    "HINGE",
    "LOCKSET",
    "CLOSER",
    "KICK PLATE",
    "WALL STOP",
    "SILENCER",
    "THRESHOLD",
    "PUSH PLATE",
    "EXIT DEVICE",
    "COORDINATOR",
)
# "8400 10 X 34" is left out: a book whose whole catalog column is that one value loses it (see
# test_four_digit_model_number_is_catalog_not_a_count, a regression test).
CATALOGS = ("5BB1 4.5 X 4.5", "ND50PD RHO", "4040XP", "8400 B4E", "WS406", "SR64", "171A",
            "315CN", "99L-F", "COR72")  # fmt: skip
FINISHES = ("626", "630", "652", "689", "US26D", "613")
MFRS = ("IVE", "SCH", "LCN", "VON", "GLY", "HAG")
COLLISION_CODES = ("PE", "NO")

HEADER_OPTS: dict[str, Any] = {"bold": True, "gap": 12}


@dataclass(frozen=True, slots=True)
class Comp:
    qty: int | None
    unit: str | None
    description: str
    catalog: str
    finish: str
    mfr: str

    def cell(self, role: str) -> str:
        value = {
            "qty": None if self.qty is None else str(self.qty),
            "unit": self.unit,
            "description": self.description,
            "catalog": self.catalog,
            "finish": self.finish,
            "mfr": self.mfr,
        }[role]
        return value or ""

    def as_tuple(self) -> tuple[Any, ...]:
        return (self.qty, self.unit, self.description, self.catalog, self.finish, self.mfr)


@dataclass(frozen=True, slots=True)
class SetSpec:
    number: int
    components: tuple[Comp, ...]
    not_used: bool = False


@dataclass(frozen=True, slots=True)
class BookSpec:
    sets: tuple[SetSpec, ...]

    def n_component_rows(self) -> int:
        return sum(len(s.components) for s in self.sets if not s.not_used)


@dataclass(slots=True)
class Layout:
    order: tuple[str, ...] = ROLES  # role of each column, left to right
    page_break_before: frozenset[int] = field(default_factory=frozenset)  # global row indices
    gap_before: frozenset[int] = field(default_factory=frozenset)  # component row indices
    gap: float = 16.0


def row_text(comp: Comp, order: tuple[str, ...]) -> str:
    return "|".join(comp.cell(role) for role in order)


def render(book: BookSpec, layout: Layout | None = None) -> list[SynthPage]:
    """Lay the book out; ``page_break_before`` holds indices into the flat row list (headers,
    NOT USED lines and component rows alike)."""
    lay = layout or Layout()
    rows: list[tuple[str, dict[str, Any]]] = []
    comp_index = 0
    for s in book.sets:
        rows.append((f"HARDWARE SET NO. {s.number:02d}", dict(HEADER_OPTS)))
        if s.not_used:
            rows.append(("NOT USED", {}))
            continue
        for c in s.components:
            opts: dict[str, Any] = {"gap": lay.gap} if comp_index in lay.gap_before else {}
            rows.append((row_text(c, lay.order), opts))
            comp_index += 1
    pages: list[list[tuple[str, dict[str, Any]]]] = [[]]
    for i, row in enumerate(rows):
        if i in lay.page_break_before and pages[-1]:
            pages.append([])
        pages[-1].append(row)
    return [make_page(n, page_rows, SLOTS) for n, page_rows in enumerate(pages, start=1)]


def _comps(qty: st.SearchStrategy[int | None]) -> st.SearchStrategy[Comp]:
    return st.builds(
        Comp,
        qty=qty,
        unit=st.sampled_from(UNITS),
        description=st.sampled_from(DESCRIPTIONS),
        catalog=st.sampled_from(CATALOGS),
        finish=st.sampled_from(FINISHES),
        mfr=st.sampled_from(MFRS),
    )


@st.composite
def books(
    draw: st.DrawFn,
    *,
    min_sets: int = 2,
    max_sets: int = 4,
    min_comps: int = 2,
    max_comps: int = 5,
    allow_missing_qty: bool = False,
    allow_not_used: bool = False,
) -> BookSpec:
    """Random books. With ``allow_missing_qty`` any component but the first two of each set may
    lack a quantity, so the quantity column keeps enough support (>= 2 values, >= 15% of rows)
    to be found as a column at all; ``test_sparse_quantity_column_keeps_its_component`` shows
    what happens below that."""
    assert min_comps >= 2
    qty: st.SearchStrategy[int | None] = st.integers(1, 4)
    later_qty = st.one_of(qty, st.none()) if allow_missing_qty else qty
    n = draw(st.integers(min_sets, max_sets))
    sets: list[SetSpec] = []
    for k in range(n):
        not_used = allow_not_used and k > 0 and draw(st.booleans())
        comps: tuple[Comp, ...] = ()
        if not not_used:
            first = draw(st.lists(_comps(qty), min_size=2, max_size=2))
            rest = draw(st.lists(_comps(later_qty), min_size=min_comps - 2, max_size=max_comps - 2))
            comps = (*first, *rest)
        sets.append(SetSpec(number=k + 1, components=comps, not_used=not_used))
    return BookSpec(tuple(sets))
