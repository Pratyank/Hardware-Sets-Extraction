"""Flat export: ``DocumentResult`` -> the brief's plain shape (``FlatDocument``)."""

from __future__ import annotations

from hwsets.models import (
    Component,
    DocumentResult,
    FlatComponent,
    FlatDocument,
    FlatLocation,
    FlatSet,
    HardwareSet,
)


def _flat_qty(c: Component) -> int | None:
    v = c.qty.value
    return v if isinstance(v, int) else None


def flat_component(c: Component) -> FlatComponent:
    return FlatComponent(
        qty=_flat_qty(c),
        qty_unit=c.qty_unit,
        description=c.description.value,
        catalog_number=c.catalog_number.value,
        mfr=c.mfr.value,
        finish=c.finish.value,
        notes=c.notes.value,
    )


def flat_set(s: HardwareSet) -> FlatSet:
    pages = sorted({r.page for r in s.location.regions})
    return FlatSet(
        set_number=s.set_number.value or "",
        description=s.description.value,
        status=s.status,
        location=FlatLocation(
            pages=pages, regions=list(s.location.regions), line_range=s.location.line_range
        ),
        components=[flat_component(c) for c in s.components],
    )


def to_flat(result: DocumentResult) -> FlatDocument:
    return FlatDocument(source_pdf=result.source_pdf, sets=[flat_set(s) for s in result.sets])
