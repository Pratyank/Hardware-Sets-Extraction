"""Manufacturer and finish lexicons, and the collision set.

These are *evidence*, not decisions: a value's role is decided by the column it sits in
(see ``assign.py``). Codes in ``COLLISIONS`` (e.g. ``PE`` = Pemko / Painted Enamel, ``NO`` =
Norton / the word "No") carry no lexicon evidence for either role.

Seeded from common BHMA / industry abbreviations. Additions found during the Phase 0 survey
carry their evidence as a trailing comment: ``# <doc_id> p<page>``.
"""

from __future__ import annotations

import re
from typing import Final

# fmt: off
# code -> canonical manufacturer name
MFR_CODES: Final[dict[str, str]] = {
    # Allegion
    "IVE": "Ives", "IVES": "Ives", "IV": "Ives",
    "SCH": "Schlage", "SCHLAGE": "Schlage", "SC": "Schlage",
    "SCE": "Schlage Electronics",
    "LCN": "LCN", "LC": "LCN",
    "VON": "Von Duprin", "VD": "Von Duprin",
    "GLY": "Glynn-Johnson", "GJ": "Glynn-Johnson", "GL": "Glynn-Johnson",
    "ZER": "Zero International", "ZERO": "Zero International", "ZE": "Zero International",
    "FAL": "Falcon", "FALCON": "Falcon",
    "STE": "Steelcraft",
    # ASSA ABLOY
    "PEM": "Pemko", "PEMKO": "Pemko", "PE": "Pemko",
    "MK": "McKinney", "MCK": "McKinney",
    "SAR": "Sargent", "SARGENT": "Sargent", "SA": "Sargent",
    "COR": "Corbin Russwin", "CR": "Corbin Russwin", "RUS": "Corbin Russwin",
    "YAL": "Yale", "YALE": "Yale", "YA": "Yale",
    "RIX": "Rixson", "RF": "Rixson",
    "NOR": "Norton", "NORTON": "Norton", "NO": "Norton",
    "SEC": "Securitron", "SU": "Securitron",
    "HES": "HES", "HS": "HES",
    "ADA": "Adams Rite", "AR": "Adams Rite",
    "ACC": "Accurate", "ACCURATE": "Accurate",
    "CER": "Ceco", "CUR": "Curries",
    # dormakaba
    "DOR": "dormakaba", "DORMA": "dormakaba",
    "BES": "Best", "BEST": "Best",
    # Hager / Stanley / others
    "HAG": "Hager", "HAGER": "Hager", "HA": "Hager",
    "STA": "Stanley", "STANLEY": "Stanley",
    "ROC": "Rockwood", "ROCKWOOD": "Rockwood", "RO": "Rockwood",
    "NGP": "National Guard Products", "NAT": "National Guard Products",
    "ABH": "ABH", "TRI": "Trimco", "TRIMCO": "Trimco",
    "BOM": "Bommer", "BOMMER": "Bommer",
    "MED": "Medeco", "MEDECO": "Medeco",
    "SEL": "Select Products", "SELECT": "Select Products",
    "MAR": "Markar", "ROT": "Roton", "BUR": "Burns", "DON": "Don-Jo",
    "HEW": "Hewi", "KEE": "Keedex", "BBW": "Bobrick", "BOB": "Bobrick",
    "AD": "Adams Rite", "DCI": "Door Controls International",
    "LUN": "Lund", "KNC": "Knape & Vogt", "PRE": "Precision",
    "DET": "Detex", "DETEX": "Detex", "ALA": "Alarm Lock", "SDC": "SDC",
    "AIP": "Architectural Builders Hardware", "WAL": "Walsh",
    "HEC": "Hechinger", "GAL": "Gallery", "CAL": "Cal-Royal",
}
# fmt: on

_BHMA = [
    "600",
    "603",
    "604",
    "605",
    "606",
    "609",
    "610",
    "611",
    "612",
    "613",
    "614",
    "615",
    "616",
    "618",
    "619",
    "620",
    "621",
    "622",
    "623",
    "624",
    "625",
    "626",
    "627",
    "628",
    "629",
    "630",
    "631",
    "632",
    "633",
    "634",
    "636",
    "637",
    "638",
    "639",
    "640",
    "643",
    "644",
    "645",
    "646",
    "647",
    "648",
    "649",
    "650",
    "651",
    "652",
    "653",
    "654",
    "655",
    "660",
    "661",
    "662",
    "663",
    "664",
    "665",
    "666",
    "667",
    "668",
    "669",
    "670",
    "671",
    "672",
    "673",
    "674",
    "675",
    "676",
    "677",
    "678",
    "679",
    "680",
    "681",
    "682",
    "683",
    "684",
    "685",
    "686",
    "687",
    "688",
    "689",
    "690",
    "691",
    "692",
    "693",
    "694",
    "695",
    "696",
    "697",
    "698",
    "699",
    "710",
    "711",
    "712",
    "713",
    "714",
    "715",
    "716",
    "717",
    "718",
    "719",
    "720",
    "721",
    "722",
    "723",
    "724",
]
_US = [
    "US1B",
    "US3",
    "US4",
    "US9",
    "US10",
    "US10A",
    "US10B",
    "US11",
    "US14",
    "US15",
    "US15A",
    "US19",
    "US20",
    "US20A",
    "US26",
    "US26D",
    "US27",
    "US28",
    "US32",
    "US32D",
    "USP",
]
_OTHER = [
    # anodized aluminium finishes seen in dev books (morris-bank p232: 313; shubie-center p174: 315)
    "313",
    "315",
    "335",
    "AL",
    "ALUM",
    "ALU",
    "BLK",
    "BK",
    "BSP",
    "DKB",
    "DBZ",
    "DB",
    "GRY",
    "PC",
    "SP",
    "PRIMED",
    "PRIME",
    "CLR",
    "CL",
    "SS",
    "SSS",
    "SST",
    "ANCLR",
    "AN",
    "BRZ",
    "DU",
    "BLKAN",
    "WHT",
    "WH",
    "613E",
    "626AM",
    "630AM",
    "652AM",
    "643E",
    "619AM",
    "690AM",
    "693AM",
    "313AN",
    "335AN",
    "628AM",
    "622AM",
    "605AM",
    "606AM",
    "612AM",
    "613AM",
    "625AM",
]

# code -> canonical finish description (only where it is unambiguous; numbers map to BHMA)
FINISH_CODES: Final[dict[str, str]] = {
    **{c: f"BHMA {c}" for c in _BHMA},
    **{c: c for c in _US},
    **{c: c for c in _OTHER},
}

# Full manufacturer names as printed in some books ("Pemko", "Von Duprin", "McKinney").
for _name in set(MFR_CODES.values()):
    MFR_CODES.setdefault(re.sub(r"[^A-Z0-9]", "", _name.upper()), _name)
MFR_CODES.update({"BYOTHERS": "By Others", "BO": "By Others", "BYDOORMFR": "By Door Manufacturer"})

# US <-> BHMA equivalences (used by eval normalization and finish resolution)
US_TO_BHMA: Final[dict[str, str]] = {
    "US3": "605",
    "US4": "606",
    "US9": "611",
    "US10": "612",
    "US10B": "613",
    "US14": "618",
    "US15": "619",
    "US19": "622",
    "US26": "625",
    "US26D": "626",
    "US28": "628",
    "US32": "629",
    "US32D": "630",
    "USP": "600",
    "US10A": "641",
    "US15A": "620",
}

# Codes that are both manufacturer and finish codes, or ordinary words. Zero evidence.
_COMMON_WORDS = {
    "NO",
    "PE",
    "BL",
    "AL",
    "SP",
    "ST",
    "SC",
    "AS",
    "OR",
    "TO",
    "IN",
    "AT",
    "BY",
    "ON",
    "AN",
    "AD",
    "BE",
    "DU",
    "CL",
    "SS",
    "HA",
    "RO",
    "PRE",
    "CAL",
    "MAR",
    "DON",
    "SEL",
    "SELECT",
    "BEST",
    "ZERO",
    "DB",
    "WH",
    "BK",
    "PC",
}
COLLISIONS: Final[frozenset[str]] = frozenset((set(MFR_CODES) & set(FINISH_CODES)) | _COMMON_WORDS)

_NORM_RE = re.compile(r"[^A-Z0-9]")

UNITS: Final[dict[str, str]] = {
    "EA": "EA", "EACH": "EA", "EAR": "EA-R", "PR": "PR", "PRS": "PR", "PAIR": "PR",
    "PAIRS": "PR", "SET": "SET", "SETS": "SET", "LOT": "LOT", "LS": "LOT", "FT": "FT",
    "LF": "LF", "BOX": "BOX", "ROLL": "ROLL",
}  # fmt: skip


def unit_code(text: str) -> str | None:
    """``"Ea."`` -> ``"EA"``, ``"Pair"`` -> ``"PR"``; None if not a unit."""
    return UNITS.get(_NORM_RE.sub("", text.upper()))


def is_finish_value(text: str) -> bool:
    """A whole finish cell: ``626``, ``630-316``, ``626/622``, ``613 (OIL RUBBED BRONZE)``."""
    first = text.split(maxsplit=1)[0] if text.split() else ""
    parts = [p for p in re.split(r"[-/]", first) if p]
    return (
        bool(parts)
        and all(is_finish_code(p) or p.isdigit() for p in parts)
        and any(is_finish_code(p) for p in parts)
    )


def norm_code(text: str) -> str:
    """Uppercase and strip punctuation: ``"us26d,"`` -> ``"US26D"``."""
    return _NORM_RE.sub("", text.upper())


def is_mfr_code(text: str) -> bool:
    """Lexicon evidence for the manufacturer role (collisions carry none)."""
    c = norm_code(text)
    return c in MFR_CODES and c not in COLLISIONS


def is_finish_code(text: str) -> bool:
    """Lexicon evidence for the finish role (collisions carry none)."""
    c = norm_code(text)
    return c in FINISH_CODES and c not in COLLISIONS


def mfr_name(text: str) -> str | None:
    return MFR_CODES.get(norm_code(text))


def finish_canonical(text: str) -> str:
    """Normalize finishes for comparison: ``US26D`` -> ``626``."""
    c = norm_code(text)
    return US_TO_BHMA.get(c, c)
