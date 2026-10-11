"""Line stream -> set spans, and classification of lines inside a span.

The stream is the hardware pages' lines in reading order with chrome removed, so **a page break
is never a boundary**: a set runs from its header to the next header (or to an end-of-section
marker). Inside a span, lines are classified as set-level text (door lists, "Provide each ...",
"Notes:", column-header rows, ...) or candidate component rows. Row assembly happens later,
once column roles are known.

Pure functions of lines and tokens.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from hwsets.columns.features import is_catalog_token
from hwsets.columns.lexicon import is_finish_code, is_mfr_code, unit_code
from hwsets.layout.chrome import header_row_roles
from hwsets.layout.columns import cell_starts
from hwsets.models import Line, Token
from hwsets.segment.headers import NOT_USED_RE, OUTLINE_RE, HeaderParse
from hwsets.segment.section import END_OF_SECTION_RE


class Kind(StrEnum):
    HEADER = "header"
    DESCRIPTION = "description"  # set description line(s)
    SET_LEVEL = "set_level"  # doors, operation, notes, "provide each", risk level ...
    COLUMN_HEADER = "column_header"
    NOT_USED = "not_used"
    ROW = "row"  # candidate component row or continuation (decided with column roles)


_SET_LEVEL_RE = re.compile(
    r"^(?:doors?\s*(?:[:#(]|no\b|nos?\.|numbers?\b|\d)|openings?\s*[:#(\d]|for\s+use\s+on|provide\s+each|"
    r"each\s+(?:to\s+have|opening|door|pair|single|leaf)|opening\s+(?:description|type)|"
    r"operation(?:al)?\b|remarks?\s*:|location\s*:|item\s*#|heading\s+notes|"
    r"legend\s*:|link\s+to\s+catalog|electrified\s+opening|hardware\s+sets?\s*:|"
    r"mode\s+of\s+operation|sequence\s+of\s+operation|keying\s*:|frame\s*:|door\s+type)",
    re.IGNORECASE,
)
# Notes before the first row describe the set; after a row they belong to that row (parse.py).
_NOTES_RE = re.compile(r"^(?:notes?|properties)\s*[:\-.]", re.IGNORECASE)
# A line that only introduces a prose block ("Operational Description:", "Operation:", "Notes:"):
# the lines after it are set-level text until a quantity-led row starts.
_BLOCK_INTRO_RE = re.compile(
    r"^(?:operational\s+description|description\s+of\s+operation|operation(?:al)?(?:\s+narrative)?|"
    r"sequence\s+of\s+operations?|mode\s+of\s+operation|notes?|remarks|general\s+notes?)\s*:?\s*$",
    re.IGNORECASE,
)
_QTY_LEAD_RE = re.compile(r"^\d{1,4}(?:\.0+)?\s+\S")
_DESCRIPTION_RE = re.compile(r"^description\s*:\s*", re.IGNORECASE)
_DOOR_TOKEN_RE = re.compile(r"^(?:[A-Z]{0,3}-?\d{1,4}(?:\.\d{1,2})?[A-Z]{0,3}[,;]?|&|and|thru|to)$",
                            re.IGNORECASE)  # fmt: skip
_DOORS_HASH_RE = re.compile(r"\bdoors?\s*#", re.IGNORECASE)
# Door/opening sizes: "965 x 2134 x 44 - HM DR x HM FR", "3'-0\" x 7'-0\"", "965, 965 x 2147".
_DIMENSION_RE = re.compile(r"^[\d'\"\-.,/ ]{1,14}\s*[x\u00d7]\s*\d", re.IGNORECASE)
_ARTICLE_RE = re.compile(r"^(?:SECTION\s+\d|PART\s+\d\s+[A-Z]|\d+\.\d+\s+[A-Z][A-Z \-/&,]{3,}$)")


@dataclass(slots=True)
class Span:
    header: HeaderParse
    set_id: str
    id_token_ids: tuple[str, ...]
    lines: list[Line]  # header first
    kinds: list[Kind] = field(default_factory=list)
    terminated_by: str | None = None


def _content_text(line: Line) -> str:
    m = OUTLINE_RE.match(line.text)
    return line.text[m.end() :] if m else line.text


def is_door_list(line: Line, toks: Mapping[str, Token]) -> bool:
    words = [toks[i].text for i in line.token_ids]
    if not words or len(words) > 40:
        return False
    if any(is_mfr_code(w) or is_finish_code(w) for w in words) and len(words) < 3:
        return False
    return all(_DOOR_TOKEN_RE.match(w) for w in words) and any(c.isdigit() for c in line.text)


def split_spans(stream: Sequence[Line], headers: Mapping[str, HeaderParse]) -> list[Span]:
    """Split the stream at header lines. A header naming several sets yields one span per id
    (sharing the same lines); the first id owns the header's tokens."""
    spans: list[Span] = []
    current: list[Span] = []
    for ln in stream:
        h = headers.get(ln.id)
        if h is not None:
            current = [
                Span(header=h, set_id=sid, id_token_ids=h.id_token_ids[k], lines=[ln])
                for k, sid in enumerate(h.set_ids)
            ]
            spans.extend(current)
            continue
        if not current or current[0].terminated_by:
            continue
        text = _content_text(ln).strip()
        stop = END_OF_SECTION_RE.match(ln.text) or _ARTICLE_RE.match(ln.text.strip())
        if stop:
            for sp in current:
                sp.terminated_by = text[:40]
            continue
        for sp in current:
            sp.lines.append(ln)
    return spans


_INTRO_RE = re.compile(
    r"^(?:provide\s+each|each\s+(?:to\s+have|opening\s+to\s+receive))", re.IGNORECASE
)
_INTRO_WINDOW = 30


def _table_intro_index(span: Span, toks: Mapping[str, Token]) -> int | None:
    for i, ln in enumerate(span.lines[1 : 1 + _INTRO_WINDOW], start=1):
        text = _content_text(ln).strip()
        if _INTRO_RE.match(text) or header_row_roles([toks[t].text for t in ln.token_ids]):
            return i
        if _QTY_LEAD_RE.match(text) and looks_like_row(ln, toks):
            return None  # rows started before any intro: no preamble to skip
    return None


def looks_like_row(ln: Line, toks: Mapping[str, Token]) -> bool:
    words = [toks[t].text for t in ln.token_ids]
    return len(words) >= 3 and any(
        is_mfr_code(w) or is_finish_code(w) or unit_code(w) for w in words
    )


def _is_title(text: str, words: Sequence[str]) -> bool:
    """An upper-case set title ("ENTRANCE DOORS"), not a row: no codes, units or model numbers."""
    return (
        bool(words)
        and text.isupper()
        and not any(is_mfr_code(w) or is_finish_code(w) for w in words)
        and not words[0][:1].isdigit()
        and not any(unit_code(w) or is_catalog_token(w) for w in words)
    )


def classify(span: Span, toks: Mapping[str, Token]) -> list[Kind]:
    kinds: list[Kind] = [Kind.HEADER]
    seen_row = False
    in_block = False  # inside a prose block introduced by "Operational Description:" etc.
    # Lines between the set header and the item-table intro ("Provide each ... with the
    # following:" or a column-header row) are the set's preamble: door grids, room names, notes.
    intro = _table_intro_index(span, toks)
    for i, ln in enumerate(span.lines[1:], start=1):
        text = _content_text(ln).strip()
        words = [toks[t].text for t in ln.token_ids]
        if intro is not None and i < intro:
            if i == 1 and NOT_USED_RE.fullmatch(text.strip(" .:-()")):
                kinds.append(Kind.NOT_USED)
            elif i == 1 and (_DESCRIPTION_RE.match(text) or _is_title(text, words)):
                kinds.append(Kind.DESCRIPTION)
            else:
                kinds.append(Kind.SET_LEVEL)
            continue
        if in_block:
            if _QTY_LEAD_RE.match(text) or header_row_roles(words):
                in_block = False  # a quantity-led row ends the block
            else:
                kinds.append(Kind.SET_LEVEL)
                continue
        if _BLOCK_INTRO_RE.match(text):
            in_block = True
            kinds.append(Kind.SET_LEVEL)
        elif not text.strip(" -.:"):
            kinds.append(Kind.SET_LEVEL)  # auto-numbering residue such as "PART 59 -"
        elif header_row_roles(words):
            kinds.append(Kind.COLUMN_HEADER)
        elif (
            kinds[-1] in (Kind.HEADER, Kind.DESCRIPTION)
            and not seen_row
            and NOT_USED_RE.fullmatch(text.strip(" .:-()"))
        ):
            # Only the header's own line or the first line after it can mark a set NOT USED;
            # elsewhere "N/A" is ordinary text (e.g. the tail of a wrapped door description).
            kinds.append(Kind.NOT_USED)
        elif _NOTES_RE.match(text):
            kinds.append(Kind.ROW if seen_row else Kind.SET_LEVEL)
        elif _DESCRIPTION_RE.match(text):
            kinds.append(Kind.DESCRIPTION)
        elif (
            # After the first item, a set-level phrase must be a single run of text: "DOOR | 29"
            # split across two table columns is the wrapped tail of a row, not a door reference.
            (_SET_LEVEL_RE.match(text) and not (seen_row and len(cell_starts(ln, toks)) > 1))
            or _DOORS_HASH_RE.search(text)
            or (not seen_row and (is_door_list(ln, toks) or bool(_DIMENSION_RE.match(text))))
        ):
            kinds.append(Kind.SET_LEVEL)
        elif not seen_row and i == 1 and _is_title(text, words):
            kinds.append(Kind.DESCRIPTION)
        else:
            kinds.append(Kind.ROW)
            seen_row = True
    span.kinds = kinds
    return kinds
