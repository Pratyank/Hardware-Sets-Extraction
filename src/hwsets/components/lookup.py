"""Same-page lookup codes (bonus): a component that prints only a short key ("A") resolved from
a key legend on the same page(s) as its set, e.g.

    A  -  HINGES: 5BB1 4.5 x 4.5 NRP 652 IVE
    B  -  LOCKSET: ND50PD RHO 626 SCH

Keys are one or two letters or digits. A legend needs at least two entries in a block, so an
ordinary sentence starting with "A -" is not mistaken for one. The resolved text cites the
legend line's tokens (``resolved_from_code_tokens``), keeping it grounded.

Pure functions.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hwsets.models import Component, Line, Token

_ENTRY_RE = re.compile(r"^(?P<key>[A-Z]{1,2}|\d{1,2})\s*[-\u2013\u2014:=.)]\s*(?P<text>\S.{3,})$")
_MIN_BLOCK = 2


@dataclass(frozen=True, slots=True)
class LookupEntry:
    key: str
    text: str
    token_ids: tuple[str, ...]


def find_lookup_legend(lines: Sequence[Line], toks: Mapping[str, Token]) -> dict[str, LookupEntry]:
    """Key -> entry for blocks of >= 2 consecutive key lines (one gap line allowed)."""
    found: list[tuple[int, LookupEntry]] = []
    for i, ln in enumerate(lines):
        m = _ENTRY_RE.match(ln.text.strip())
        if not m:
            continue
        key = m.group("key")
        text_ids = tuple(ln.token_ids[1:]) if toks[ln.token_ids[0]].text.startswith(key) else ()
        ids = tuple(t for t in text_ids if toks[t].text not in {"-", "\u2013", "\u2014", ":", "="})
        found.append((i, LookupEntry(key=key, text=m.group("text").strip(), token_ids=ids)))
    out: dict[str, LookupEntry] = {}
    block: list[tuple[int, LookupEntry]] = []
    for item in [*found, (10**9, None)]:  # sentinel flushes the last block
        if block and (item[1] is None or item[0] - block[-1][0] > 2):
            if len(block) >= _MIN_BLOCK and len({e.key for _, e in block}) == len(block):
                out.update({e.key: e for _, e in block})
            block = []
        if item[1] is not None:
            block.append(item)  # type: ignore[arg-type]
    return out


def resolve_codes(components: Sequence[Component], legend: Mapping[str, LookupEntry]) -> int:
    """Fill ``resolved_from_code`` for components whose description or catalog is just a key.
    Returns the number of components resolved."""
    n = 0
    for c in components:
        for f in (c.catalog_number, c.description):
            key = (f.value or "").strip()
            if key in legend and len(key) <= 2:
                c.resolved_from_code = legend[key].text
                c.resolved_from_code_tokens = list(legend[key].token_ids)
                n += 1
                break
    return n
