"""Row rhythm: telling rows apart by vertical spacing when nothing else separates them.

Many unruled schedules print a wrapped cell with tighter leading than the pitch between rows:

    1 Fail Safe Exit Device, RX      [12] 55 PE8875 ETMI   Sargent     <- row
      Surface Closer (Mounted on stairwell                             <- 14.5 pt below: new row
    1                                7500                  Norton      <- centred qty / cells
      side of door)                                                    <- 11.5 pt below the
                                                                          cell's first line: wrap

When a layout shows two clearly separated spacings, a line that sits a full row pitch below the
previous line starts a new block (a new row, or a remark) rather than continuing the row above.

The two spacings are measured per layout from the document itself:

* row pitch: the median top-to-top distance between adjacent quantity-led rows;
* wrap leading: the median distance between consecutive lines of the same column where the lower
  line does not start a row, keeping only lines inside an item table (between its first and last
  quantity row) so prose paragraphs, often set in a smaller size, do not count.

Layouts without two distinct spacings get no threshold and keep the other row rules unchanged.

Pure functions.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from hwsets.models import Line, Token

_LONE_INT_RE = re.compile(r"^\d{1,4}$")
_MIN_ROW_SAMPLES = 5
_MIN_WRAP_SAMPLES = 3
_MIN_RATIO = 1.12  # row pitch must exceed wrap leading by at least this factor
_MAX_LINES_PER_ROW = 2.2  # beyond this, rows hold paragraphs rather than wrapped cells
_MAX_BLOCK_GAP = 1.5  # a gap well beyond one row pitch is a hole (struck lines removed), not a row

RoleOf = Callable[[Token], str]
StartsRow = Callable[[Line], bool]


@dataclass(frozen=True, slots=True)
class Rhythm:
    """A layout's two line spacings (pt, top to top)."""

    leading: float  # between wrapped lines of one cell
    pitch: float  # between rows

    @property
    def gap(self) -> float:
        """Distances at or above this open a new block."""
        return (self.leading + self.pitch) / 2


def _value_cols(ln: Line, toks: Mapping[str, Token], role_of: RoleOf) -> set[str]:
    """Columns this line has text in, ignoring a lone integer (a centred quantity)."""
    out: set[str] = set()
    for i in ln.token_ids:
        tok = toks[i]
        role = role_of(tok)
        if role in {"ignore", "left"} or _LONE_INT_RE.match(tok.text):
            continue
        out.add(role)
    return out


def estimate_rhythm(
    sets: Sequence[Sequence[Line]],
    toks: Mapping[str, Token],
    role_of: RoleOf,
    starts_row: StartsRow,
) -> Rhythm | None:
    """A layout's wrap leading and row pitch, or None unless they are clearly distinct."""
    pitches: list[float] = []
    wraps: list[float] = []
    n_lines = n_rows = 0
    for lines in sets:
        starts = [starts_row(ln) for ln in lines]
        if sum(starts) < 2:
            continue
        first = starts.index(True)
        last = len(starts) - 1 - starts[::-1].index(True)
        n_lines += last - first + 1
        n_rows += sum(starts)
        for a, b, sa, sb in zip(lines, lines[1:], starts, starts[1:], strict=False):
            if a.page == b.page and sa and sb:
                pitches.append(b.bbox[1] - a.bbox[1])
        last_top: dict[str, tuple[int, float]] = {}
        for k in range(first, last + 1):
            ln = lines[k]
            for col in _value_cols(ln, toks, role_of):
                prev = last_top.get(col)
                if prev is not None and prev[0] == ln.page and not starts[k]:
                    wraps.append(ln.bbox[1] - prev[1])
                last_top[col] = (ln.page, ln.bbox[1])
    if len(pitches) < _MIN_ROW_SAMPLES:
        return None
    if n_lines > _MAX_LINES_PER_ROW * n_rows:
        # Paragraph cells: spacing between a cell's paragraphs matches the row pitch, so
        # spacing cannot tell rows apart.
        return None
    pitch = statistics.median(pitches)
    # Keep plausible wrap distances: below the row pitch, and not the half-steps of a centred cell.
    tight = [d for d in wraps if 0.6 * pitch < d < 0.93 * pitch]
    if len(tight) < _MIN_WRAP_SAMPLES:
        return None
    leading = statistics.median(tight)
    if pitch < _MIN_RATIO * leading:
        return None
    return Rhythm(leading=round(leading, 2), pitch=round(pitch, 2))


def opens_block(prev: Line | None, ln: Line, rhythm: Rhythm | None) -> bool:
    """Does ``ln`` sit about one row pitch below ``prev`` on the same page? A much larger gap is
    a hole left by removed (struck) lines, so it is not evidence either way."""
    if rhythm is None or prev is None or prev.page != ln.page:
        return False
    delta = ln.bbox[1] - prev.bbox[1]
    return rhythm.gap <= delta <= _MAX_BLOCK_GAP * rhythm.pitch


def in_block(prev: Line | None, ln: Line, rhythm: Rhythm | None) -> bool:
    """Does ``ln`` follow ``prev`` closer than a row pitch (a wrap within the same block)?"""
    if rhythm is None or prev is None or prev.page != ln.page:
        return False
    return ln.bbox[1] - prev.bbox[1] < rhythm.gap


def block_cols(
    lines: Sequence[Line],
    idx: int,
    *,
    toks: Mapping[str, Token],
    role_of: RoleOf,
    starts_row: StartsRow,
    rhythm: Rhythm,
) -> set[str]:
    """Columns filled by the block that ``lines[idx]`` opens: it and the following lines up to
    the next row start or the next full row pitch."""
    cols = _value_cols(lines[idx], toks, role_of)
    for k in range(idx + 1, len(lines)):
        a, b = lines[k - 1], lines[k]
        if b.page != a.page or b.bbox[1] - a.bbox[1] >= rhythm.gap or starts_row(b):
            break
        cols |= _value_cols(b, toks, role_of)
    return cols
