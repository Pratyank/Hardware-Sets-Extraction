"""Drawn rules: capture in ingest, vector strike detection, and rule-based row separation."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from hwsets.ingest.pdf import apply_drawn_strikes, extract_document_with_rules
from hwsets.layout.rules import RuleIndex, drop_strike_strokes
from hwsets.models import Line, Rule, Token


def _tok(text: str, bbox: tuple[float, float, float, float]) -> Token:
    return Token(id=f"p1_w{abs(hash(text)) % 1000}", page=1, text=text, bbox=bbox,
                 font_size=10, bold=False, block=0, line=0)  # fmt: skip


def _line(lid: str, y0: float, y1: float, x0: float = 50, x1: float = 500) -> Line:
    return Line(id=lid, page=1, token_ids=[], bbox=(x0, y0, x1, y1), text="")


def test_vector_strike_through_middle_marks_token() -> None:
    tok = _tok("BES", (100, 100, 120, 110))
    strike = Rule(bbox=(98, 104.8, 122, 105.4), horizontal=True)
    assert apply_drawn_strikes([tok], [strike])[0].strike


def test_underline_and_row_border_do_not_strike() -> None:
    tok = _tok("SCH", (100, 100, 120, 110))
    underline = Rule(bbox=(98, 109.5, 122, 110.0), horizontal=True)
    border_above = Rule(bbox=(40, 98.0, 560, 98.5), horizontal=True)
    short = Rule(bbox=(100, 105, 104, 105.5), horizontal=True)  # covers < 60% of the word
    out = apply_drawn_strikes([tok], [underline, border_above, short])
    assert not out[0].strike


def test_rule_index_separates_rows_only_across_a_border() -> None:
    upper, lower = _line("L1_0", 100, 108), _line("L1_1", 112, 120)
    ruled = RuleIndex({1: [Rule(bbox=(40, 109.8, 560, 110.2), horizontal=True)]})
    plain = RuleIndex({1: []})
    assert ruled.separated(upper, lower)
    assert not plain.separated(upper, lower)
    # A rule that does not run under the lines (e.g. another table) does not separate them.
    elsewhere = RuleIndex({1: [Rule(bbox=(520, 109.8, 600, 110.2), horizontal=True)]})
    assert not elsewhere.separated(_line("a", 100, 108, 50, 300), _line("b", 112, 120, 50, 300))
    # Lines on different pages are never separated by a rule.
    other = Line(id="L2_0", page=2, token_ids=[], bbox=(50, 112, 500, 120), text="")
    assert not ruled.separated(upper, other)


def test_ingest_captures_table_rules(tmp_path: Path) -> None:
    pdf = tmp_path / "table.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 100), "HINGE", fontname="helv", fontsize=9)
    page.draw_line((50, 104), (560, 104), color=(0, 0, 0), width=0.5)  # row border
    page.draw_line((50, 90), (50, 120), color=(0, 0, 0), width=0.5)  # column border
    doc.save(pdf)
    doc.close()
    _, tokens, rules = extract_document_with_rules(pdf)
    hz = [r for r in rules[0] if r.horizontal]
    vt = [r for r in rules[0] if not r.horizontal]
    assert len(hz) == 1 and len(vt) == 1
    assert not tokens[0][0].strike  # the border under the word is not a strike


def test_strike_strokes_are_not_table_borders() -> None:
    struck = Token(id="p1_w0", page=1, text="NIGHT", bbox=(136.0, 446.6, 170.0, 457.6),
                   font_size=10.0, bold=False, block=0, line=0, strike=True)  # fmt: skip
    stroke = Rule(bbox=(136.0, 452.6, 170.0, 452.6), horizontal=True)
    border = Rule(bbox=(72.0, 460.0, 540.0, 460.0), horizontal=True)
    assert drop_strike_strokes([stroke, border], [struck]) == [border]
    assert drop_strike_strokes([stroke], []) == [stroke]
