"""Positional template for list-format schedules whose columns do not align.

When column inference finds no manufacturer or finish column but many rows end in lexicon
codes, the document is a free-flowing list. A *single* template is inferred for the whole
document from the rows whose trailing tokens are confident lexicon hits, e.g.

    [qty] [unit] desc... catalog... finish mfr      or      [qty] desc... catalog... mfr finish

and then applied to every row. Rows that do not fit get no trailing roles (and a warning
upstream). The decision is document-level: one row's codes never decide its own roles.

Pure functions.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hwsets.columns.features import is_catalog_token
from hwsets.columns.lexicon import (
    COLLISIONS,
    FINISH_CODES,
    is_finish_value,
    is_mfr_code,
    norm_code,
    unit_code,
)
from hwsets.models import Line, Token

_INT_RE = re.compile(r"^\d{1,5}(?:\.0+)?$")
MIN_SUPPORT = 3


@dataclass(frozen=True, slots=True)
class Template:
    trailing: tuple[str, ...]  # roles of the last tokens, left to right, e.g. ("finish", "mfr")
    support: int  # rows that voted for this order
    votes: int  # rows with any confident trailing evidence


def _code_role(text: str, mfr_legend: frozenset[str], finish_legend: frozenset[str]) -> str | None:
    code = norm_code(text)
    if code in mfr_legend:
        return "mfr"
    if code in finish_legend:
        return "finish"
    if code in COLLISIONS:
        return None
    if is_mfr_code(text):
        return "mfr"
    if is_finish_value(text):
        return "finish"
    return None


def infer_template(
    lines: Sequence[Line],
    toks: Mapping[str, Token],
    mfr_legend: frozenset[str] = frozenset(),
    finish_legend: frozenset[str] = frozenset(),
) -> Template | None:
    orders: Counter[tuple[str, ...]] = Counter()
    for ln in lines:
        words = [toks[i].text for i in ln.token_ids]
        if len(words) < 3:
            continue
        last = _code_role(words[-1], mfr_legend, finish_legend)
        prev = _code_role(words[-2], mfr_legend, finish_legend)
        if last and prev and last != prev:
            orders[(prev, last)] += 1
        elif last:
            orders[(last,)] += 1
    if not orders:
        return None
    pairs = {k: v for k, v in orders.items() if len(k) == 2}
    total = sum(orders.values())
    order: tuple[str, ...]
    if pairs:
        order, support = max(pairs.items(), key=lambda kv: kv[1])
    else:
        order, support = max(orders.items(), key=lambda kv: kv[1])
    if support < MIN_SUPPORT:
        return None
    return Template(trailing=order, support=support, votes=total)


def apply_template(
    template: Template, line: Line, toks: Mapping[str, Token]
) -> tuple[dict[str, str], bool]:
    """Roles per token id for one row, and whether the row fit the template.

    Trailing slots are filled from the right only with tokens that are plausible for the slot
    (a finish slot never takes a word, a manufacturer slot never takes a number); everything
    before them is ``[qty] [unit] description... catalog...`` split at the first model token.
    """
    tokens = [toks[i] for i in line.token_ids]
    roles: dict[str, str] = {}
    end = len(tokens)
    fit = True
    for role in reversed(template.trailing):
        if end <= 1:
            fit = False
            break
        t = tokens[end - 1]
        # The slot decides ambiguous codes: "AL" in the finish slot is a finish, "PE" in the
        # manufacturer slot is a manufacturer (collisions are accepted here, by position).
        code = norm_code(t.text)
        ok = (
            role == "finish" and (is_finish_value(t.text) or code in FINISH_CODES or code.isdigit())
        ) or (role == "mfr" and t.text[:1].isalpha() and len(t.text) <= 12)
        if not ok:
            fit = False
            continue  # slot left empty (e.g. no finish printed for this item)
        roles[t.id] = role
        end -= 1
    start = 0
    if tokens and _INT_RE.match(tokens[0].text):
        roles[tokens[0].id] = "qty"
        start = 1
        if len(tokens) > 1 and unit_code(tokens[1].text):
            roles[tokens[1].id] = "unit"
            start = 2
    in_catalog = False
    for t in tokens[start:end]:
        if not in_catalog and t is not tokens[start] and is_catalog_token(t.text):
            in_catalog = True
        roles[t.id] = "catalog" if in_catalog else "description"
    return roles, fit
