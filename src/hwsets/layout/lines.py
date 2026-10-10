"""Tokens -> visual lines.

Tokens are grouped by vertical overlap, so that a line is one horizontal band of text on the page
whatever PyMuPDF's block/line structure says. This matters because wrapped table cells are often
emitted out of reading order. Within a line, tokens are sorted by x.

Pure function of tokens. Struck-through tokens are excluded (they are redline deletions).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from hwsets.models import BBox, Line, Token

# Two tokens share a line when their vertical overlap is at least this fraction of the shorter
# token's height. 0.5 corresponds to the plan's "half the median token height" tolerance for
# tokens of typical size, and stays robust when one token is much taller than the other.
_OVERLAP_FRACTION = 0.5


def union_bbox(boxes: Iterable[BBox]) -> BBox:
    xs0, ys0, xs1, ys1 = zip(*boxes, strict=True)
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def _v_overlap(a: BBox, b: BBox) -> float:
    return min(a[3], b[3]) - max(a[1], b[1])


def _height(b: BBox) -> float:
    return max(b[3] - b[1], 0.1)


def is_glyph_noise(tok: Token) -> bool:
    """Icon glyphs (private-use code points, e.g. cut-sheet/electrified markers) carry no text."""
    return all(0xE000 <= ord(c) <= 0xF8FF or not c.isprintable() for c in tok.text)


def _is_pua(c: str) -> bool:
    return 0xE000 <= ord(c) <= 0xF8FF


def clean_tokens(tokens: Sequence[Token]) -> list[Token]:
    """Drop glyph-only tokens and strip icon glyphs glued to words (``"\uf09d 626"`` -> ``"626"``).

    The bbox is shrunk proportionally to the stripped prefix so column assignment uses where the
    text actually starts. Token ids are kept, so values stay grounded on the original tokens.
    """
    out: list[Token] = []
    for t in tokens:
        if is_glyph_noise(t):
            continue
        text = "".join(c for c in t.text if not _is_pua(c)).strip()
        if text == t.text:
            out.append(t)
            continue
        lead = len(t.text) - len(t.text.lstrip("".join({c for c in t.text if _is_pua(c)} | {" "})))
        x0, y0, x1, y1 = t.bbox
        if lead:
            # Icon glyphs are wider than letters: estimate where the text starts from the right
            # edge and a typical glyph width, not from a share of the characters.
            x0 = max(x0 + (x1 - x0) * lead / len(t.text), x1 - len(text) * 0.6 * t.font_size)
        out.append(t.model_copy(update={"text": text, "bbox": (x0, y0, x1, y1)}))
    return out


def is_rotated_noise(tok: Token) -> bool:
    """Vertical text (margin watermarks, stamps): one glyph wide and several glyphs tall.

    Upright words are wider than tall once they have two or more characters, so a word whose
    box is about one em wide and at least 1.5x taller than wide is running vertically.
    """
    w = tok.bbox[2] - tok.bbox[0]
    h = _height(tok.bbox)
    return len(tok.text) >= 2 and h >= 1.5 * w and w <= 1.3 * max(tok.font_size, 1.0)


def vertical_line_keys(tokens: Sequence[Token]) -> set[tuple[int, int]]:
    """PyMuPDF lines whose words progress downward (rotated text such as margin watermarks)."""
    groups: dict[tuple[int, int], list[Token]] = {}
    for t in tokens:
        groups.setdefault((t.block, t.line), []).append(t)
    out: set[tuple[int, int]] = set()
    for key, toks in groups.items():
        if len(toks) < 2:
            continue
        span_x = max(t.bbox[2] for t in toks) - min(t.bbox[0] for t in toks)
        span_y = max(t.bbox[3] for t in toks) - min(t.bbox[1] for t in toks)
        if span_y > 2.0 * span_x:
            out.add(key)
    return out


def group_lines(tokens: Sequence[Token]) -> list[Line]:
    """Group one page's tokens into visual lines, top to bottom. Ids are ``L{page}_{i}``."""
    live = [t for t in tokens if not t.strike and not is_glyph_noise(t)]
    if not live:
        return []
    vertical = vertical_line_keys(live)
    live = [t for t in live if (t.block, t.line) not in vertical and not is_rotated_noise(t)]
    if not live:
        return []
    live.sort(key=lambda t: ((t.bbox[1] + t.bbox[3]) / 2, t.bbox[0]))

    bands: list[list[Token]] = []
    band_boxes: list[BBox] = []
    for tok in live:
        best, best_ov = -1, 0.0
        # Only recent bands can overlap, since tokens are sorted by vertical centre.
        for i in range(len(bands) - 1, max(len(bands) - 4, -1), -1):
            ov = _v_overlap(tok.bbox, band_boxes[i])
            ratio = ov / min(_height(tok.bbox), _height(band_boxes[i]))
            if ratio >= _OVERLAP_FRACTION and ov > best_ov:
                best, best_ov = i, ov
        if best < 0:
            bands.append([tok])
            band_boxes.append(tok.bbox)
        else:
            bands[best].append(tok)
            # Track the band's core height (median of members) rather than its union, so that a
            # tall outlier does not swallow neighbouring lines.
            b = band_boxes[best]
            band_boxes[best] = (min(b[0], tok.bbox[0]), b[1], max(b[2], tok.bbox[2]), b[3])

    page = live[0].page
    lines: list[Line] = []
    order = sorted(range(len(bands)), key=lambda i: band_boxes[i][1])
    for idx, i in enumerate(order):
        toks = sorted(bands[i], key=lambda t: t.bbox[0])
        lines.append(
            Line(
                id=f"L{page}_{idx}",
                page=page,
                token_ids=[t.id for t in toks],
                bbox=union_bbox(t.bbox for t in toks),
                text=" ".join(t.text for t in toks),
            )
        )
    return lines
