"""Per-column feature distributions computed over *all* rows of a layout.

A column's role is decided from the distribution of its values across the document, never from
one value: "PE" alone is ambiguous, but a column of {SCH, LCN, IVE, PE, VON} is manufacturers and
a column of {626, 630, PE, 689} is finishes.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from hwsets.columns.lexicon import (
    COLLISIONS,
    is_finish_value,
    is_mfr_code,
    norm_code,
    unit_code,
)

QTY_RE = re.compile(
    r"^(?:\d{1,5}(?:\.0+)?(?:\s*[A-Za-z]{1,5}\.?)?|as\s+req(?:'?d|uired)?\.?|--+|_+(?:\s*\w+\.?)?)$",
    re.IGNORECASE,
)
_CATALOG_TOKEN = re.compile(r"(?=.*\d)[A-Za-z0-9][A-Za-z0-9\-/.#\"'x\u00d7]*$")
_WORD = re.compile(r"^[A-Za-z][A-Za-z'&./()-]*$")


@dataclass(frozen=True, slots=True)
class ColumnFeatures:
    n_rows: int  # rows considered
    fill: float  # share of rows with a value in this column
    qty: float
    unit: float
    mfr: float
    finish: float
    catalog: float
    words: float  # share of values that are mostly dictionary-like words
    mean_tokens: float
    collisions: float  # share of values that are ambiguous codes (PE, NO, ...)


def is_mfr_value(text: str, legend: frozenset[str] = frozenset()) -> bool:
    toks = text.split()
    if not toks or len(toks) > 3:
        return False
    whole = norm_code(text)
    return whole in legend or is_mfr_code(text) or (len(toks) == 1 and norm_code(toks[0]) in legend)


def is_catalog_token(tok: str) -> bool:
    """Model-number-like: has a digit, and is either 3+ characters or mixes letters and digits
    (a bare "2" or "10" is a count, not a model)."""
    if not _CATALOG_TOKEN.match(tok):
        return False
    return len(tok) >= 3 or any(c.isalpha() for c in tok)


def is_catalog_value(text: str) -> bool:
    toks = text.split()
    if toks and re.fullmatch(r"\d{1,4}", toks[0]):
        toks = toks[1:]  # a leading count shares the cell in some layouts ("2 Continuous Hinge")
    return any(is_catalog_token(t) for t in toks)


def is_wordy(text: str) -> bool:
    toks = text.split()
    if not toks:
        return False
    return sum(bool(_WORD.match(t)) and len(t) > 1 for t in toks) / len(toks) >= 0.6


def _qty_share(vals: Sequence[str]) -> float:
    """Share of values shaped like quantities, discounted when the numbers are implausibly large
    for a per-opening count (BHMA finish numbers such as 626 or 313 also match the shape)."""
    hits = [v for v in vals if QTY_RE.match(v)]
    nums = [int(m.group()) for v in hits if (m := re.match(r"\d+", v))]
    share = len(hits) / len(vals)
    if nums and sorted(nums)[len(nums) // 2] > 100:
        share *= 0.4
    return share


def column_features(
    values: Sequence[str],
    n_rows: int,
    legend: frozenset[str] = frozenset(),
    finish_legend: frozenset[str] = frozenset(),
) -> ColumnFeatures:
    vals = [v.strip() for v in values if v.strip()]
    n = len(vals)
    if n == 0:
        return ColumnFeatures(n_rows, 0.0, 0, 0, 0, 0, 0, 0, 0, 0)
    collide = [v for v in vals if norm_code(v) in COLLISIONS and norm_code(v) not in legend]
    decisive = n - len(collide)  # ambiguous codes are evidence for neither role
    mfr = sum(is_mfr_value(v, legend) for v in vals if v not in collide)
    fin = sum(
        is_finish_value(v) or norm_code(v.split()[0]) in finish_legend
        for v in vals
        if v not in collide
    )
    return ColumnFeatures(
        n_rows=n_rows,
        fill=n / max(n_rows, 1),
        qty=_qty_share(vals),
        unit=sum(unit_code(v) is not None for v in vals) / n,
        mfr=mfr / decisive if decisive else 0.0,
        finish=fin / decisive if decisive else 0.0,
        catalog=sum(is_catalog_value(v) for v in vals) / n,
        words=sum(is_wordy(v) for v in vals) / n,
        mean_tokens=sum(len(v.split()) for v in vals) / n,
        collisions=len(collide) / n,
    )
