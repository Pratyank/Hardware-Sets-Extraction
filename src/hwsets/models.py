"""Pydantic data model: the single source of truth for every stage's inputs and outputs.

Every extracted value is a ``Field`` that cites the ``token_ids`` it was read from, so any
value in the output can be traced back to real words (with coordinates) on the page.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydField

TokenId = str  # f"p{page}_w{index}"
BBox = tuple[float, float, float, float]  # x0, y0, x1, y1 in PDF points (page as displayed)
FieldSource = Literal["rule", "lookup", "llm", "human"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Token(_Frozen):
    id: TokenId
    page: int  # 1-based
    text: str
    bbox: BBox
    font_size: float
    bold: bool
    block: int
    line: int  # PyMuPDF block/line indices (hints only)
    ocr: bool = False
    strike: bool = False  # struck-through (redline deletion): evidence only, never extracted


class PageInfo(_Frozen):
    page: int  # 1-based
    width: float  # displayed (rotation-applied) size in PDF points
    height: float
    rotation: int
    n_tokens: int
    has_images: bool
    ocr: bool = False


class Rule(_Frozen):
    """A thin drawn line (table border, strike line) on the displayed page."""

    bbox: BBox
    horizontal: bool


class TokenDocument(_Frozen):
    """Cached ingest output for one PDF (``data/tokens/<sha>.tokens.json``)."""

    source_pdf: str
    sha256: str
    ingest_version: int
    pages: list[PageInfo]
    tokens: list[Token]


class Line(_Frozen):
    id: str
    page: int
    token_ids: list[TokenId]
    bbox: BBox
    text: str  # tokens joined with single spaces


class Field[T](BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: T | None = None
    token_ids: list[TokenId] = PydField(default_factory=list)
    confidence: float = PydField(default=0.0, ge=0.0, le=1.0)
    source: FieldSource = "rule"


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")

    qty: Field[int | str]  # int when numeric; units like "PR" live in qty_unit
    qty_unit: str | None = None  # "EA", "PR", "SET", or None
    description: Field[str]
    catalog_number: Field[str]
    mfr: Field[str]  # raw code as printed, e.g. "PE"
    mfr_resolved: str | None = None  # e.g. "Pemko", if a legend or lexicon resolves it
    finish: Field[str]  # raw code, e.g. "626"
    notes: Field[str]
    resolved_from_code: str | None = None  # lookup-code bonus: "A" -> full item


class PageRegion(_Frozen):
    page: int
    bbox: BBox


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regions: list[PageRegion]  # one per page spanned
    line_range: tuple[str, str]  # first and last Line.id


class HardwareSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    set_number: Field[str]
    description: Field[str]
    status: Literal["active", "not_used"] = "active"
    status_text: str | None = None  # e.g. "NOT USED"
    location: Location
    components: list[Component] = PydField(default_factory=list)
    notes: Field[str] = PydField(default_factory=Field[str])
    confidence: float = PydField(default=0.0, ge=0.0, le=1.0)  # set-level aggregate


class DocumentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_pdf: str
    hardware_pages: list[int]
    column_roles: dict[str, str]  # diagnostic: column band -> role, with margins
    sets: list[HardwareSet]
    warnings: list[str] = PydField(default_factory=list)


# ---------------------------------------------------------------------------
# Flat export: the brief's plain shape (also the gold-label format).
# ---------------------------------------------------------------------------


class FlatLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pages: list[int]
    regions: list[PageRegion] = PydField(default_factory=list)
    line_range: tuple[str, str] | None = None


class FlatComponent(BaseModel):
    model_config = ConfigDict(extra="allow")  # gold files may carry "_uncertain"

    qty: int | None = None
    qty_unit: str | None = None
    description: str | None = None
    catalog_number: str | None = None
    mfr: str | None = None
    finish: str | None = None
    notes: str | None = None


class FlatSet(BaseModel):
    model_config = ConfigDict(extra="allow")

    set_number: str
    description: str | None = None
    status: Literal["active", "not_used"] = "active"
    location: FlatLocation
    components: list[FlatComponent] = PydField(default_factory=list)


class FlatDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_pdf: str
    gold_pages: str | None = None  # gold files only: page window covered, e.g. "20-40"
    sets: list[FlatSet]
