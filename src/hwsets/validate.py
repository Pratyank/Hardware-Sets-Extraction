"""Invariants and confidence adjustment. Violations become warnings and lower confidence; they
never raise.

* every field with a value cites at least one token, and its tokens lie on the set's pages;
* every cited token's text appears in the value (grounding: no invented text);
* ``qty`` is an int or null;
* an active set has at least one component;
* set numbers are unique within the document (duplicates are flagged, never merged).
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from collections.abc import Mapping

from hwsets.models import Component, DocumentResult, Field, HardwareSet, Token

_PENALTY = 0.5
_NORM = re.compile(r"[^A-Z0-9]")


def _grounded(field: Field[str], toks: Mapping[str, Token], pages: set[int]) -> str | None:
    if field.value is None:
        return None
    if not field.token_ids:
        return "value without tokens"
    missing = [i for i in field.token_ids if i not in toks]
    if missing:
        return f"unknown tokens {missing[:3]}"
    if any(toks[i].page not in pages for i in field.token_ids):
        return "token outside the set's pages"
    value = _NORM.sub("", field.value.upper())
    source = _NORM.sub("", "".join(toks[i].text for i in field.token_ids).upper())
    if value != source:
        return "value text differs from its tokens"
    return None


def _check_component(c: Component, toks: Mapping[str, Token], pages: set[int]) -> list[str]:
    problems: list[str] = []
    for name in ("description", "catalog_number", "mfr", "finish", "notes"):
        f: Field[str] = getattr(c, name)
        err = _grounded(f, toks, pages)
        if err:
            problems.append(f"{name}: {err}")
            f.confidence = round(f.confidence * _PENALTY, 3)
    if c.qty.value is not None and not isinstance(c.qty.value, int):
        problems.append("qty is not an integer")
        c.qty.confidence = round(c.qty.confidence * _PENALTY, 3)
    if c.qty.value is not None and not c.qty.token_ids:
        problems.append("qty without tokens")
        c.qty.confidence = round(c.qty.confidence * _PENALTY, 3)
    return problems


def _set_conf(s: HardwareSet) -> float:
    if not s.components:
        return s.confidence
    vals = [
        statistics.fmean(
            [
                c.qty.confidence,
                c.description.confidence,
                c.catalog_number.confidence,
                c.mfr.confidence,
                c.finish.confidence,
            ]
        )
        for c in s.components
    ]
    return round(statistics.fmean(vals), 3)


def validate_document(result: DocumentResult, toks: Mapping[str, Token]) -> DocumentResult:
    out = result.model_copy(deep=True)
    counts = Counter(s.set_number.value for s in out.sets)
    for s in out.sets:
        pages = {r.page for r in s.location.regions}
        label = f"set {s.set_number.value}"
        for k, c in enumerate(s.components):
            for p in _check_component(c, toks, pages):
                out.warnings.append(f"{label} component {k + 1}: {p}")
        if s.status == "active" and not s.components:
            out.warnings.append(f"{label}: active set has no components")
            s.confidence = round(min(s.confidence, 0.5), 3)
        elif s.status == "not_used" and s.components:
            out.warnings.append(f"{label}: NOT USED set has components; dropped")
            s.components = []
        else:
            s.confidence = _set_conf(s)
        if counts[s.set_number.value] > 1:
            out.warnings.append(f"{label}: duplicate set number ({counts[s.set_number.value]}x)")
            s.set_number.confidence = round(s.set_number.confidence * 0.8, 3)
    return out
