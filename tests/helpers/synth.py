"""Synthetic token builder: textual table specs -> Tokens with realistic geometry.

A row spec is ``(text, opts)``. ``text`` is split on ``|`` into cells, cell ``i`` starting at
``col_x[i]`` (an empty cell is skipped, so ``"||WRAPPED TEXT"`` puts text in column 2). Text with
no ``|`` is one cell starting at ``col_x[0]`` (or ``opts["x"]``). Words inside a cell are laid out
left to right with a single-space gap, using an average glyph width of half the font size.

Row options:

* ``bold`` (bool), ``size`` (font size, default 9), ``strike`` (bool)
* ``x``: start x for a single-cell row (overrides ``col_x[0]``)
* ``gap``: extra vertical space before the row, in points
* ``y``: absolute top y (overrides the running cursor)

Token ids are ``p{page}_w{i}`` in reading order, exactly as the ingest stage produces them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from hwsets import pipeline
from hwsets.layout.lines import group_lines
from hwsets.models import DocumentResult, Line, PageInfo, Token

PAGE_W = 612.0
PAGE_H = 792.0
DEFAULT_SIZE = 9.0
ROW_STEP = 14.0
TOP_Y = 110.0
# qty, unit, description, catalog, finish, mfr
COL_X: tuple[float, ...] = (72.0, 100.0, 140.0, 270.0, 450.0, 500.0)

RowSpec = tuple[str, Mapping[str, Any]]


def char_w(size: float) -> float:
    return 0.5 * size


@dataclass(slots=True)
class SynthPage:
    info: PageInfo
    tokens: list[Token]
    # token ids of each input row, in input order (a row may have no tokens if text was blank)
    row_token_ids: list[list[str]] = field(default_factory=list)

    @property
    def toks(self) -> dict[str, Token]:
        return {t.id: t for t in self.tokens}

    def lines(self) -> list[Line]:
        return group_lines(self.tokens)


def _words(
    *,
    page: int,
    row: int,
    start_index: int,
    text: str,
    x: float,
    y: float,
    opts: Mapping[str, Any],
) -> list[Token]:
    """Lay out one cell's words. Each row is its own PyMuPDF line (``line=row``)."""
    size = float(opts.get("size", DEFAULT_SIZE))
    out: list[Token] = []
    cw = char_w(size)
    for w in text.split():
        x1 = x + len(w) * cw
        out.append(
            Token(
                id=f"p{page}_w{start_index + len(out)}",
                page=page,
                text=w,
                bbox=(round(x, 2), round(y, 2), round(x1, 2), round(y + size, 2)),
                font_size=size,
                bold=bool(opts.get("bold", False)),
                block=0,
                line=row,
                strike=bool(opts.get("strike", False)),
            )
        )
        x = x1 + cw
    return out


def make_page(
    page: int,
    rows: Sequence[RowSpec | str],
    col_x: Sequence[float] = COL_X,
    *,
    top: float = TOP_Y,
    step: float = ROW_STEP,
    height: float = PAGE_H,
    width: float = PAGE_W,
) -> SynthPage:
    """Build one page of tokens from row specs (a bare string is ``(text, {})``)."""
    tokens: list[Token] = []
    row_ids: list[list[str]] = []
    y = top
    for ri, spec in enumerate(rows):
        text, opts = (spec, {}) if isinstance(spec, str) else spec
        y += float(opts.get("gap", 0.0))
        if "y" in opts:
            y = float(opts["y"])
        cells = text.split("|") if "|" in text else [text]
        ids: list[str] = []
        for ci, cell in enumerate(cells):
            if not cell.strip():
                continue
            x = float(opts["x"]) if ("x" in opts and len(cells) == 1) else float(col_x[ci])
            new = _words(page=page, row=ri, start_index=len(tokens), text=cell, x=x, y=y, opts=opts)
            tokens.extend(new)
            ids.extend(t.id for t in new)
        row_ids.append(ids)
        y += step
    info = PageInfo(
        page=page, width=width, height=height, rotation=0, n_tokens=len(tokens), has_images=False
    )
    return SynthPage(info=info, tokens=tokens, row_token_ids=row_ids)


def tok(
    tid: str,
    text: str,
    bbox: tuple[float, float, float, float],
    *,
    page: int = 1,
    size: float = DEFAULT_SIZE,
    bold: bool = False,
    block: int = 0,
    line: int = 0,
    strike: bool = False,
) -> Token:
    """One hand-placed token."""
    return Token(
        id=tid,
        page=page,
        text=text,
        bbox=bbox,
        font_size=size,
        bold=bold,
        block=block,
        line=line,
        strike=strike,
    )


def line_of(
    text: str,
    *,
    page: int = 1,
    x: float = 72.0,
    y: float = 100.0,
    bold: bool = False,
    size: float = DEFAULT_SIZE,
) -> tuple[Line, dict[str, Token]]:
    """A single line (and its token map) from plain text; handy for parser unit tests."""
    sp = make_page(page, [(text, {"bold": bold, "size": size, "x": x, "y": y})])
    lines = sp.lines()
    assert len(lines) == 1, lines
    return lines[0], sp.toks


def doc_inputs(pages: Sequence[SynthPage]) -> tuple[list[PageInfo], dict[int, list[Token]]]:
    return [p.info for p in pages], {p.info.page: p.tokens for p in pages}


def run(pages: Sequence[SynthPage], source_pdf: str = "synthetic.pdf") -> DocumentResult:
    infos, by_page = doc_inputs(pages)
    return pipeline.extract(source_pdf, infos, by_page)


def all_tokens(pages: Sequence[SynthPage]) -> dict[str, Token]:
    return {t.id: t for p in pages for t in p.tokens}


def set_numbers(result: DocumentResult) -> list[str | None]:
    return [s.set_number.value for s in result.sets]


def component_tuples(result: DocumentResult) -> list[list[tuple[Any, ...]]]:
    """Per set, the plain field values of each component (qty, unit, desc, cat, finish, mfr)."""
    return [
        [
            (
                c.qty.value,
                c.qty_unit,
                c.description.value,
                c.catalog_number.value,
                c.finish.value,
                c.mfr.value,
            )
            for c in s.components
        ]
        for s in result.sets
    ]
