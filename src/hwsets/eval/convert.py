"""Gold ``FlatDocument`` -> ``DocumentResult`` (for self-evaluation and sanity checks).

Evaluating a gold file against its own conversion must score perfectly; the property
tests rely on this. The result is *not* grounded (no token ids) and must never be used
as extractor output.
"""

from __future__ import annotations

from hwsets.models import (
    Component,
    DocumentResult,
    Field,
    FlatComponent,
    FlatDocument,
    FlatSet,
    HardwareSet,
    Location,
)


def _component(c: FlatComponent, confidence: float) -> Component:
    def f(v: str | None) -> Field[str]:
        return Field[str](value=v, confidence=confidence, source="human")

    return Component(
        qty=Field[int | str](value=c.qty, confidence=confidence, source="human"),
        qty_unit=c.qty_unit,
        description=f(c.description),
        catalog_number=f(c.catalog_number),
        mfr=f(c.mfr),
        finish=f(c.finish),
        notes=f(c.notes),
    )


def _set(s: FlatSet, confidence: float) -> HardwareSet:
    return HardwareSet(
        set_number=Field[str](value=s.set_number, confidence=confidence, source="human"),
        description=Field[str](value=s.description, confidence=confidence, source="human"),
        status=s.status,
        location=Location(
            regions=list(s.location.regions), line_range=s.location.line_range or ("", "")
        ),
        components=[_component(c, confidence) for c in s.components],
        confidence=confidence,
    )


def gold_to_result(gold: FlatDocument, confidence: float = 1.0) -> DocumentResult:
    """Wrap gold values as a prediction with every confidence set to ``confidence``."""
    pages = sorted({p for s in gold.sets for p in s.location.pages})
    return DocumentResult(
        source_pdf=gold.source_pdf,
        hardware_pages=pages,
        column_roles={},
        sets=[_set(s, confidence) for s in gold.sets],
    )
