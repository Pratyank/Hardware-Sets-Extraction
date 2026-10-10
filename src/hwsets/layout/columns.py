"""Column bands from token x-positions, inferred over many lines at once.

Cells are left-aligned in every schedule format surveyed. Within a line, a token *starts a cell*
when it is the first token or follows a horizontal gap wider than about one character. Cell-start
x positions are clustered across all component-like lines of a layout, and clusters with enough
support (>= 15% of lines) become column anchors. A token belongs to the rightmost anchor at or
left of its x0.

Pages can use different layouts (one PDF can bind two consultants' schedules), so pages are first
grouped into *layout clusters* by anchor similarity, and anchors are re-estimated per cluster.

Pure functions of tokens and lines.
"""

from __future__ import annotations

import itertools
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hwsets.models import Line, Token

MIN_SUPPORT_FRACTION = 0.15
_MERGE_PT = 7.0  # cell starts closer than this belong to the same anchor
_ASSIGN_TOL = 5.0  # a token may start this far left of its anchor
_PAGE_MATCH_PT = 9.0
_PAGE_MATCH_SHARE = 0.6


@dataclass(frozen=True, slots=True)
class Anchor:
    x: float
    support: int  # number of lines with a cell starting here


@dataclass(frozen=True, slots=True)
class Layout:
    pages: tuple[int, ...]
    anchors: tuple[Anchor, ...]
    n_lines: int

    @property
    def xs(self) -> list[float]:
        return [a.x for a in self.anchors]


def cell_gap(tokens: Sequence[Token]) -> float:
    sizes = [t.font_size for t in tokens if t.font_size > 0]
    size = statistics.median(sizes) if sizes else 9.0
    return max(4.0, 0.75 * size)


def cell_starts(line: Line, toks: Mapping[str, Token]) -> list[Token]:
    tokens = [toks[i] for i in line.token_ids]
    if not tokens:
        return []
    gap = cell_gap(tokens)
    starts = [tokens[0]]
    for prev, cur in itertools.pairwise(tokens):
        if cur.bbox[0] - prev.bbox[2] > gap:
            starts.append(cur)
    return starts


def cluster_anchors(lines: Sequence[Line], toks: Mapping[str, Token]) -> list[Anchor]:
    """1-D clustering of cell-start x positions; one vote per line per cluster."""
    if not lines:
        return []
    points: list[tuple[float, int]] = []  # (x, line index)
    for li, ln in enumerate(lines):
        points.extend((t.bbox[0], li) for t in cell_starts(ln, toks))
    points.sort()
    clusters: list[list[tuple[float, int]]] = []
    for x, li in points:
        if clusters and x - clusters[-1][-1][0] <= _MERGE_PT:
            clusters[-1].append((x, li))
        else:
            clusters.append([(x, li)])
    need = max(2, MIN_SUPPORT_FRACTION * len(lines))
    out: list[Anchor] = []
    for c in clusters:
        support = len({li for _, li in c})
        if support >= need:
            # Left edge of the cluster's dense core: cells are left-aligned, and ragged starts
            # (indented continuation text) sit to the right of it.
            xs = sorted(x for x, _ in c)
            core = xs[: max(1, len(xs) // 2)]
            out.append(Anchor(x=round(statistics.median(core), 1), support=support))
    return out


def column_of(x0: float, anchors: Sequence[float]) -> int:
    """Index of the rightmost anchor at or left of ``x0`` (-1 when left of every anchor)."""
    col = -1
    for i, a in enumerate(anchors):
        if x0 + _ASSIGN_TOL >= a:
            col = i
        else:
            break
    return col


def _compatible(a: Sequence[float], b: Sequence[float]) -> bool:
    if not a or not b:
        return False
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    hits = sum(1 for x in small if any(abs(x - y) <= _PAGE_MATCH_PT for y in big))
    return hits >= _PAGE_MATCH_SHARE * len(small)


def infer_layouts(
    lines_by_page: Mapping[int, Sequence[Line]], toks: Mapping[str, Token]
) -> list[Layout]:
    """Group pages by column layout and estimate anchors per group.

    ``lines_by_page`` should hold only component-like lines (rows of the schedule).
    """
    pages = sorted(p for p, ls in lines_by_page.items() if ls)
    page_anchors = {p: [a.x for a in cluster_anchors(lines_by_page[p], toks)] for p in pages}
    groups: list[list[int]] = []
    group_xs: list[list[float]] = []
    for p in pages:
        xs = page_anchors[p]
        for gi, gxs in enumerate(group_xs):
            if _compatible(xs, gxs) or len(lines_by_page[p]) < 3:
                groups[gi].append(p)
                break
        else:
            groups.append([p])
            group_xs.append(xs)
    layouts: list[Layout] = []
    for g in groups:
        lines = [ln for p in g for ln in lines_by_page[p]]
        layouts.append(Layout(pages=tuple(g), anchors=tuple(cluster_anchors(lines, toks)),
                              n_lines=len(lines)))  # fmt: skip
    return layouts


def layout_for_page(layouts: Sequence[Layout], page: int) -> Layout | None:
    for lay in layouts:
        if page in lay.pages:
            return lay
    if not layouts:
        return None
    # Pages without component rows of their own use the nearest layout.
    return min(layouts, key=lambda lay: min(abs(p - page) for p in lay.pages))
