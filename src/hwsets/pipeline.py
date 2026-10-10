"""Orchestrates the pure stages: tokens -> DocumentResult.

    tokens ─► clean ─► lines ─► hardware pages (header-driven) ─► chrome removal ─► stream
          ─► set spans ─► line kinds ─► column layouts ─► roles (Hungarian) ─► rows ─► components
          ─► validation + confidence

No I/O here: callers (``cli.py``, ``api/``) load tokens and write results.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hwsets.columns.assign import assign_roles
from hwsets.columns.features import column_features
from hwsets.columns.legend import Legend, find_legend
from hwsets.components.parse import ColumnModel, parse_rows
from hwsets.layout.chrome import chrome_keys, header_row_roles, is_chrome
from hwsets.layout.columns import Layout, column_of, infer_layouts, layout_for_page
from hwsets.layout.lines import clean_tokens, group_lines, union_bbox
from hwsets.models import (
    Component,
    DocumentResult,
    Field,
    HardwareSet,
    Line,
    Location,
    PageInfo,
    PageRegion,
    Token,
)
from hwsets.segment.headers import NOT_USED_RE, HeaderParse
from hwsets.segment.section import find_hardware_pages
from hwsets.segment.sets import Kind, Span, classify, split_spans
from hwsets.validate import validate_document

_CHROME_CONTEXT_PAGES = 3
_LEGEND_LOOKBACK_PAGES = 6


def normalize_set_number(raw: str) -> str:
    """Display form: strip leading zeros of numeric runs ("001" -> "1", "EX-01.0" -> "EX-1.0")."""
    text = re.sub(r"\s+", " ", raw.strip().upper())
    return re.sub(r"(?<![0-9.])0+(?=\d)", "", text)


@dataclass(slots=True)
class _Doc:
    toks: dict[str, Token]
    lines_by_page: dict[int, list[Line]]
    heights: dict[int, float]


def _prepare(pages: Sequence[PageInfo], tokens_by_page: Mapping[int, Sequence[Token]]) -> _Doc:
    toks: dict[str, Token] = {}
    lines_by_page: dict[int, list[Line]] = {}
    for info in pages:
        cleaned = clean_tokens(tokens_by_page.get(info.page, []))
        toks.update({t.id: t for t in cleaned})
        lines_by_page[info.page] = group_lines(cleaned)
    return _Doc(toks, lines_by_page, {p.page: p.height for p in pages})


def _layout_model(
    layout: Layout, spans: Sequence[Span], doc: _Doc, legend: Legend
) -> tuple[ColumnModel, dict[str, str]]:
    xs = tuple(layout.xs)
    pages = set(layout.pages)
    per_col: list[list[str]] = [[] for _ in xs]
    n_rows = 0
    prior: dict[int, str] = {}
    for sp in spans:
        for ln, kind in zip(sp.lines, sp.kinds, strict=True):
            if ln.page not in pages:
                continue
            tokens = [doc.toks[i] for i in ln.token_ids]
            if kind == Kind.COLUMN_HEADER:
                for tok, role in zip(tokens, header_row_roles([t.text for t in tokens]),
                                     strict=False):  # fmt: skip
                    col = column_of(tok.bbox[0], xs)
                    if role and col >= 0 and role != "set_no":
                        prior.setdefault(col, role)
                continue
            if kind != Kind.ROW:
                continue
            n_rows += 1
            cells: dict[int, list[str]] = {}
            for t in tokens:
                col = column_of(t.bbox[0], xs)
                if col >= 0:
                    cells.setdefault(col, []).append(t.text)
            for col, words in cells.items():
                per_col[col].append(" ".join(words))
    feats = [column_features(vals, n_rows, legend.mfr_codes) for vals in per_col]
    ra = assign_roles(feats, prior)
    diag = {
        f"p{layout.pages[0]}-{layout.pages[-1]} x≈{x:.0f}": f"{role} (margin {m:.2f})"
        for x, role, m in zip(xs, ra.roles, ra.margins, strict=True)
    }
    return ColumnModel(xs=xs, roles=ra.roles, margins=ra.margins), diag


def _field_from(tokens: Sequence[str], doc: _Doc, conf: float) -> Field[str]:
    if not tokens:
        return Field[str](value=None, confidence=conf)
    text = " ".join(doc.toks[i].text for i in tokens).strip(" -\u2013:")
    return Field[str](value=text or None, token_ids=list(tokens), confidence=conf)


def _location(lines: Sequence[Line]) -> Location:
    by_page: dict[int, list[Line]] = {}
    for ln in lines:
        by_page.setdefault(ln.page, []).append(ln)
    regions = [
        PageRegion(page=p, bbox=tuple(round(v, 1) for v in union_bbox(ln.bbox for ln in ls)))
        for p, ls in sorted(by_page.items())
    ]
    return Location(regions=regions, line_range=(lines[0].id, lines[-1].id))


def _build_set(
    sp: Span, doc: _Doc, models: Mapping[int, ColumnModel], legend: Legend
) -> tuple[HardwareSet, list[str]]:
    h: HeaderParse = sp.header
    warnings: list[str] = []
    desc_ids = list(h.desc_token_ids)
    status_text: str | None = None
    status = "active"
    header_desc = " ".join(doc.toks[i].text for i in desc_ids)
    m = NOT_USED_RE.search(header_desc)
    if m and len(header_desc.split()) <= 6:
        status, status_text = "not_used", m.group(0)
    set_level: list[str] = []
    row_lines: list[Line] = []
    for ln, kind in zip(sp.lines[1:], sp.kinds[1:], strict=True):
        if kind == Kind.NOT_USED and status == "active":
            status, status_text = "not_used", ln.text.strip()
        elif kind == Kind.DESCRIPTION and not desc_ids:
            ids = list(ln.token_ids)
            if doc.toks[ids[0]].text.lower().startswith("description"):
                ids = ids[1:]
            desc_ids = ids
        elif kind in (Kind.SET_LEVEL, Kind.DESCRIPTION):
            set_level.extend(ln.token_ids)
        elif kind == Kind.ROW:
            row_lines.append(ln)

    components: list[Component] = []
    if status == "active" and row_lines:
        # Rows are parsed per page layout; consecutive same-layout lines go together.
        groups: list[tuple[ColumnModel, list[Line]]] = []
        for ln in row_lines:
            model = models[ln.page]
            if groups and groups[-1][0] is model:
                groups[-1][1].append(ln)
            else:
                groups.append((model, [ln]))
        for model, lines in groups:
            parsed = parse_rows(lines, doc.toks, model, legend)
            components.extend(parsed.components)
            set_level.extend(parsed.set_note_tokens)
            warnings.extend(f"set {sp.set_id}: {w}" for w in parsed.warnings)

    comp_conf = [_component_conf(c) for c in components]
    header_strength = 1.0 if h.bold or h.keyword else 0.9
    conf = (statistics.fmean(comp_conf) if comp_conf else 0.75) * header_strength
    hw = HardwareSet(
        set_number=Field[str](
            value=normalize_set_number(sp.set_id),
            token_ids=list(sp.id_token_ids),
            confidence=0.95,
        ),
        description=_field_from(desc_ids, doc, 0.85),
        status=status,
        status_text=status_text,
        location=_location(sp.lines),
        components=components,
        notes=_field_from(set_level, doc, 0.7),
        confidence=round(min(1.0, conf), 3),
    )
    return hw, warnings


def _component_conf(c: Component) -> float:
    fields = [c.description, c.catalog_number, c.mfr, c.finish]
    vals = [f.confidence for f in fields] + [c.qty.confidence]
    return statistics.fmean(vals)


def extract(
    source_pdf: str, pages: Sequence[PageInfo], tokens_by_page: Mapping[int, Sequence[Token]]
) -> DocumentResult:
    doc = _prepare(pages, tokens_by_page)
    section = find_hardware_pages(doc.lines_by_page, doc.toks)
    warnings = list(section.warnings)
    if not section.pages:
        warnings.append("no hardware set headers found")
        return DocumentResult(source_pdf=source_pdf, hardware_pages=[], column_roles={},
                              sets=[], warnings=warnings)  # fmt: skip

    all_pages = sorted(doc.lines_by_page)
    lo, hi = section.pages[0], section.pages[-1]
    context = [
        p for p in all_pages if lo - _CHROME_CONTEXT_PAGES <= p <= hi + _CHROME_CONTEXT_PAGES
    ]
    header_ids = frozenset(h.line_id for h in section.induction.headers)
    keys = chrome_keys({p: doc.lines_by_page[p] for p in context}, doc.heights, header_ids)

    def body(p: int) -> list[Line]:
        return [
            ln
            for ln in doc.lines_by_page[p]
            if ln.id in header_ids or not is_chrome(ln, doc.heights[p], keys)
        ]

    stream = [ln for p in section.pages for ln in body(p)]
    legend_pages = [p for p in all_pages if lo - _LEGEND_LOOKBACK_PAGES <= p <= hi]
    legend_lines = [ln for p in legend_pages for ln in body(p)]
    legend = find_legend(legend_lines, doc.toks)

    headers = {h.line_id: h for h in section.induction.headers}
    spans = split_spans(stream, headers)
    for sp in spans:
        classify(sp, doc.toks)

    row_lines_by_page: dict[int, list[Line]] = {}
    for sp in spans[::1]:
        for ln, kind in zip(sp.lines, sp.kinds, strict=True):
            if kind == Kind.ROW:
                row_lines_by_page.setdefault(ln.page, []).append(ln)
    # Multi-id headers share lines: count each line once for layout inference.
    for p, ls in row_lines_by_page.items():
        row_lines_by_page[p] = list({ln.id: ln for ln in ls}.values())
    layouts = infer_layouts(row_lines_by_page, doc.toks)
    column_roles: dict[str, str] = {}
    model_by_layout: dict[int, ColumnModel] = {}
    for li, lay in enumerate(layouts):
        model, diag = _layout_model(lay, spans, doc, legend)
        model_by_layout[li] = model
        column_roles.update(diag)
    models: dict[int, ColumnModel] = {}
    empty = ColumnModel(xs=(), roles=(), margins=())
    for p in section.pages:
        page_layout = layout_for_page(layouts, p)
        models[p] = (
            model_by_layout[layouts.index(page_layout)] if page_layout is not None else empty
        )

    sets: list[HardwareSet] = []
    for sp in spans:
        hw, w = _build_set(sp, doc, models, legend)
        sets.append(hw)
        warnings.extend(w)
    result = DocumentResult(
        source_pdf=source_pdf,
        hardware_pages=section.pages,
        column_roles=column_roles,
        sets=sets,
        warnings=warnings,
    )
    return validate_document(result, doc.toks)
