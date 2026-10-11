"""Lines -> logical rows, under a layout's column roles.

* a line with a value in the quantity position starts a new row;
* a line with only description / catalog / finish / notes text directly below a row is a wrapped
  continuation of that row (this is what fixes "STOREROOM LEVER 622 LOCKSET": geometry, not
  PyMuPDF's word order, decides which cell a word belongs to);
* a cell printed vertically centred on its row is held for that row (``_closer_to_next``);
* in layouts that space rows wider than wraps, a line a full row pitch down opens a new block:
  an item without a quantity, or a set remark (``rhythm.py``);
* a line starting left of every column, or one unbroken run of words across several columns, is
  prose and goes to the set's notes;
* ``Note:`` / ``Properties:`` sub-lines attach to the row above as notes.

Pure functions.
"""

from __future__ import annotations

import dataclasses
import itertools
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from hwsets.columns.features import QTY_RE
from hwsets.components.rhythm import Rhythm, block_cols, in_block, opens_block
from hwsets.layout.columns import cell_gap, column_of
from hwsets.layout.rules import EMPTY_RULES, RuleIndex
from hwsets.models import Line, Token

_NOTE_RE = re.compile(r"^(?:notes?|properties|note\s*\d*)\s*[:\-]", re.IGNORECASE)
_NUMBERED_NOTE_RE = re.compile(r"^notes?\s*[:\-]?\s*\d+[.)]", re.IGNORECASE)
INT_RE = re.compile(r"^(\d{1,5})(?:\.0+)?$")
REV_TAG_WORDS = r"\[(?:BULLETIN|ADDENDUM|ADD|REV(?:ISION)?|ASI|CCD|PR|RFI|ISSUE)\b"
_REV_TAG_START_RE = re.compile(rf"^{REV_TAG_WORDS}", re.IGNORECASE)
# An item name or a remark opens with a capital letter or a digit; a bullet ("- ...") or a
# lower-case start continues the cell above (paragraph cells with spaced bullets).
_ITEM_START_RE = re.compile(r"^[A-Z0-9]")
_BULLETS = frozenset({"-", "\u2013", "\u2014", "\u2022", "*"})


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
    # Item descriptions printed on quantity-led rows anywhere in this layout ("SEALS"). A
    # quantity-less line whose description is one of them is a new item, not a wrapped cell.
    known_items: frozenset[str] = frozenset()
    # Positional-template roles per token id (list format without aligned columns, template.py).
    overrides: Mapping[str, str] = dataclasses.field(default_factory=dict)
    # Wrap leading vs row pitch when the layout separates rows by spacing alone (rhythm.py).
    rhythm: Rhythm | None = None

    def x_of(self, role: str) -> float | None:
        for x, r in zip(self.xs, self.roles, strict=True):
            if r == role:
                return x
        return None

    def role_of(self, tok: Token) -> str:
        if tok.id in self.overrides:
            return self.overrides[tok.id]
        x1 = None if tok.text in _BULLETS else tok.bbox[2]  # a hanging bullet opens its cell
        col = column_of(tok.bbox[0], self.xs, x1)
        if col < 0:
            # Left of every anchor: a sparse quantity column (too few values to form an anchor).
            return "qty" if INT_RE.match(tok.text) and "qty" not in self.roles else "left"
        return self.roles[col]

    def margin_of(self, role: str) -> float:
        for r, m in zip(self.roles, self.margins, strict=True):
            if r == role:
                return m
        return 0.0

    def has(self, role: str) -> bool:
        return role in self.roles or (bool(self.overrides) and role in {"qty", "mfr", "finish"})


@dataclass(slots=True)
class Row:
    lines: list[Line] = field(default_factory=list)
    cells: dict[str, list[Token]] = field(default_factory=dict)
    note_tokens: list[Token] = field(default_factory=list)
    # A revision tag wrapped down a narrow quantity column ("[BUL" / "LETI" / "N" / "023,").
    tag_tokens: list[Token] = field(default_factory=list)
    fit: float = 1.0  # share of tokens that fell in a known column

    def add(self, role: str, tok: Token) -> None:
        self.cells.setdefault(role, []).append(tok)


def _is_prose(
    line: Line, toks: Mapping[str, Token], model: ColumnModel, *, outside_table: bool = False
) -> bool:
    tokens = [toks[i] for i in line.token_ids]
    if not tokens:
        return False
    if model.xs and tokens[0].bbox[0] < model.xs[0] - 6 and len(tokens) >= 3:
        return model.role_of(tokens[0]) != "qty"
    gap = cell_gap(tokens)
    gaps = sum(1 for a, b in itertools.pairwise(tokens) if b.bbox[0] - a.bbox[2] > gap)
    if gaps or len(tokens) < 6:
        return False
    cols = {column_of(t.bbox[0], model.xs) for t in tokens}
    if len(cols) >= 3:
        return True
    # Above the first item or below the last, in a table with its own quantity column, one
    # unbroken run of words crossing into the next column is a sentence, not a row ("Card Access
    # Not Shown On Arch Drawings Or Door Schedule - Please Confirm"). Inside the table such runs
    # are long cells (paragraph-cell layouts), so they stay.
    return (
        outside_table
        and len(cols) == 2
        and model.has("qty")
        and model.role_of(tokens[0]) not in {"qty", "unit"}
    )


def _gap_above(prev: Line | None, ln: Line) -> float:
    if prev is None or prev.page != ln.page:
        return float("inf")
    return ln.bbox[1] - prev.bbox[3]


def _starts_row(roles: Sequence[str], tokens: Sequence[Token], model: ColumnModel) -> bool:
    qty_text = " ".join(t.text for t, r in zip(tokens, roles, strict=True) if r == "qty")
    if qty_text:
        # The quantity position must hold a quantity ("3", "1 Ea.", "As Req", "--"), not the
        # tail of a prose sentence that happens to start at the same x.
        return bool(QTY_RE.match(qty_text))
    if not model.has("qty") and tokens and QTY_RE.match(tokens[0].text):
        return bool(INT_RE.match(tokens[0].text)) and len(tokens) >= 2
    return False


def line_starts_row(ln: Line, toks: Mapping[str, Token], model: ColumnModel) -> bool:
    tokens = [toks[i] for i in ln.token_ids]
    return bool(tokens) and _starts_row([model.role_of(t) for t in tokens], tokens, model)


def assemble_rows(
    lines: Sequence[Line],
    toks: Mapping[str, Token],
    model: ColumnModel,
    set_desc: list[str] | None = None,
    rules: RuleIndex = EMPTY_RULES,
    *,
    deleted_rows: Mapping[int, Sequence[float]] | None = None,
) -> tuple[list[Row], list[str]]:
    """Group candidate row lines into logical rows. Returns rows and set-note token ids.

    ``deleted_rows`` holds the top y of struck-out rows per page (``deleted_row_tops``): a
    revision tag left behind by a deleted row is dropped with it.

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
    starts = [k for k, x in enumerate(lines) if line_starts_row(x, toks, model)]
    first_start, last_start = (starts[0], starts[-1]) if starts else (len(lines), -1)
    prev_ln: Line | None = None
    prev_line: Line | None = None  # the previous line reaching the prose check
    prev_prose = False
    in_remark = False  # inside a remark block (rhythm.py): its wrapped lines are remark too
    deleted = deleted_rows or {}
    in_deleted = False  # just below a struck-out row
    tag_depth = 0  # open "[" of a deleted row's revision tag
    open_tag: str | None = None  # narrow column holding an unfinished revision tag
    for idx, line in enumerate(lines):
        ln = line  # may be narrowed below (revision-tag fragments taken out)
        tokens = [toks[i] for i in ln.token_ids]
        if not tokens:
            continue
        if open_tag is not None:
            if rows and ln.page == rows[-1].lines[-1].page:
                tag_part = [t for t in tokens if model.role_of(t) == open_tag]
                if tag_part:
                    # Fragments of the tag, never a quantity (a "2512" here is half a date).
                    rows[-1].tag_tokens.extend(tag_part)
                    if any("]" in t.text for t in tag_part):
                        open_tag = None
                    tokens = [t for t in tokens if t not in tag_part]
                    if not tokens:
                        rows[-1].lines.append(ln)
                        prev_ln = ln
                        continue
                    ln = ln.model_copy(update={"token_ids": [t.id for t in tokens]})
                else:
                    open_tag = None
            else:
                open_tag = None
        prev_top = prev_ln.bbox[1] if prev_ln is not None and prev_ln.page == ln.page else -1.0
        if any(prev_top < y <= ln.bbox[1] + 0.5 for y in deleted.get(ln.page, ())):
            in_deleted = True
        if in_deleted:
            if ln.text.startswith("[") or tag_depth > 0:
                # The revision tag of a struck-out row: deleted along with its row.
                tag_depth = max(0, tag_depth + ln.text.count("[") - ln.text.count("]"))
                prev_ln = ln
                continue
            in_deleted, tag_depth = False, 0
        # A full row pitch above this line (in a layout that spaces rows wider than wraps).
        block = opens_block(prev_ln, ln, model.rhythm)
        within = in_block(prev_ln, ln, model.rhythm)
        prev_ln = ln
        if in_remark and within and not line_starts_row(ln, toks, model):
            set_notes.extend(ln.token_ids)
            continue
        in_remark = False
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
            if not _starts_row(roles0, tokens, model) and x0 >= note_x - 3 and not block:
                if note_to_set or not rows:
                    set_notes.extend(ln.token_ids)
                else:
                    rows[-1].note_tokens.extend(tokens)
                    rows[-1].lines.append(ln)
                last_bottom, last_page = ln.bbox[3], ln.page
                continue
            note_x = None
        # Outside the item table, and set apart from it: a gap above, or prose directly above.
        set_apart = prev_prose or _gap_above(prev_line, ln) > 1.5 * max(ln.bbox[3] - ln.bbox[1], 6)
        outside = set_apart and not first_start <= idx <= last_start
        prev_line, prev_prose = ln, False
        if _is_prose(ln, toks, model, outside_table=outside):
            prev_prose = True
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
        desc_text = _norm_desc(
            t.text for t, r in zip(tokens, roles, strict=True) if r == "description"
        )
        # Ruled tables already mark row boundaries exactly, so the vocabulary heuristic is only
        # used where no rules are drawn.
        known_item = bool(
            rows
            and desc_text
            and desc_text in model.known_items
            and len(value_roles) >= 2
            and not rules.row_ruled(ln.page)
        )
        notes_only = set(roles) - {"ignore", "left"} == {"notes"}
        if (
            rows
            and notes_only
            and (
                (rules.row_ruled(ln.page) and rules.separated(rows[-1].lines[-1], ln))
                # Nothing to continue: the row above has no note, so this is not a wrapped note
                # but a remark row about the set.
                or not rows[-1].cells.get("notes")
            )
        ):
            set_notes.extend(ln.token_ids)  # a row holding only a remark: set-level note
            last_bottom, last_page = ln.bbox[3], ln.page
            continue
        if (
            _starts_row(roles, tokens, model)
            or (rows and len(value_roles) >= 3)
            or ruled_break  # a drawn table border closes the previous row
            or known_item  # a description this document prints as its own item elsewhere
        ):
            # A line filling three value columns is a new item even without a quantity
            # ("GASKETING / SWEEP | PEMKO - ... | BLACK"); wrapped cells rarely span three.
            row = Row()
            rows.append(row)
            lead_qty = bool(pending) and not model.has("qty") and bool(INT_RE.match(tokens[0].text))
            for frag in pending:  # centred-cell fragments printed above this row's first line
                _add_line(row, frag, toks, model)
            pending = []
            if lead_qty:
                # The quantity is centred on a wrapped description: printed alone, mid-cell.
                row.add("qty", tokens[0])
                _add_line(row, ln, toks, model, skip=1)
                open_tag = _take_open_tag(row, model)
                last_bottom, last_page = ln.bbox[3], ln.page
                continue
        elif rows and _closer_to_next(
            ln, idx, lines=lines, toks=toks, model=model, last_bottom=last_bottom
        ):
            pending.append(ln)
            continue
        elif (
            rows
            and block
            and model.rhythm is not None
            and not _REV_TAG_START_RE.match(ln.text)  # a revision tag annotates the row above
        ):
            cols = block_cols(
                lines,
                idx,
                toks=toks,
                role_of=model.role_of,
                starts_row=lambda x: line_starts_row(x, toks, model),
                rhythm=model.rhythm,
            ) & {"description", "catalog", "finish", "mfr"}
            if len(cols) < 2 and _ITEM_START_RE.match(tokens[0].text):
                # A one-cell block a full row below the item: a remark row, about the set.
                set_notes.extend(ln.token_ids)
                in_remark = True
                last_bottom, last_page = ln.bbox[3], ln.page
                continue
            if (
                len(cols) >= 2
                and roles[0] == "description"
                and _ITEM_START_RE.match(tokens[0].text)
            ):
                row = Row()  # an item printed without a quantity, in its own row
                rows.append(row)
            elif near and _continuation_ok(rows[-1], roles):
                row = rows[-1]  # not an item name (a bullet, a sentence's tail): keep wrapping
            else:
                set_notes.extend(ln.token_ids)
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
        open_tag = _take_open_tag(row, model) or open_tag
        last_bottom, last_page = ln.bbox[3], ln.page
    if pending and rows:
        for frag in pending:
            _add_line(rows[-1], frag, toks, model)
    return rows, set_notes


def _norm_desc(words: Iterable[str]) -> str:
    return " ".join(w.upper() for w in words).strip(" .,:")


def _add_line(
    row: Row, ln: Line, toks: Mapping[str, Token], model: ColumnModel, skip: int = 0
) -> None:
    tokens = [toks[i] for i in ln.token_ids]
    known = skip
    for tok in tokens[skip:]:
        role = model.role_of(tok)
        if role in {"ignore", "left"}:
            continue
        known += 1
        row.add(role, tok)
    row.lines.append(ln)
    if tokens:
        row.fit = min(row.fit, known / len(tokens))


def _take_open_tag(row: Row, model: ColumnModel) -> str | None:
    """A revision tag started in a narrow quantity/unit cell but not closed there continues down
    that column. Move its opening fragment to the row's tag tokens; return the column's role."""
    for role in ("qty", "unit"):
        cell = row.cells.get(role, [])
        for k, t in enumerate(cell):
            if t.text.startswith("[") and not any("]" in u.text for u in cell[k:]):
                row.tag_tokens.extend(cell[k:])
                row.cells[role] = cell[:k]
                return role if model.has(role) else None
    return None


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
    if nxt_tokens and not model.has("qty") and INT_RE.match(nxt_tokens[0].text):
        nxt_roles[0] = "qty"  # quantity sharing the description cell ("1 | 7500 | Norton")
    if not _starts_row(nxt_roles, nxt_tokens, model):
        return False
    # The fragment's cells must be empty on the next row's line: in a centred layout that line
    # lacks exactly the cell the fragment belongs to; in a top-aligned table it has its own text.
    frag_roles = {model.role_of(toks[i]) for i in ln.token_ids} - {"ignore", "left"}
    if frag_roles & set(nxt_roles):
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
