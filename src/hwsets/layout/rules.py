"""Drawn table rules as row boundaries.

In a ruled table every row is closed by a horizontal border, while a wrapped cell's second
line is not. So "is there a horizontal rule between these two lines, under both of them?" is an
exact row-boundary test where rules exist, and a no-op where they do not.

Pure functions of lines and rules.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hwsets.models import Line, Rule, Token

_MIN_OVERLAP = 0.3  # the rule must run under this share of the narrower line
_MIN_ROW_RULES = 6


class RuleIndex:
    def __init__(self, rules_by_page: Mapping[int, Sequence[Rule]]) -> None:
        self._hz = {
            p: sorted((r for r in rules if r.horizontal), key=lambda r: r.bbox[1])
            for p, rules in rules_by_page.items()
        }

    def has_rules(self, page: int) -> bool:
        return bool(self._hz.get(page))

    def row_ruled(self, page: int) -> bool:
        """A ruled table: many long horizontal rules (row borders), not a few boxes or strikes."""
        hz = self._hz.get(page, ())
        if not hz:
            return False
        span = max(r.bbox[2] for r in hz) - min(r.bbox[0] for r in hz)
        wide = sum(1 for r in hz if r.bbox[2] - r.bbox[0] >= 0.5 * span and span > 100)
        return wide >= _MIN_ROW_RULES

    def separated(self, upper: Line, lower: Line) -> bool:
        """True when a horizontal rule runs between ``upper`` and ``lower`` (same page)."""
        if upper.page != lower.page:
            return False
        top, bottom = upper.bbox[3] - 1.0, lower.bbox[1] + 1.0
        if bottom <= top:
            return False
        left = max(upper.bbox[0], lower.bbox[0])
        right = min(upper.bbox[2], lower.bbox[2])
        narrow = max(min(upper.bbox[2] - upper.bbox[0], lower.bbox[2] - lower.bbox[0]), 1.0)
        for r in self._hz.get(upper.page, ()):
            y = (r.bbox[1] + r.bbox[3]) / 2
            if y < top:
                continue
            if y > bottom:
                break
            overlap = min(right, r.bbox[2]) - max(left, r.bbox[0])
            if overlap >= _MIN_OVERLAP * narrow:
                return True
        return False


EMPTY_RULES = RuleIndex({})


def drop_strike_strokes(rules: Sequence[Rule], tokens: Sequence[Token]) -> list[Rule]:
    """Remove horizontal rules that run through the middle of words: those are strike-throughs of
    deleted text, not table borders (borders run between lines). Left in, the stroke through a
    struck-out line reads as a border and splits the row it sits in."""
    struck = [t for t in tokens if t.strike]  # ingest flags every word a stroke crosses
    if not struck:
        return list(rules)
    out: list[Rule] = []
    for r in rules:
        if r.horizontal and any(_strikes(r, t) for t in struck):
            continue
        out.append(r)
    return out


def _strikes(r: Rule, t: Token) -> bool:
    x0, y0, x1, y1 = t.bbox
    h = y1 - y0
    ry = (r.bbox[1] + r.bbox[3]) / 2
    if not (y0 + 0.3 * h <= ry <= y0 + 0.72 * h):
        return False
    return min(x1, r.bbox[2]) - max(x0, r.bbox[0]) >= 0.5 * (x1 - x0)
