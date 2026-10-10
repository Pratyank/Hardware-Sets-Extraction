"""Running header/footer ("chrome") detection and repeated table-header rows.

A line in the top or bottom 8% of a page whose normalized text (digits -> ``#``) recurs on at
least half of the pages considered is chrome and is dropped. Repeated column-header rows
("QTY DESCRIPTION CATALOG NUMBER FINISH MFR") are not dropped here: they are recognized so that
segmentation skips them and column inference can use them as role evidence.

Pure functions of lines.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence

from hwsets.models import Line

# The plan's 8% misses 4-line running headers (e.g. a block ending at y=72 of 792), so the
# zone is 12%; set-header lines are protected by the caller, so they are never chrome.
MARGIN_FRACTION = 0.12
MIN_SHARE = 0.5
_DIGITS = re.compile(r"\d+")
_WS = re.compile(r"\s+")

# Column-header vocabulary -> role. Used for header-row detection and as a role prior.
HEADER_WORDS: Mapping[str, str] = {
    "QTY": "qty", "QTY.": "qty", "QUANTITY": "qty", "QT": "qty",
    "UNIT": "unit", "UOM": "unit",
    "DESCRIPTION": "description", "ITEM": "description", "TYPE": "description",
    "CATALOG": "catalog", "CAT": "catalog", "CAT.": "catalog", "MODEL": "catalog",
    "PRODUCT": "catalog", "PART": "catalog",
    "FINISH": "finish", "FIN": "finish", "FIN.": "finish", "FNSH": "finish",
    "MFR": "mfr", "MFR.": "mfr", "MFG": "mfr", "MFG.": "mfr", "MANF": "mfr", "MANF.": "mfr",
    "MANUFACTURER": "mfr", "MAN.": "mfr", "MFGR": "mfr",
    "NOTES": "notes", "NOTE": "notes", "REMARKS": "notes", "COMMENTS": "notes",
    "SET": "set_no",
}  # fmt: skip


def normalize(text: str) -> str:
    return _WS.sub(" ", _DIGITS.sub("#", text.strip().lower()))


def in_margin(line: Line, page_height: float) -> bool:
    y_mid = (line.bbox[1] + line.bbox[3]) / 2
    return y_mid < page_height * MARGIN_FRACTION or y_mid > page_height * (1 - MARGIN_FRACTION)


def chrome_keys(
    lines_by_page: Mapping[int, Sequence[Line]],
    page_heights: Mapping[int, float],
    protect: frozenset[str] = frozenset(),
) -> set[str]:
    """Normalized texts of margin lines recurring on >= MIN_SHARE of the given pages.

    Lines whose id is in ``protect`` (set headers) are never counted.
    """
    pages = [p for p in lines_by_page if lines_by_page[p]]
    if len(pages) < 2:
        return set()
    counts: Counter[str] = Counter()
    for p in pages:
        keys = {
            normalize(ln.text)
            for ln in lines_by_page[p]
            if in_margin(ln, page_heights[p]) and ln.id not in protect
        }
        counts.update(keys)
    need = max(2, MIN_SHARE * len(pages))
    return {k for k, c in counts.items() if c >= need}


def is_chrome(line: Line, page_height: float, keys: set[str]) -> bool:
    return in_margin(line, page_height) and normalize(line.text) in keys


def header_row_roles(words: Sequence[str]) -> list[str | None]:
    """Role per word if the words look like a column-header row (>= 3 vocabulary hits)."""
    roles = [HEADER_WORDS.get(w.upper()) for w in words]
    hits = sum(r is not None for r in roles)
    if hits >= 3 and hits >= 0.6 * len(words):
        return roles
    return []
