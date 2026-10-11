"""PDF -> tokens with bounding boxes and typography (PyMuPDF).

Words come from ``page.get_text("words")``; font size and bold come from the spans of
``page.get_text("dict")`` and are joined onto words by bounding-box overlap. All boxes are
normalized to the page *as displayed* (rotation applied), so they line up with rendered PNGs.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from hwsets.ingest import ocr
from hwsets.models import BBox, PageInfo, Rule, Token

log = logging.getLogger(__name__)

# Same flags for "words" and "dict" so block/line numbering agrees between the two.
_TEXT_FLAGS = (
    pymupdf.TEXT_PRESERVE_LIGATURES | pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP
)
# Styles are collected only for "dict": it marks strikeout per span (char_flags bit 0).
_DICT_FLAGS = _TEXT_FLAGS | pymupdf.TEXT_COLLECT_STYLES
_BOLD_FLAG = 16  # span["flags"] bit 4
_STRIKEOUT_FLAG = 1  # span["char_flags"] bit 0 (MuPDF FZ_STEXT_STRIKEOUT)
OCR_MIN_WORDS = 5


@dataclass(frozen=True, slots=True)
class _Span:
    bbox: BBox
    size: float
    bold: bool
    strike: bool


def _overlap(a: BBox, b: BBox) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _spans_by_line(page: pymupdf.Page) -> dict[tuple[int, int], list[_Span]]:
    out: dict[tuple[int, int], list[_Span]] = {}
    data = page.get_text("dict", flags=_DICT_FLAGS)
    for b_no, block in enumerate(data["blocks"]):
        if block.get("type", 0) != 0:
            continue
        for l_no, line in enumerate(block["lines"]):
            for span in line["spans"]:
                font = str(span.get("font", ""))
                bold = bool(int(span.get("flags", 0)) & _BOLD_FLAG) or "bold" in font.lower()
                strike = bool(int(span.get("char_flags", 0)) & _STRIKEOUT_FLAG)
                out.setdefault((b_no, l_no), []).append(
                    _Span(
                        bbox=tuple(span["bbox"]),
                        size=float(span["size"]),
                        bold=bold,
                        strike=strike,
                    )
                )
    return out


def _best_span(bbox: BBox, candidates: Iterable[_Span]) -> _Span | None:
    best: _Span | None = None
    best_area = 0.0
    for span in candidates:
        area = _overlap(bbox, span.bbox)
        if area > best_area:
            best, best_area = span, area
    return best


def _display_bbox(bbox: BBox, page: pymupdf.Page) -> BBox:
    """Map an unrotated-page bbox to displayed-page coordinates, clamped to the page."""
    rect = pymupdf.Rect(bbox) * page.rotation_matrix
    rect.normalize()
    bounds = page.rect  # displayed size
    x0 = min(max(rect.x0, bounds.x0), bounds.x1)
    y0 = min(max(rect.y0, bounds.y0), bounds.y1)
    x1 = min(max(rect.x1, bounds.x0), bounds.x1)
    y1 = min(max(rect.y1, bounds.y0), bounds.y1)
    return (round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2))


def page_tokens(
    page: pymupdf.Page, *, page_no: int | None = None, is_ocr: bool = False
) -> list[Token]:
    """Extract tokens for one page in PyMuPDF reading order with stable ids ``p{n}_w{i}``."""
    page_no = page_no if page_no is not None else page.number + 1
    spans = _spans_by_line(page)
    all_spans = [s for group in spans.values() for s in group]
    words = page.get_text("words", flags=_TEXT_FLAGS, sort=True)
    tokens: list[Token] = []
    for x0, y0, x1, y1, word, b_no, l_no, _w_no in words:
        text = str(word).strip()
        if not text:
            continue
        raw: BBox = (float(x0), float(y0), float(x1), float(y1))
        span = _best_span(raw, spans.get((int(b_no), int(l_no)), ())) or _best_span(raw, all_spans)
        tokens.append(
            Token(
                id=f"p{page_no}_w{len(tokens)}",
                page=page_no,
                text=text,
                bbox=_display_bbox(raw, page),
                font_size=round(span.size, 2) if span else round(raw[3] - raw[1], 2),
                bold=span.bold if span else False,
                strike=span.strike if span else False,
                block=int(b_no),
                line=int(l_no),
                ocr=is_ocr,
            )
        )
    return tokens


_RULE_THICK = 1.6  # max thickness (pt) of a drawn line
_RULE_MIN_LEN = 6.0
_MAX_RULES_PER_PAGE = 4000


def _segments(page: pymupdf.Page) -> list[BBox]:
    """Every drawn straight stroke or rectangle, in displayed-page coordinates."""
    try:
        drawings = page.get_drawings()
    except Exception:  # malformed content streams must not stop ingest
        log.warning("could not read drawings on page %d", page.number + 1)
        return []
    out: list[BBox] = []
    for d in drawings:
        for item in d.get("items", ()):
            kind = item[0]
            if kind == "l":
                p1, p2 = item[1], item[2]
                raw: BBox = (min(p1.x, p2.x), min(p1.y, p2.y), max(p1.x, p2.x), max(p1.y, p2.y))
            elif kind == "re":
                r = item[1]
                raw = (r.x0, r.y0, r.x1, r.y1)
            else:
                continue
            out.append(_display_bbox(raw, page))
    return out


def page_rules(page: pymupdf.Page, segments: Sequence[BBox] | None = None) -> list[Rule]:
    """Thin horizontal / vertical drawn lines (strokes or filled hairline rectangles)."""
    rules: list[Rule] = []
    for bbox in _segments(page) if segments is None else segments:
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if h <= _RULE_THICK and w >= _RULE_MIN_LEN:
            rules.append(Rule(bbox=bbox, horizontal=True))
        elif w <= _RULE_THICK and h >= _RULE_MIN_LEN:
            rules.append(Rule(bbox=bbox, horizontal=False))
        if len(rules) >= _MAX_RULES_PER_PAGE:
            break
    return rules


def strike_strokes(segments: Sequence[BBox]) -> list[BBox]:
    """Thin horizontal strokes of any length: candidate strike lines (a single struck digit has
    a stroke shorter than any table rule)."""
    return [b for b in segments if b[3] - b[1] <= _RULE_THICK and b[2] - b[0] >= 1.0]


def apply_drawn_strikes(tokens: list[Token], rules: list[Rule]) -> list[Token]:
    """Mark tokens crossed by a horizontal line through their middle band as struck.

    Some redlines draw the strike as a vector line instead of a font strikeout flag. Table borders
    run between rows and underlines sit at the baseline, so neither crosses the middle band.
    """
    hz = [r for r in rules if r.horizontal]
    if not hz:
        return tokens
    out: list[Token] = []
    for t in tokens:
        out.append(t.model_copy(update={"strike": True}) if _crossed(t, hz) else t)
    return out


def _crossed(t: Token, hz: list[Rule]) -> bool:
    if t.strike:
        return False
    x0, y0, x1, y1 = t.bbox
    h = y1 - y0
    lo, hi = y0 + 0.3 * h, y0 + 0.72 * h
    for r in hz:
        ry = (r.bbox[1] + r.bbox[3]) / 2
        cover = min(x1, r.bbox[2]) - max(x0, r.bbox[0])
        if lo <= ry <= hi and cover >= 0.6 * (x1 - x0):
            return True
    return False


def reconcile_strikes(tokens: Sequence[Token], strokes: Sequence[BBox]) -> list[Token]:
    """Clear a font strikeout flag that the drawn strike strokes contradict.

    MuPDF's strikeout flag is set per span by its own heuristic, and it can flag a neighbour of the
    struck text (the bold ``2`` in ``2 (1)``, where only ``(1)`` is crossed). ``strokes`` holds
    every thin horizontal stroke on the page, however short. When a stroke runs through this
    token's middle band right beside it but none crosses the token itself, the strike belongs to
    the neighbour and the flag is cleared. Tokens with no stroke nearby are left as flagged.
    """
    if not strokes:
        return list(tokens)
    return [
        t.model_copy(update={"strike": False}) if _strike_contradicted(t, strokes) else t
        for t in tokens
    ]


def _strike_contradicted(t: Token, strokes: Sequence[BBox]) -> bool:
    if not t.strike:
        return False
    x0, y0, x1, y1 = t.bbox
    h, w = y1 - y0, max(x1 - x0, 0.1)
    lo, hi = y0 + 0.3 * h, y0 + 0.72 * h
    near = [
        b
        for b in strokes
        if lo <= (b[1] + b[3]) / 2 <= hi and b[0] - x1 < 0.6 * h and x0 - b[2] < 0.6 * h
    ]
    if not near:
        return False
    return max(min(x1, b[2]) - max(x0, b[0]) for b in near) < 0.2 * w


def extract_document(path: Path) -> tuple[list[PageInfo], list[list[Token]]]:
    """Tokenize every page (see ``extract_document_with_rules``)."""
    pages, tokens, _rules = extract_document_with_rules(path)
    return pages, tokens


def extract_document_with_rules(
    path: Path,
) -> tuple[list[PageInfo], list[list[Token]], list[list[Rule]]]:
    """Tokenize every page and collect its drawn rules. Pages with almost no text but with
    images go through OCR. Tokens crossed by a drawn strike line are flagged ``strike``."""
    pages: list[PageInfo] = []
    per_page: list[list[Token]] = []
    per_page_rules: list[list[Rule]] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            segments = _segments(page)
            rules = page_rules(page, segments)
            tokens = apply_drawn_strikes(page_tokens(page), rules)
            tokens = reconcile_strikes(tokens, strike_strokes(segments))
            has_images = bool(page.get_images(full=False))
            used_ocr = False
            if len(tokens) < OCR_MIN_WORDS and has_images:
                ocr_pdf = ocr.ocr_page_pdf(path, page.number)
                if ocr_pdf is not None:
                    with pymupdf.open(stream=ocr_pdf, filetype="pdf") as ocr_doc:
                        tokens = page_tokens(ocr_doc[0], page_no=page.number + 1, is_ocr=True)
                    used_ocr = True
            rect = page.rect
            pages.append(
                PageInfo(
                    page=page.number + 1,
                    width=round(rect.width, 2),
                    height=round(rect.height, 2),
                    rotation=page.rotation,
                    n_tokens=len(tokens),
                    has_images=has_images,
                    ocr=used_ocr,
                )
            )
            per_page.append(tokens)
            per_page_rules.append(rules)
    return pages, per_page, per_page_rules
