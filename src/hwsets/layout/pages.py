"""Cheap per-page score for "does this page contain hardware sets?".

Pure function of a page's tokens. Combines heading keywords (``HARDWARE SET``, ``SET NO``,
``HEADING``, ``HARDWARE GROUP``, ``HW-``) with the density of manufacturer / finish lexicon
hits. Used to pick hardware pages before layout and segmentation.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from hwsets.columns.lexicon import is_finish_code, is_mfr_code
from hwsets.models import Token

_KEYWORD_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"\bHARDWARE\s+SETS?\b",
        r"\bHDWE?\.?\s+SETS?\b",
        r"\bHW\s*SETS?\b",
        r"\bSET\s*(?:NO|NUMBER|#)",
        r"\bHARDWARE\s+GROUPS?\b",
        r"\bHARDWARE\s+HEADINGS?\b",
        r"\bHEADING\s*(?:NO\.?|#)?\s*\d",
        r"\bHW-\s*\d",
        r"\bGROUP\s*(?:NO\.?|#)\s*\d",
    )
)
_QTY_UNIT_RE = re.compile(r"^\d{1,3}$|^(EA|PR|SET|LOT)$")


@dataclass(frozen=True, slots=True)
class PageScore:
    page: int
    n_tokens: int
    keyword_hits: int
    mfr_hits: int
    finish_hits: int
    qty_hits: int
    score: float

    @property
    def is_candidate(self) -> bool:
        return self.score >= 1.0


def score_page(page: int, tokens: Sequence[Token]) -> PageScore:
    n = len(tokens)
    if n == 0:
        return PageScore(page, 0, 0, 0, 0, 0, 0.0)
    text = " ".join(t.text for t in tokens).upper()
    kw = sum(len(p.findall(text)) for p in _KEYWORD_PATTERNS)
    mfr = sum(1 for t in tokens if is_mfr_code(t.text))
    fin = sum(1 for t in tokens if is_finish_code(t.text))
    qty = sum(1 for t in tokens if _QTY_UNIT_RE.match(t.text.upper()))
    # Hardware pages pair manufacturers with finishes, many times per page.
    pair_evidence = min(mfr, fin)
    lex_density = (mfr + fin) / n
    score = 0.35 * min(kw, 4) + 0.08 * min(pair_evidence, 20) + 4.0 * lex_density
    return PageScore(page, n, kw, mfr, fin, qty, round(score, 3))
