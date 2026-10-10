"""Which pages hold the hardware schedule?

Header-driven: the document's set-header signature is induced from header candidates on every
page, then hardware pages are the pages holding those headers plus the continuation pages after
them (pages with component rows before the next header, until ``END OF SECTION``). Lexicon page
scores (``layout.pages``) are only a prefilter, because many real set pages carry no lexicon
hits (full manufacturer names, no finish column) and much spec prose does.

Pure function of lines and tokens.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from hwsets.models import Line, Token
from hwsets.segment.headers import (
    HeaderInduction,
    induce_bare_ids,
    induce_headers,
    looks_like_component,
    parse_header,
)

END_OF_SECTION_RE = re.compile(r"^\s*END\s+OF\s+(?:SECTION|SCHEDULE)\b", re.IGNORECASE)
_MAX_CONTINUATION_PAGES = 4


@dataclass(slots=True)
class SectionResult:
    pages: list[int]
    induction: HeaderInduction
    warnings: list[str] = field(default_factory=list)


def find_hardware_pages(
    lines_by_page: Mapping[int, Sequence[Line]], toks: Mapping[str, Token]
) -> SectionResult:
    candidate_pages = {
        p for p, lines in lines_by_page.items() if any(parse_header(ln, toks) for ln in lines)
    }
    cand_lines = [ln for p in sorted(candidate_pages) for ln in lines_by_page[p]]
    induction = induce_headers(cand_lines, toks)
    if induction.signature is None or induction.signature.support < 3:
        # No keyword headers: try a table SET column (bare ids at the left of component rows).
        bare = induce_bare_ids([ln for p in sorted(lines_by_page) for ln in lines_by_page[p]], toks)
        if bare.signature is not None and (
            induction.signature is None or bare.signature.support > induction.signature.support
        ):
            induction = bare
    out = SectionResult(pages=[], induction=induction, warnings=list(induction.warnings))
    if induction.signature is None:
        return out

    header_pages = sorted({int(h.line_id[1:].split("_")[0]) for h in induction.headers})
    pages: set[int] = set(header_pages)
    all_pages = sorted(lines_by_page)
    for hp in header_pages:
        # Continuation pages: sets that run past a page break with no header on the next page.
        idx = all_pages.index(hp)
        ended = _has_end(lines_by_page[hp], after_last_header=True, toks=toks)
        for nxt in all_pages[idx + 1 : idx + 1 + _MAX_CONTINUATION_PAGES]:
            if ended or nxt in pages:
                break
            lines = lines_by_page[nxt]
            if sum(looks_like_component(ln, toks) for ln in lines) < 1:
                break
            pages.add(nxt)
            ended = _has_end(lines, after_last_header=False, toks=toks)
    out.pages = sorted(pages)
    return out


def _has_end(lines: Sequence[Line], *, after_last_header: bool, toks: Mapping[str, Token]) -> bool:
    start = 0
    if after_last_header:
        for i, ln in enumerate(lines):
            if parse_header(ln, toks):
                start = i
    return any(END_OF_SECTION_RE.match(ln.text) for ln in lines[start:])
