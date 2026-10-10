"""Set-header detection: candidate scoring + per-document pattern induction.

Instead of one hand-written regex per specbook format, every line is parsed by one permissive
grammar ``[outline numbering] KEYWORDS ID [and ID...] [- description]`` where KEYWORDS is drawn
from a small vocabulary (HARDWARE, GROUP, SET, HEADING, HW, NO., #, ...). Each candidate gets a
*shape signature* (canonical keyword bag + id shape + typography + x anchor). The signature with
the most support in the document is chosen, and only lines matching it become headers. This is
how "Hardware Group No. 01", "Set: EX-1.0", "Set #AL 01", "Heading #17", "HW 02A" and
"PART 60 - HARDWARE GROUP NO. C00.EXT" are all handled by the same code.

Pure functions of lines and tokens.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from hwsets.columns.lexicon import is_finish_code, is_mfr_code
from hwsets.models import Line, Token

# Leading outline numbering that some documents auto-insert: "PART 60 -", "3.6", "A.", "1)".
OUTLINE_RE = re.compile(
    r"^\s*(?:PART\s+\d+\s*[-\u2013.:]?|\d+(?:\.\d+)+\.?|[A-Z]\.|\d+[.)])\s+", re.IGNORECASE
)

_KW_WORDS = r"(?:door\s+)?(?:hardware|hdwe?\.?|hw|groups?|sets?|headings?|schedule)"
_KW_RE = re.compile(
    rf"^(?P<kw>{_KW_WORDS}(?:\s*/\s*{_KW_WORDS}|\s+{_KW_WORDS})*"
    r"(?:\s*(?:no\.?|nos\.?|number|num\.?))?\s*(?:#|:|-)?)\s*",
    re.IGNORECASE,
)
# A set identifier: "01", "3A", "EX-1.0", "101T.1", "C200CT", "V-731CR", "AL 01", "MISC".
_ID_CORE = r"#?[A-Z0-9](?:[A-Z0-9.\-]{0,13})"
_ID_RE = re.compile(rf"^(?P<id>(?:[A-Z]{{1,3}}\s+\d{{1,4}}[A-Z]?\b)|{_ID_CORE})", re.IGNORECASE)
_MORE_IDS_RE = re.compile(rf"^\s*(?:,|and|&)\s*(?P<id>{_ID_CORE})", re.IGNORECASE)
_DESC_SEP_RE = re.compile(r"^\s*[-\u2013\u2014:]+\s*")
_STRONG_KW = re.compile(r"(#|:|\bno\b|\bnumber\b|\bheading\b|\bgroup\b|\bhw\b)", re.IGNORECASE)
_CANON = {
    "groups": "group",
    "sets": "set",
    "headings": "heading",
    "hdw": "hardware",
    "hdwe": "hardware",
    "nos": "no",
    "num": "no",
    "number": "no",
}
NOT_USED_RE = re.compile(
    r"(?<![A-Z])(?:NOT\s+USED|N/?A|OMITTED|DELETED|VOID|NOT\s+IN\s+CONTRACT|MOVED\s+TO)(?![A-Z])",
    re.IGNORECASE,
)
_QTY_START_RE = re.compile(r"^\d{1,4}(?:\.0+)?$")


@dataclass(frozen=True, slots=True)
class HeaderParse:
    line_id: str
    keyword: str  # canonical keyword bag, e.g. "group hardware no"
    set_ids: tuple[str, ...]  # raw id text(s) as printed (without leading '#')
    id_token_ids: tuple[tuple[str, ...], ...]  # tokens of each id
    keyword_token_ids: tuple[str, ...]
    desc_token_ids: tuple[str, ...]  # remainder of the line after the id(s)
    x0: float
    bold: bool
    font_size: float


@dataclass(frozen=True, slots=True)
class Signature:
    keyword: str
    x_anchor: float
    bold: bool
    support: int


@dataclass(slots=True)
class HeaderInduction:
    signature: Signature | None
    headers: list[HeaderParse] = field(default_factory=list)
    candidates: int = 0
    warnings: list[str] = field(default_factory=list)


def canonical_keyword(kw: str) -> str:
    words = re.findall(r"[a-z]+|#", kw.lower())
    bag = sorted({_CANON.get(w, w) for w in words if w not in {"door"}})
    return " ".join(bag)


def _char_spans(tokens: Sequence[Token]) -> tuple[str, list[tuple[int, int]]]:
    parts: list[str] = []
    spans: list[tuple[int, int]] = []
    pos = 0
    for t in tokens:
        if parts:
            pos += 1
        spans.append((pos, pos + len(t.text)))
        parts.append(t.text)
        pos += len(t.text)
    return " ".join(parts), spans


def _tokens_in(spans: list[tuple[int, int]], tokens: Sequence[Token], a: int, b: int) -> list[str]:
    return [t.id for t, (s, e) in zip(tokens, spans, strict=True) if s < b and e > a]


def parse_header(line: Line, toks: Mapping[str, Token]) -> HeaderParse | None:
    """Parse one line with the header grammar. Returns None if it cannot be a set header."""
    tokens = [toks[i] for i in line.token_ids]
    if not tokens:
        return None
    text, spans = _char_spans(tokens)
    start = 0
    m = OUTLINE_RE.match(text)
    if m:
        start = m.end()
    km = _KW_RE.match(text[start:])
    if not km:
        return None
    kw_text = km.group("kw")
    # "DOOR HARDWARE 08 71 00" (a running footer) is not a header: the keyword must name a set.
    if not re.search(r"set|group|heading|\bhw\b", kw_text, re.IGNORECASE):
        return None
    pos = start + km.end()
    im = _ID_RE.match(text[pos:])
    if not im:
        return None
    raw_id = im.group("id")
    # An id without digits is only accepted after an explicit marker ("Set: MISC", "Set #MISC").
    if not re.search(r"\d", raw_id) and not (
        re.search(r"[#:]\s*$", kw_text) or raw_id.startswith("#")
    ):
        return None
    if raw_id.lower().rstrip(".") in {"no", "nos", "number", "sets", "set", "group", "groups"}:
        return None
    ids = [(pos + im.start("id"), pos + im.end("id"))]
    rest = pos + im.end()
    while True:
        mm = _MORE_IDS_RE.match(text[rest:])
        if not mm or not re.search(r"\d", mm.group("id")):
            break
        ids.append((rest + mm.start("id"), rest + mm.end("id")))
        rest += mm.end()
    dm = _DESC_SEP_RE.match(text[rest:])
    desc_start = rest + (dm.end() if dm else 0)
    kw_ids = _tokens_in(spans, tokens, start, start + len(kw_text.rstrip()))
    id_tok = [tuple(_tokens_in(spans, tokens, a, b)) for a, b in ids]
    used = set(kw_ids) | {t for grp in id_tok for t in grp}
    desc_ids = [t.id for t, (s, _e) in zip(tokens, spans, strict=True) if s >= desc_start]
    desc_ids = [t for t in desc_ids if t not in used]
    first_kw = toks[kw_ids[0]] if kw_ids else tokens[0]
    return HeaderParse(
        line_id=line.id,
        keyword=canonical_keyword(kw_text),
        set_ids=tuple(text[a:b].lstrip("#").strip() for a, b in ids),
        id_token_ids=tuple(id_tok),
        keyword_token_ids=tuple(kw_ids),
        desc_token_ids=tuple(desc_ids),
        x0=first_kw.bbox[0],
        bold=first_kw.bold,
        font_size=first_kw.font_size,
    )


def looks_like_component(line: Line, toks: Mapping[str, Token]) -> bool:
    """Leading quantity, or several manufacturer/finish lexicon hits: a component row."""
    tokens = [toks[i] for i in line.token_ids]
    if not tokens:
        return False
    if _QTY_START_RE.match(tokens[0].text) and len(tokens) >= 3:
        return True
    hits = sum(1 for t in tokens if is_mfr_code(t.text) or is_finish_code(t.text))
    return hits >= 2


def _candidate_score(h: HeaderParse, line: Line, body_size: float, is_comp: bool) -> float:
    s = 1.0
    if _STRONG_KW.search(h.keyword):
        s += 0.5
    if h.bold:
        s += 0.5
    if h.font_size > body_size * 1.05:
        s += 0.5
    if len(line.token_ids) <= 12:
        s += 0.25
    if is_comp:
        s -= 1.0
    return s


def induce_headers(
    lines: Sequence[Line], toks: Mapping[str, Token], *, min_support: int = 3
) -> HeaderInduction:
    """Find the document's dominant header signature and return every line matching it."""
    parsed: list[tuple[HeaderParse, float]] = []
    sizes = [toks[i].font_size for ln in lines for i in ln.token_ids]
    body = statistics.median(sizes) if sizes else 10.0
    for ln in lines:
        h = parse_header(ln, toks)
        if h is None:
            continue
        parsed.append((h, _candidate_score(h, ln, body, looks_like_component(ln, toks))))
    out = HeaderInduction(signature=None, candidates=len(parsed))
    if not parsed:
        return out

    # Support and quality per canonical keyword.
    by_kw: dict[str, list[tuple[HeaderParse, float]]] = {}
    for h, s in parsed:
        by_kw.setdefault(h.keyword, []).append((h, s))

    def strength(items: list[tuple[HeaderParse, float]]) -> float:
        good = [s for _, s in items if s > 0.5]
        return len(good) * (sum(good) / len(good) if good else 0.0)

    kw, items = max(by_kw.items(), key=lambda kv: strength(kv[1]))
    good = [(h, s) for h, s in items if s > 0.5]
    if not good:
        return out
    x_anchor = Counter(round(h.x0 / 6) * 6 for h, _ in good).most_common(1)[0][0]
    bold = Counter(h.bold for h, _ in good).most_common(1)[0][0]
    # Alignment with the dominant x anchor is supporting evidence, not a requirement: auto-
    # numbering ("PART 60 - ...") can shift a header right. Off-anchor lines need a strong score.
    aligned = [(h, s) for h, s in good if abs(h.x0 - x_anchor) <= 24 or s >= 1.5]
    sig = Signature(keyword=kw, x_anchor=float(x_anchor), bold=bold, support=len(aligned))
    if sig.support < min_support:
        out.warnings.append(
            f"header signature '{kw}' has low support ({sig.support}); kept with evidence checks"
        )
    out.signature = sig
    out.headers = [h for h, _ in aligned]
    return out
