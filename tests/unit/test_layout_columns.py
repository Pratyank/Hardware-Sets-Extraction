"""layout.columns: cell starts, anchor clustering, layout clusters."""

from __future__ import annotations

import pytest

from helpers.synth import COL_X, make_page
from hwsets.layout.columns import (
    cell_starts,
    cluster_anchors,
    column_of,
    infer_layouts,
    layout_for_page,
)
from hwsets.layout.lines import group_lines

ROWS = [
    "3|EA|HINGE|5BB1 4.5 X 4.5|652|IVE",
    "1|EA|LOCKSET|ND50PD RHO|626|SCH",
    "1|EA|CLOSER|4040XP|689|LCN",
    "1|EA|KICK PLATE|8400 10 X 34|630|IVE",
    "1|EA|THRESHOLD|171A|AL|PE",
]


def test_cell_starts_split_on_wide_gaps_only() -> None:
    sp = make_page(1, ["1|EA|KICK PLATE|8400 10 X 34|630|IVE"])
    (line,) = sp.lines()
    starts = [t.text for t in cell_starts(line, sp.toks)]
    # Words inside a cell are separated by one space and do not start new cells.
    assert starts == ["1", "EA", "KICK", "8400", "630", "IVE"]


def test_cluster_anchors_on_aligned_rows() -> None:
    sp = make_page(1, ROWS)
    anchors = cluster_anchors(sp.lines(), sp.toks)
    assert [a.x for a in anchors] == list(COL_X)
    assert all(a.support == len(ROWS) for a in anchors)


def test_ragged_starts_cluster_to_the_left_edge() -> None:
    # Each row's description starts slightly to the right (indent jitter < merge distance).
    sp = make_page(1, ROWS)
    jittered = [
        t.model_copy(update={"bbox": (t.bbox[0] + (i % 3), *t.bbox[1:])})
        if abs(t.bbox[0] - 140) < 1
        else t
        for i, t in enumerate(sp.tokens)
    ]
    toks = {t.id: t for t in jittered}
    anchors = cluster_anchors(group_lines(jittered), toks)
    desc = [a for a in anchors if 135 <= a.x <= 145]
    assert len(desc) == 1
    assert desc[0].x <= 141


def test_low_support_positions_are_not_anchors() -> None:
    rows = [*ROWS, *ROWS, ("ODD CELL", {"x": 330})]
    sp = make_page(1, rows)
    xs = [a.x for a in cluster_anchors(sp.lines(), sp.toks)]
    assert 330 not in xs  # 1 of 11 lines: below 15% support


@pytest.mark.parametrize(
    ("x0", "expected"),
    [(60.0, -1), (68.0, 0), (72.0, 0), (99.0, 1), (139.0, 2), (269.0, 3), (449.0, 4), (520.0, 5)],
)
def test_column_of_picks_rightmost_anchor_at_or_left(x0: float, expected: int) -> None:
    assert column_of(x0, list(COL_X)) == expected


def test_infer_layouts_separates_pages_with_different_anchors() -> None:
    other_x = (40.0, 210.0, 380.0, 520.0)  # qty, description, catalog, mfr: different consultant
    p1 = make_page(1, ROWS)
    p2 = make_page(2, ["2|HINGE|5BB1|IVE", "1|CLOSER|4040XP|LCN", "1|STOP|WS406|IVE"], other_x)
    lines = {1: p1.lines(), 2: p2.lines()}
    toks = {**p1.toks, **p2.toks}
    layouts = infer_layouts(lines, toks)
    assert [lay.pages for lay in layouts] == [(1,), (2,)]
    assert layouts[0].xs == list(COL_X)
    assert layouts[1].xs == list(other_x)
    assert layout_for_page(layouts, 2) is layouts[1]


def test_infer_layouts_merges_similar_pages() -> None:
    shifted = tuple(x + 3 for x in COL_X)  # same layout, a few points of drift
    p1 = make_page(1, ROWS)
    p2 = make_page(2, ROWS, shifted)
    p3 = make_page(3, ROWS)
    lines = {1: p1.lines(), 2: p2.lines(), 3: p3.lines()}
    toks = {**p1.toks, **p2.toks, **p3.toks}
    layouts = infer_layouts(lines, toks)
    assert len(layouts) == 1
    assert layouts[0].pages == (1, 2, 3)
    assert layouts[0].n_lines == 3 * len(ROWS)
    assert len(layouts[0].anchors) == len(COL_X)


def test_layout_for_page_falls_back_to_nearest_layout() -> None:
    p1 = make_page(1, ROWS)
    p5 = make_page(5, ["2|HINGE|5BB1|IVE", "1|CLOSER|4040XP|LCN", "1|STOP|WS406|IVE"],
                   (40.0, 210.0, 380.0, 520.0))  # fmt: skip
    layouts = infer_layouts({1: p1.lines(), 5: p5.lines()}, {**p1.toks, **p5.toks})
    assert layout_for_page(layouts, 2) is layouts[0]
    assert layout_for_page(layouts, 4) is layouts[1]
    assert layout_for_page([], 1) is None
