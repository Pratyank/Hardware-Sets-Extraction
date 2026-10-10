"""PDF -> tokens with bounding boxes and typography (PyMuPDF).

Words come from ``page.get_text("words")``; font size and bold come from the spans of
``page.get_text("dict")`` and are joined onto words by bounding-box overlap. All boxes are
normalized to the page *as displayed* (rotation applied), so they line up with rendered PNGs.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from hwsets.ingest import ocr
from hwsets.models import BBox, PageInfo, Token

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


def extract_document(path: Path) -> tuple[list[PageInfo], list[list[Token]]]:
    """Tokenize every page. Pages with almost no text but with images go through OCR."""
    pages: list[PageInfo] = []
    per_page: list[list[Token]] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            tokens = page_tokens(page)
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
    return pages, per_page
