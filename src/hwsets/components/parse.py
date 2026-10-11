"""Rows -> components.

Row assembly (which lines form one row) lives in ``rows.py``. This module turns a row's cells into
fields: quantity only from the quantity position, never defaulted; description and catalog from
their columns (or split at the first model-like token when one cell holds both); manufacturer and
finish from their columns, with codes resolved by the column's role, not by the code alone.

Pure functions.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from hwsets.columns.features import is_catalog_token
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
from hwsets.components.rows import INT_RE, REV_TAG_WORDS, ColumnModel, Row, assemble_rows
from hwsets.layout.rules import EMPTY_RULES, RuleIndex
from hwsets.models import Component, Field, Line, Token

_REV_TAG_RE = re.compile(rf"^{REV_TAG_WORDS}[^\]]*\]$", re.IGNORECASE)
_MFR_SPLIT_RE = re.compile(r"\s[-\u2013]\s")


@dataclass(slots=True)
class ParsedRows:
    components: list[Component]
    set_note_tokens: list[str]
    warnings: list[str]
    set_desc_tokens: list[str] = field(default_factory=list)  # text of a table SET column


def _join(tokens: Sequence[Token]) -> str:
    """Join cell tokens with single spaces, except a code broken across a line wrap at a hyphen
    ("630-" on one line, "316" on the next -> "630-316") and an opening bracket left alone
    before a wrap. Other tokens on the same line keep their space ("W/ KEYFOB")."""
    out = ""
    prev: Token | None = None
    for t in tokens:
        if prev is None:
            out = t.text
        else:
            wrapped = t.bbox[1] >= prev.bbox[3] - 0.25 * (prev.bbox[3] - prev.bbox[1])
            if wrapped and len(prev.text) > 1 and prev.text.endswith("-") and t.text[:1].isalnum():
                out += t.text
            elif prev.text in {"(", "["} and (wrapped or t.bbox[0] - prev.bbox[2] < 1.0):
                # An opening bracket left alone (the struck word after it was deleted) opens
                # the next word: "(" + "NIGHT" -> "(NIGHT".
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
        m = INT_RE.match(t.text)
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
    if (
        not qty_cell
        and not model.has("qty")  # with a quantity column, quantities come only from it
        and first_role
        and INT_RE.match(cells[first_role][0].text)
    ):
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
    # A revision tag on a newly revised item (the item's own text is emphasised, i.e. bold)
    # stays with it; a tag next to an unchanged item is left over from a struck revision.
    body = desc + cat
    # A bold quantity is a revised quantity ("2 (1)": the new value bold, the old one struck).
    revised = (bool(body) and sum(t.bold for t in body) * 2 > len(body)) or any(
        t.bold for t in q_used
    )
    tags = (tag_d + tag_c) if revised else []
    notes = cells.get("notes", []) + tags + row.note_tokens
    col_tag = row.tag_tokens if revised else []

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
    # Values assembled from several wrapped lines are where row-assembly mistakes live, so their
    # raw score drops with each extra line (calibration turns scores into accuracies later).
    wrap = 0.93 ** max(len(row.lines) - 1, 0)
    comp = Component(
        qty=qty_field,
        qty_unit=unit,
        description=_field(desc, m_conf.get("description", 0.6) * (0.7 + 0.3 * fit) * wrap),
        catalog_number=_field(cat, m_conf.get("catalog", 0.6) * (0.7 + 0.3 * fit) * wrap),
        mfr=_field(mfr, mfr_conf if mfr else 0.7),
        mfr_resolved=mfr_resolved,
        finish=_field(finish, fin_conf if finish else 0.7),
        notes=_notes_field(notes, col_tag, 0.7 * wrap),
    )
    return comp, warnings


def _notes_field(notes: Sequence[Token], col_tag: Sequence[Token], conf: float) -> Field[str]:
    """Notes, plus a revision tag re-flowed from a narrow column ("[BUL" "LETI" "N" "023,"
    "2512" "18]" -> "[BULLETIN 023, 251218]": the column broke words, not the tag's spacing)."""
    if not col_tag:
        return _field(notes, conf)
    tag = "".join(t.text for t in col_tag)
    tag = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", tag)
    tag = re.sub(r",(?=\S)", ", ", tag)
    text = " ".join(x for x in (_join(notes) if notes else "", tag) if x)
    return Field[str](
        value=text, token_ids=[t.id for t in [*notes, *col_tag]], confidence=round(conf, 3)
    )


def parse_rows(
    lines: Sequence[Line],
    toks: Mapping[str, Token],
    model: ColumnModel,
    legend: Legend,
    rules: RuleIndex = EMPTY_RULES,
    *,
    deleted_rows: Mapping[int, Sequence[float]] | None = None,
) -> ParsedRows:
    set_desc: list[str] = []
    rows, set_notes = assemble_rows(lines, toks, model, set_desc, rules, deleted_rows=deleted_rows)
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
