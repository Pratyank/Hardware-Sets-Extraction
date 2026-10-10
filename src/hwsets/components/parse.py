"""Rows -> components.

Row assembly uses the column roles of the page's layout:

* a line with a value in the quantity position starts a new row;
* a line with only description / catalog / finish / notes text directly below a row is a wrapped
  continuation of that row (this is what fixes "STOREROOM LEVER 622 LOCKSET": geometry, not
  PyMuPDF's word order, decides which cell a word belongs to);
* a line starting left of every column, or one unbroken run of words across several columns, is
  prose and goes to the set's notes;
* ``Note:`` / ``Properties:`` sub-lines attach to the row above as notes.

Field rules: quantity only from the quantity position, never defaulted; description and catalog
from their columns (or split at the first model-like token when one cell holds both); manufacturer
and finish from their columns, with codes resolved by the column's role, not by the code alone.

Pure functions.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from hwsets.columns.features import QTY_RE, is_catalog_token
from hwsets.columns.legend import Legend
from hwsets.columns.lexicon import (
    COLLISIONS,
    FINISH_CODES,
    is_finish_value,
    is_mfr_code,
    mfr_name,
    norm_code,
    unit_code,
)
from hwsets.layout.columns import cell_gap, column_of
from hwsets.layout.rules import EMPTY_RULES, RuleIndex
from hwsets.models import Component, Field, Line, Token

_NOTE_RE = re.compile(r"^(?:notes?|properties|note\s*\d*)\s*[:\-]", re.IGNORECASE)
_NUMBERED_NOTE_RE = re.compile(r"^notes?\s*[:\-]?\s*\d+[.)]", re.IGNORECASE)
_INT_RE = re.compile(r"^(\d{1,5})(?:\.0+)?$")
_MFR_SPLIT_RE = re.compile(r"\s[-\u2013]\s")


@dataclass(frozen=True, slots=True)
class ColumnModel:
    """Column anchors and roles for one layout."""

    xs: tuple[float, ...]
    roles: tuple[str, ...]
    margins: tuple[float, ...]
    # The description column also holds model numbers (no catalog column of its own), so a row's
    # description cell is split at its first model-like token.
    split_merged: bool = False
    # Most catalog cells read "MANUFACTURER - PRODUCT" (no manufacturer column): split every
    # such cell at its first " - ", a document-level decision rather than a per-row guess.
    mfr_prefix: bool = False

    def x_of(self, role: str) -> float | None:
        for x, r in zip(self.xs, self.roles, strict=True):
            if r == role:
                return x
        return None

    def role_of(self, tok: Token) -> str:
        col = column_of(tok.bbox[0], self.xs)
        return "left" if col < 0 else self.roles[col]

    def margin_of(self, role: str) -> float:
        for r, m in zip(self.roles, self.margins, strict=True):
            if r == role:
                return m
        return 0.0

    def has(self, role: str) -> bool:
        return role in self.roles


@dataclass(slots=True)
class Row:
    lines: list[Line] = field(default_factory=list)
    cells: dict[str, list[Token]] = field(default_factory=dict)
    note_tokens: list[Token] = field(default_factory=list)
    fit: float = 1.0  # share of tokens that fell in a known column

    def add(self, role: str, tok: Token) -> None:
        self.cells.setdefault(role, []).append(tok)


@dataclass(slots=True)
class ParsedRows:
    components: list[Component]
    set_note_tokens: list[str]
    warnings: list[str]
    set_desc_tokens: list[str] = field(default_factory=list)  # text of a table SET column


def _is_prose(line: Line, toks: Mapping[str, Token], model: ColumnModel) -> bool:
    tokens = [toks[i] for i in line.token_ids]
    if not tokens:
        return False
    if model.xs and tokens[0].bbox[0] < model.xs[0] - 6 and len(tokens) >= 3:
        return True
    gap = cell_gap(tokens)
    gaps = sum(1 for a, b in itertools.pairwise(tokens) if b.bbox[0] - a.bbox[2] > gap)
    cols = {column_of(t.bbox[0], model.xs) for t in tokens}
    return gaps == 0 and len(cols) >= 3 and len(tokens) >= 6


def _starts_row(roles: Sequence[str], tokens: Sequence[Token], model: ColumnModel) -> bool:
    qty_text = " ".join(t.text for t, r in zip(tokens, roles, strict=True) if r == "qty")
    if qty_text:
        # The quantity position must hold a quantity ("3", "1 Ea.", "As Req", "--"), not the
        # tail of a prose sentence that happens to start at the same x.
        return bool(QTY_RE.match(qty_text))
    if not model.has("qty") and tokens and QTY_RE.match(tokens[0].text):
        return bool(_INT_RE.match(tokens[0].text)) and len(tokens) >= 2
    return False


def assemble_rows(
    lines: Sequence[Line],
    toks: Mapping[str, Token],
    model: ColumnModel,
    set_desc: list[str] | None = None,
    rules: RuleIndex = EMPTY_RULES,
) -> tuple[list[Row], list[str]]:
    """Group candidate row lines into logical rows. Returns rows and set-note token ids.

    Tokens in a table's SET column are collected into ``set_desc`` (the set's description).
    """
    rows: list[Row] = []
    set_notes: list[str] = []
    if model.has("set_no"):
        kept: list[Line] = []
        for ln in lines:
            ids = [i for i in ln.token_ids if model.role_of(toks[i]) != "set_no"]
            if set_desc is not None:
                set_desc.extend(i for i in ln.token_ids if model.role_of(toks[i]) == "set_no")
            if ids:
                kept.append(ln.model_copy(update={"token_ids": ids}))
        lines = kept
    last_bottom = 0.0
    last_page = -1
    note_x: float | None = None  # left edge of the note being continued, if any
    note_to_set = False
    pending: list[Line] = []  # fragments of a vertically centred cell, held for the next row
    for idx, ln in enumerate(lines):
        tokens = [toks[i] for i in ln.token_ids]
        if not tokens:
            continue
        x0 = tokens[0].bbox[0]
        roles0 = [model.role_of(t) for t in tokens]
        if _NOTE_RE.match(ln.text):
            # Numbered notes ("Note: 1. ...") are set-level; a plain note belongs to the row above.
            # A note aligned with (or left of) the description column is about the whole set;
            # only a note indented under an item belongs to that item.
            desc_x = model.x_of("description")
            note_to_set = (
                not rows
                or bool(_NUMBERED_NOTE_RE.match(ln.text))
                or (desc_x is not None and x0 <= desc_x + 4)
            )
            note_x = x0
            if note_to_set:
                set_notes.extend(ln.token_ids)
            else:
                rows[-1].note_tokens.extend(tokens)
                rows[-1].lines.append(ln)
            last_bottom, last_page = ln.bbox[3], ln.page
            continue
        if note_x is not None:
            if not _starts_row(roles0, tokens, model) and x0 >= note_x - 3:
                if note_to_set or not rows:
                    set_notes.extend(ln.token_ids)
                else:
                    rows[-1].note_tokens.extend(tokens)
                    rows[-1].lines.append(ln)
                last_bottom, last_page = ln.bbox[3], ln.page
                continue
            note_x = None
        if _is_prose(ln, toks, model):
            set_notes.extend(ln.token_ids)
            continue
        roles = [model.role_of(t) for t in tokens]
        height = ln.bbox[3] - ln.bbox[1]
        near = rows and ln.page == last_page and ln.bbox[1] - last_bottom <= 1.6 * max(height, 6)
        new_page_cont = rows and ln.page != last_page
        value_roles = set(roles) & {"description", "catalog", "finish", "mfr"}
        ruled_break = bool(
            rows and value_roles and rows[-1].lines and rules.separated(rows[-1].lines[-1], ln)
        )
        if (
            _starts_row(roles, tokens, model)
            or (rows and len(value_roles) >= 3)
            or ruled_break  # a drawn table border closes the previous row
        ):
            # A line filling three value columns is a new item even without a quantity
            # ("GASKETING / SWEEP | PEMKO - ... | BLACK"); wrapped cells rarely span three.
            row = Row()
            rows.append(row)
            for frag in pending:  # centred-cell fragments printed above this row's first line
                _add_line(row, frag, toks, model)
            pending = []
        elif rows and _closer_to_next(
            ln, idx, lines=lines, toks=toks, model=model, last_bottom=last_bottom
        ):
            pending.append(ln)
            continue
        elif rows and (near or new_page_cont) and _continuation_ok(rows[-1], roles):
            row = rows[-1]
        elif sum(r in {"description", "catalog", "finish", "mfr"} for r in set(roles)) >= 2:
            row = Row()  # a row printed without a quantity (e.g. "As Req" hinges, blank qty)
            rows.append(row)
        else:
            set_notes.extend(ln.token_ids)
            continue
        _add_line(row, ln, toks, model)
        last_bottom, last_page = ln.bbox[3], ln.page
    if pending and rows:
        for frag in pending:
            _add_line(rows[-1], frag, toks, model)
    return rows, set_notes


def _add_line(row: Row, ln: Line, toks: Mapping[str, Token], model: ColumnModel) -> None:
    tokens = [toks[i] for i in ln.token_ids]
    known = 0
    for tok in tokens:
        role = model.role_of(tok)
        if role in {"ignore", "left"}:
            continue
        known += 1
        row.add(role, tok)
    row.lines.append(ln)
    if tokens:
        row.fit = min(row.fit, known / len(tokens))


def _closer_to_next(
    ln: Line,
    idx: int,
    *,
    lines: Sequence[Line],
    toks: Mapping[str, Token],
    model: ColumnModel,
    last_bottom: float,
) -> bool:
    """A continuation fragment that sits much closer to the next row's first line than to the
    line above belongs to that next row: its cell is vertically centred on the row, so the cell's
    first line is printed above the row's single-line cells (quantity, manufacturer)."""
    if idx + 1 >= len(lines):
        return False
    nxt = lines[idx + 1]
    if nxt.page != ln.page:
        return False
    nxt_tokens = [toks[i] for i in nxt.token_ids]
    nxt_roles = [model.role_of(t) for t in nxt_tokens]
    if not _starts_row(nxt_roles, nxt_tokens, model):
        return False
    gap_prev = max(ln.bbox[1] - last_bottom, 0.0)
    gap_next = max(nxt.bbox[1] - ln.bbox[3], 0.0)
    return gap_next < 0.5 * gap_prev


def _continuation_ok(prev: Row, roles: Sequence[str]) -> bool:
    """A wrapped line adds to cells; it must not bring a second manufacturer."""
    present = set(roles) - {"ignore", "left"}
    if not present:
        return False
    if "mfr" in present and prev.cells.get("mfr"):
        return False
    return not ("finish" in present and prev.cells.get("finish") and "mfr" in present)


def _join(tokens: Sequence[Token]) -> str:
    """Join cell tokens with single spaces, except a code broken across a line wrap at a hyphen
    ("630-" on one line, "316" on the next -> "630-316"). Tokens on the same line always keep
    their space ("W/ KEYFOB", "CORE - COMBINATED")."""
    out = ""
    prev: Token | None = None
    for t in tokens:
        if prev is None:
            out = t.text
        else:
            wrapped = t.bbox[1] >= prev.bbox[3] - 0.25 * (prev.bbox[3] - prev.bbox[1])
            if wrapped and len(prev.text) > 1 and prev.text.endswith("-") and t.text[:1].isalnum():
                out += t.text
            else:
                out += " " + t.text
        prev = t
    return out.strip()


def _field(tokens: Sequence[Token], conf: float) -> Field[str]:
    if not tokens:
        return Field[str](value=None, token_ids=[], confidence=round(conf, 3))
    return Field[str](
        value=_join(tokens), token_ids=[t.id for t in tokens], confidence=round(conf, 3)
    )


def _parse_qty(cell: list[Token]) -> tuple[int | None, str | None, list[Token], list[Token]]:
    """Returns (qty, unit, qty tokens used, unit tokens used). Never guesses a number."""
    qty: int | None = None
    unit: str | None = None
    q_used: list[Token] = []
    u_used: list[Token] = []
    for t in cell:
        m = _INT_RE.match(t.text)
        glued = re.match(r"^(\d{1,5})([A-Za-z]{2,4})\.?$", t.text)  # "2EA"
        if qty is None and m and not q_used:
            qty = int(m.group(1))
            q_used.append(t)
        elif qty is None and glued and unit_code(glued.group(2)):
            qty, unit = int(glued.group(1)), unit_code(glued.group(2))
            q_used.append(t)
            u_used.append(t)
        elif unit is None and unit_code(t.text):
            unit = unit_code(t.text)
            u_used.append(t)
    return qty, unit, q_used, u_used


_REV_TAG_RE = re.compile(
    r"^\[(?:BULLETIN|ADDENDUM|ADD|REV(?:ISION)?|ASI|CCD|PR|RFI|ISSUE)\b[^\]]*\]$", re.IGNORECASE
)


def _pop_revision_tags(tokens: list[Token]) -> tuple[list[Token], list[Token]]:
    """Split off bracketed revision tags (which may span several tokens)."""
    keep: list[Token] = []
    tags: list[Token] = []
    i = 0
    while i < len(tokens):
        if tokens[i].text.startswith("["):
            j = i
            while j < len(tokens) and not tokens[j].text.endswith("]"):
                j += 1
            group = tokens[i : j + 1]
            if j < len(tokens) and _REV_TAG_RE.match(" ".join(t.text for t in group)):
                tags.extend(group)
                i = j + 1
                continue
        keep.append(tokens[i])
        i += 1
    return keep, tags


def is_mfr_prefix(left: str, legend_codes: frozenset[str] = frozenset()) -> bool:
    """ "VON DUPRIN", "PEMKO / NGP / ZERO", "IVES": known manufacturer names joined by / , &."""
    parts = [p for p in re.split(r"[/,&]", left) if p.strip()]
    return (
        bool(parts)
        and len(left.split()) <= 6
        and all(is_mfr_code(p) or norm_code(p) in legend_codes for p in parts)
    )


def _split_desc_catalog(tokens: list[Token]) -> tuple[list[Token], list[Token]]:
    """One cell holding both: the catalog starts at the first model-like token."""
    for i, t in enumerate(tokens):
        if i > 0 and is_catalog_token(t.text):
            return tokens[:i], tokens[i:]
    return tokens, []


def build_component(row: Row, model: ColumnModel, legend: Legend) -> tuple[Component, list[str]]:
    warnings: list[str] = []
    cells = {k: list(v) for k, v in row.cells.items()}
    m_conf = {r: max(0.3, min(1.0, 0.55 + model.margin_of(r))) for r in model.roles}

    # Quantity: the quantity column, or the leading token of the row when qty shares a cell.
    qty_cell = cells.pop("qty", [])
    first_role = next((r for r in ("description", "catalog") if cells.get(r)), None)
    if not qty_cell and first_role and _INT_RE.match(cells[first_role][0].text):
        qty_cell = [cells[first_role].pop(0)]
        if cells[first_role] and unit_code(cells[first_role][0].text):
            qty_cell.append(cells[first_role].pop(0))
    qty, unit, q_used, u_used = _parse_qty(qty_cell)
    unit_tokens = u_used or cells.pop("unit", [])
    if unit is None and unit_tokens:
        unit = unit_code(" ".join(t.text for t in unit_tokens)) or _join(unit_tokens).upper()
    qty_field = Field[int | str](
        value=qty,
        token_ids=[t.id for t in q_used],
        confidence=0.95 if qty is not None else 0.8,
    )

    desc = cells.get("description", [])
    cat = cells.get("catalog", [])
    if desc and not cat and not model.has("catalog") and model.split_merged:
        desc, cat = _split_desc_catalog(desc)
    elif cat and not desc and not model.has("description"):
        desc, cat = _split_desc_catalog(cat)

    mfr = cells.get("mfr", [])
    # "IVES - 5BB1 4.5 x 4.5": manufacturer and catalog share one cell (no manufacturer column).
    if not mfr and not model.has("mfr") and cat:
        text = _join(cat)
        m = _MFR_SPLIT_RE.search(text)
        if m:
            left = text[: m.start()]
            if model.mfr_prefix or is_mfr_prefix(left, legend.mfr_codes):
                n_left = len(left.split())
                mfr, cat = cat[:n_left], [t for t in cat[n_left:] if t.text not in {"-", "\u2013"}]

    finish = cells.get("finish", [])
    # Revision tags ("[BULLETIN 023, 251218]") annotate the row; they are not part of a value.
    desc, tag_d = _pop_revision_tags(desc)
    cat, tag_c = _pop_revision_tags(cat)
    notes = cells.get("notes", []) + tag_d + tag_c + row.note_tokens

    mfr_text = _join(mfr) if mfr else None
    mfr_resolved = None
    mfr_conf = m_conf.get("mfr", 0.5)
    if mfr_text:
        code = norm_code(mfr_text)
        if code in legend.mfr:
            mfr_resolved = legend.mfr[code].name
            mfr_conf = min(1.0, mfr_conf + 0.15)
        elif mfr_name(mfr_text):
            mfr_resolved = mfr_name(mfr_text)
            mfr_conf = min(1.0, mfr_conf + (0.0 if code in COLLISIONS else 0.1))
        else:
            mfr_conf *= 0.85
            if code in FINISH_CODES:
                warnings.append(f"finish-like code {mfr_text!r} in manufacturer column")
    fin_conf = m_conf.get("finish", 0.5)
    if finish:
        fin_text = _join(finish)
        fin_conf = min(1.0, fin_conf + 0.1) if is_finish_value(fin_text) else fin_conf * 0.85

    fit = row.fit
    comp = Component(
        qty=qty_field,
        qty_unit=unit,
        description=_field(desc, m_conf.get("description", 0.6) * (0.7 + 0.3 * fit)),
        catalog_number=_field(cat, m_conf.get("catalog", 0.6) * (0.7 + 0.3 * fit)),
        mfr=_field(mfr, mfr_conf if mfr else 0.7),
        mfr_resolved=mfr_resolved,
        finish=_field(finish, fin_conf if finish else 0.7),
        notes=_field(notes, 0.7),
    )
    return comp, warnings


def parse_rows(
    lines: Sequence[Line],
    toks: Mapping[str, Token],
    model: ColumnModel,
    legend: Legend,
    rules: RuleIndex = EMPTY_RULES,
) -> ParsedRows:
    set_desc: list[str] = []
    rows, set_notes = assemble_rows(lines, toks, model, set_desc, rules)
    comps: list[Component] = []
    warnings: list[str] = []
    for row in rows:
        desc_text = " ".join(t.text for t in row.cells.get("description", [])).strip(" :.")
        if desc_text.upper() in {"NOTE", "NOTES"}:
            # "1  NOTE  BALANCE OF HARDWARE BY DOOR MFR": a note printed in row form.
            set_notes.extend(t.id for ln in row.lines for t in (toks[i] for i in ln.token_ids))
            continue
        if not any(row.cells.get(r) for r in ("description", "catalog", "qty", "mfr")):
            set_notes.extend(t.id for ln in row.lines for t in (toks[i] for i in ln.token_ids))
            continue
        comp, w = build_component(row, model, legend)
        comps.append(comp)
        warnings.extend(w)
    return ParsedRows(comps, set_notes, warnings, set_desc)
