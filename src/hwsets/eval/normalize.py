"""Pure normalization helpers for evaluation.

Every comparison the metrics make goes through one of these functions, so the rules for
"equal after normalization" are documented and tested in one place.
"""

from __future__ import annotations

import re

from hwsets.columns.lexicon import finish_canonical, norm_code

_WS_RE = re.compile(r"\s+")
# A run of zeros that starts a numeric part (not preceded by a digit or a decimal point)
# and is followed by another digit: "001" -> "1", "EX-01.0" -> "EX-1.0", "1.05" unchanged.
_LEADING_ZEROS_RE = re.compile(r"(?<![0-9.])0+(?=[0-9])")
_PUNCT_RE = re.compile(r"[^\w\s]")
_WINDOW_PART_RE = re.compile(r"^(\d+)(?:\s*-\s*(\d+))?$")


def normalize_set_number(raw: str | None) -> str:
    """Canonical form of a set number used for matching.

    Steps: strip, uppercase, collapse internal whitespace to one space, and drop leading
    zeros of every numeric part. ``"001"`` -> ``"1"``, ``" 01a "`` -> ``"1A"``,
    ``"EX-01.0"`` -> ``"EX-1.0"``, ``"0"`` -> ``"0"``. ``None`` -> ``""``.
    """
    if raw is None:
        return ""
    s = _WS_RE.sub(" ", raw.strip().upper())
    return _LEADING_ZEROS_RE.sub("", s)


def norm_text(value: str | None) -> str:
    """Free text (description, notes): casefold, collapse whitespace. ``None`` -> ``""``."""
    if value is None:
        return ""
    return _WS_RE.sub(" ", value.strip()).casefold()


def norm_text_loose(value: str | None) -> str:
    """Free text with punctuation removed too (used for fuzzy similarity only)."""
    return _WS_RE.sub(" ", _PUNCT_RE.sub(" ", norm_text(value))).strip()


def norm_code_value(value: str | None) -> str:
    """Codes (catalog, mfr, qty unit): case, whitespace and punctuation insensitive."""
    if value is None:
        return ""
    return norm_code(value)


def norm_finish(value: str | None) -> str:
    """Finish codes: :func:`norm_code_value` plus US<->BHMA equivalence (US26D == 626)."""
    if value is None:
        return ""
    return finish_canonical(value)


def norm_qty(value: int | str | None) -> int | None:
    """Quantities compare as ints; a digit-only string counts, anything else is ``None``."""
    if isinstance(value, bool):  # bool is an int subclass; never a quantity
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def parse_page_window(spec: str | None) -> frozenset[int] | None:
    """Parse a gold page window: ``"20-40"``, ``"7-18,20"``. ``None``/blank -> ``None``.

    Raises ``ValueError`` on malformed input (validated at the gold-file boundary).
    """
    if spec is None or not spec.strip():
        return None
    pages: set[int] = set()
    for part in spec.split(","):
        m = _WINDOW_PART_RE.match(part.strip())
        if m is None:
            raise ValueError(f"bad page window part {part!r} in {spec!r}")
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        if hi < lo:
            raise ValueError(f"descending page range {part!r} in {spec!r}")
        pages.update(range(lo, hi + 1))
    return frozenset(pages)
