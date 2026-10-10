"""Confidence calibration: map raw field scores to empirical accuracy.

Raw confidences combine column-role margins, lexicon agreement, row fit and wrap counts. They
rank fields well but are not probabilities. A per-field monotone (isotonic) map, fitted on the
gold books with pool-adjacent-violators, turns a raw score into "how often a field with this
score was exactly right". The map is piecewise linear between breakpoints and never reorders
fields, so ranking (what the review UI uses to send reviewers to the weakest fields) is kept.

Pure functions: the table is loaded and saved by the CLI.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from hwsets.models import Component, DocumentResult, Field

FIELDS = ("qty", "description", "catalog_number", "mfr", "finish", "notes")
_MIN_BLOCK = 20  # pool at least this many observations per breakpoint (stability)


class FieldMap(BaseModel):
    model_config = ConfigDict(frozen=True)

    xs: tuple[float, ...]  # raw score breakpoints, ascending
    ys: tuple[float, ...]  # calibrated accuracy at each breakpoint, non-decreasing
    n: int  # observations used

    def __call__(self, raw: float) -> float:
        if not self.xs:
            return raw
        if raw <= self.xs[0]:
            return self.ys[0]
        if raw >= self.xs[-1]:
            return self.ys[-1]
        i = bisect.bisect_right(self.xs, raw)
        x0, x1, y0, y1 = self.xs[i - 1], self.xs[i], self.ys[i - 1], self.ys[i]
        return y0 + (y1 - y0) * (raw - x0) / (x1 - x0) if x1 > x0 else y1


class Calibration(BaseModel):
    model_config = ConfigDict(frozen=True)

    fields: dict[str, FieldMap]
    source: str = ""  # what it was fitted on


def isotonic(points: Sequence[tuple[float, bool]], min_block: int = _MIN_BLOCK) -> FieldMap:
    """Pool-adjacent-violators on (raw score, correct) pairs, in blocks of >= ``min_block``."""
    pts = sorted(points)
    if not pts:
        return FieldMap(xs=(), ys=(), n=0)
    # Initial blocks of min_block observations: [sum_x, sum_y, count].
    blocks: list[list[float]] = []
    for i in range(0, len(pts), min_block):
        chunk = pts[i : i + min_block]
        blocks.append([sum(x for x, _ in chunk), float(sum(y for _, y in chunk)), len(chunk)])
    merged: list[list[float]] = []
    for b in blocks:
        merged.append(b)
        while len(merged) > 1 and merged[-2][1] / merged[-2][2] > merged[-1][1] / merged[-1][2]:
            sx, sy, n = merged.pop()
            merged[-1] = [merged[-1][0] + sx, merged[-1][1] + sy, merged[-1][2] + n]
    # Compress: neighbouring blocks with the same accuracy (or the same mean score) carry no
    # extra information and only clutter the table.
    compact: list[list[float]] = []
    for b in merged:
        if compact and (
            abs(compact[-1][1] / compact[-1][2] - b[1] / b[2]) < 1e-3
            or abs(compact[-1][0] / compact[-1][2] - b[0] / b[2]) < 1e-3
        ):
            compact[-1] = [compact[-1][0] + b[0], compact[-1][1] + b[1], compact[-1][2] + b[2]]
        else:
            compact.append(b)
    xs = tuple(round(sx / n, 4) for sx, _, n in compact)
    ys = tuple(round(sy / n, 4) for _, sy, n in compact)
    return FieldMap(xs=xs, ys=ys, n=len(pts))


def fit(observations: Mapping[str, Iterable[tuple[float, bool]]], source: str = "") -> Calibration:
    return Calibration(
        fields={f: isotonic(list(obs)) for f, obs in observations.items() if f in FIELDS},
        source=source,
    )


def _apply_field(field: Field[str] | Field[int | str], fmap: FieldMap | None) -> None:
    if fmap is not None and field.source == "rule":
        field.confidence = round(min(1.0, max(0.0, fmap(field.confidence))), 3)


def _component_conf(c: Component) -> float:
    vals = [c.qty.confidence, c.description.confidence, c.catalog_number.confidence,
            c.mfr.confidence, c.finish.confidence]  # fmt: skip
    return sum(vals) / len(vals)


def apply(result: DocumentResult, calibration: Calibration | None) -> DocumentResult:
    """Return a copy with every rule-sourced field confidence mapped through the calibration."""
    if calibration is None:
        return result
    out = result.model_copy(deep=True)
    for s in out.sets:
        for c in s.components:
            for name in FIELDS:
                _apply_field(getattr(c, name), calibration.fields.get(name))
        if s.components:
            s.confidence = round(
                sum(_component_conf(c) for c in s.components) / len(s.components), 3
            )
    return out
