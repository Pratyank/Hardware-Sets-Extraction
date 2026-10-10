"""Manufacturer / finish legends printed in the book ("PE - Pemko", "IVE  H.B. Ives",
"626  Satin Chromium", "McKinney (MK)").

A legend overrides the built-in lexicon: its codes become strong manufacturer (or finish)
evidence even when they are collisions like ``PE``, and resolved names cite the legend tokens.

Pure function of lines and tokens.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from hwsets.columns.lexicon import MFR_CODES, is_finish_code, norm_code
from hwsets.layout.chrome import header_row_roles
from hwsets.models import Line, Token

_ENTRY_RE = re.compile(
    r"^(?:\d{1,2}[.)]\s*)?(?P<code>[A-Z](?:[A-Z0-9/&]|-(?=[A-Z0-9])){0,5}|\d{3}[A-Z]{0,3}|US\d{1,2}[A-Z]?)"
    r"\s*(?:[-\u2013\u2014=:]\s*|\s+)(?P<name>[A-Z][A-Za-z0-9.,&'/()\- ]{2,60})$"
)
_INLINE_RE = re.compile(
    r"(?P<name>[A-Z][A-Za-z.&'\-]+(?:\s+[A-Z][A-Za-z.&'\-]+){0,3})\s*\((?P<code>[A-Z]{2,4})\)"
)
_FINISH_WORDS = re.compile(
    r"chrom|bronze|brass|nickel|stainless|steel|black|alumin|anodiz|paint|prime|satin|"
    r"polish|oil rubbed|duranodic|powder|enamel|finish|white|grey|gray|clear|mill|dark",
    re.IGNORECASE,
)
_MFR_NAMES = sorted(set(MFR_CODES.values()))


@dataclass(frozen=True, slots=True)
class LegendEntry:
    code: str  # normalized code
    name: str  # name as printed
    kind: str  # "mfr" | "finish"
    token_ids: tuple[str, ...]


@dataclass(slots=True)
class Legend:
    mfr: dict[str, LegendEntry] = field(default_factory=dict)
    finish: dict[str, LegendEntry] = field(default_factory=dict)

    @property
    def mfr_codes(self) -> frozenset[str]:
        return frozenset(self.mfr)


def _known_mfr(name: str) -> bool:
    best = process.extractOne(name, _MFR_NAMES, scorer=fuzz.partial_ratio)
    return bool(best and best[1] >= 88 and len(best[0]) >= 3)


def _classify(code: str, name: str) -> str | None:
    """ "mfr", "finish", "finish?" (finish words but a code that is not a known finish code; kept
    only inside a block of confirmed finish entries) or None."""
    has_finish_words = bool(_FINISH_WORDS.search(name))
    if has_finish_words and (is_finish_code(code) or code[:1].isdigit()):
        return "finish"
    if _known_mfr(name) or name.lower().startswith(("by ", "others")):
        return "mfr"
    if has_finish_words and len(code) <= 4:
        return "finish?"
    return None


def find_legend(lines: Sequence[Line], toks: Mapping[str, Token]) -> Legend:
    """Collect legend entries. Isolated lines need a recognisable name; lines inside a block of
    three or more consecutive entries are accepted on the block's majority kind."""
    raw: list[tuple[int, str, str, str | None, tuple[str, ...]]] = []
    for i, ln in enumerate(lines):
        if len(ln.token_ids) > 12:
            for m in _INLINE_RE.finditer(ln.text):
                if _known_mfr(m.group("name")):
                    ids = _ids_for(ln, toks, m.group("code"))
                    raw.append((i, norm_code(m.group("code")), m.group("name"), "mfr", ids))
            continue
        if header_row_roles(ln.text.split()):
            continue
        em = _ENTRY_RE.match(ln.text.strip())
        if not em:
            continue
        code, name = em.group("code"), em.group("name").strip()
        if name.split()[0].isdigit():
            continue
        raw.append(
            (i, norm_code(code), name, _classify(norm_code(code), name), tuple(ln.token_ids))
        )

    legend = Legend()
    # Block majority: consecutive entry lines (allowing one gap line) share a kind.
    blocks: list[list[int]] = []
    for k, (i, *_rest) in enumerate(raw):
        if blocks and i - raw[blocks[-1][-1]][0] <= 2:
            blocks[-1].append(k)
        else:
            blocks.append([k])
    for blk in blocks:
        kinds = [raw[k][3] for k in blk if raw[k][3] in {"mfr", "finish"}]
        major = max(set(kinds), key=kinds.count) if kinds else None
        n_finish = kinds.count("finish")
        for k in blk:
            _i, code, name, kind, ids = raw[k]
            if kind == "finish?":
                final = "finish" if n_finish >= 2 and major == "finish" else None
            else:
                final = kind or (major if len(blk) >= 3 else None)
            if final is None:
                continue
            entry = LegendEntry(code=code, name=name, kind=final, token_ids=ids)
            (legend.mfr if final == "mfr" else legend.finish).setdefault(code, entry)
    return legend


def _ids_for(line: Line, toks: Mapping[str, Token], text: str) -> tuple[str, ...]:
    return tuple(i for i in line.token_ids if text in toks[i].text) or tuple(line.token_ids)
