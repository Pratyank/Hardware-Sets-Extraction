"""layout.lines: tokens -> visual lines."""

from __future__ import annotations

from helpers.synth import make_page, tok
from hwsets.layout.lines import (
    clean_tokens,
    group_lines,
    is_glyph_noise,
    is_rotated_noise,
    union_bbox,
)


def test_tokens_group_by_vertical_overlap_not_pymupdf_line_index() -> None:
    # Same visual band, different PyMuPDF block/line, small baseline jitter.
    toks = [
        tok("p1_w0", "HINGE", (140, 100, 165, 109), block=3, line=0),
        tok("p1_w1", "3", (72, 101, 76, 110), block=1, line=0),
        tok("p1_w2", "IVE", (500, 99.5, 513, 108.5), block=7, line=2),
        tok("p1_w3", "LOCKSET", (140, 114, 175, 123), block=3, line=1),
    ]
    lines = group_lines(toks)
    assert [ln.text for ln in lines] == ["3 HINGE IVE", "LOCKSET"]
    assert lines[0].token_ids == ["p1_w1", "p1_w0", "p1_w2"]  # sorted by x
    assert [ln.id for ln in lines] == ["L1_0", "L1_1"]
    assert lines[0].bbox == (72, 99.5, 513, 110)


def test_lines_are_ordered_top_to_bottom_regardless_of_input_order() -> None:
    sp = make_page(2, ["FIRST LINE", "SECOND LINE", "THIRD LINE"])
    lines = group_lines(list(reversed(sp.tokens)))
    assert [ln.text for ln in lines] == ["FIRST LINE", "SECOND LINE", "THIRD LINE"]
    assert all(ln.page == 2 for ln in lines)


def test_small_overlap_does_not_merge_adjacent_rows() -> None:
    # 9pt glyphs on a 7pt pitch overlap by 2pt (22% of the height): still two lines.
    toks = [
        tok("p1_w0", "A", (72, 100, 77, 109), line=0),
        tok("p1_w1", "B", (72, 107, 77, 116), line=1),
    ]
    assert [ln.text for ln in group_lines(toks)] == ["A", "B"]


def test_struck_tokens_are_excluded() -> None:
    sp = make_page(1, [("1|EA|CLOSER|4040XP|689|LCN", {}), ("1|EA|CLOSER|4041|689|LCN", {})])
    struck = [t.model_copy(update={"strike": True}) if t.text == "4040XP" else t for t in sp.tokens]
    lines = group_lines(struck)
    assert lines[0].text == "1 EA CLOSER 689 LCN"
    assert all("4040XP" not in ln.text for ln in lines)


def test_line_of_only_struck_tokens_disappears() -> None:
    sp = make_page(1, [("DELETED ROW", {"strike": True}), "KEPT ROW"])
    assert [ln.text for ln in group_lines(sp.tokens)] == ["KEPT ROW"]


def test_glyph_and_pua_tokens_are_dropped() -> None:
    toks = [
        tok("p1_w0", "", (60, 100, 68, 109)),  # private-use icon glyph
        tok("p1_w1", "626", (72, 100, 86, 109)),
        tok("p1_w2", "\x07", (90, 100, 92, 109)),  # non-printable
    ]
    assert is_glyph_noise(toks[0]) and is_glyph_noise(toks[2])
    assert not is_glyph_noise(toks[1])
    lines = group_lines(toks)
    assert len(lines) == 1
    assert lines[0].token_ids == ["p1_w1"]


def test_vertical_watermark_line_is_dropped() -> None:
    # A PyMuPDF line whose words progress downward (rotated margin stamp).
    stamp = [
        tok("p1_w0", "NOT", (20, 300, 29, 318), block=9, line=0),
        tok("p1_w1", "FOR", (20, 322, 29, 340), block=9, line=0),
        tok("p1_w2", "CONSTRUCTION", (20, 344, 29, 420), block=9, line=0),
    ]
    body = [tok("p1_w3", "HINGE", (140, 320, 165, 329), block=1, line=0)]
    lines = group_lines(stamp + body)
    assert [ln.text for ln in lines] == ["HINGE"]


def test_single_rotated_word_is_noise_but_upright_word_is_not() -> None:
    rotated = tok("p1_w0", "DRAFT", (20, 300, 29, 330))  # 9 wide, 30 tall
    upright = tok("p1_w1", "DRAFT", (72, 300, 95, 309))
    assert is_rotated_noise(rotated)
    assert not is_rotated_noise(upright)
    assert [ln.text for ln in group_lines([rotated, upright])] == ["DRAFT"]


def test_clean_tokens_strips_glued_icon_and_shifts_bbox_right() -> None:
    glued = tok("p1_w0", " 626", (100, 100, 130, 109))
    plain = tok("p1_w1", "IVE", (140, 100, 153, 109))
    out = clean_tokens([glued, plain, tok("p1_w2", "", (5, 5, 9, 9))])
    assert [t.id for t in out] == ["p1_w0", "p1_w1"]  # id kept, glyph-only token dropped
    cleaned = out[0]
    assert cleaned.text == "626"
    assert cleaned.bbox[0] > glued.bbox[0]  # the text starts right of the icon
    assert cleaned.bbox[1:] == glued.bbox[1:]
    assert out[1] is plain  # untouched tokens are passed through


def test_union_bbox() -> None:
    assert union_bbox([(1, 5, 3, 6), (0, 7, 2, 9)]) == (0, 5, 3, 9)


def test_empty_input() -> None:
    assert group_lines([]) == []
    assert clean_tokens([]) == []
