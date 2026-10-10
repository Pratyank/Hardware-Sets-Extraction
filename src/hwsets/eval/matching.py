"""Set and component matching (pure functions).

Sets are matched one-to-one by normalized set number, pairing duplicates in document
order; whatever is left falls back to a Hungarian assignment on same-page region IoU.
Components inside a matched set are paired by a Hungarian assignment on
description + catalog similarity.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from hwsets.eval.normalize import (
    norm_code_value,
    norm_finish,
    norm_qty,
    norm_text,
    norm_text_loose,
)
from hwsets.models import BBox, Component, FlatComponent, PageRegion

SET_IOU_THRESHOLD = 0.3
MIN_COMPONENT_SIMILARITY = 50.0  # token_set_ratio, 0..100


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def bbox_iou(a: BBox, b: BBox) -> float:
    """Intersection over union of two ``(x0, y0, x1, y1)`` boxes (0 for degenerate)."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def page_boxes(regions: Iterable[PageRegion]) -> dict[int, BBox]:
    """Union bbox per page (several regions on one page merge into their hull)."""
    out: dict[int, BBox] = {}
    for r in regions:
        b = out.get(r.page)
        out[r.page] = (
            r.bbox
            if b is None
            else (
                min(b[0], r.bbox[0]),
                min(b[1], r.bbox[1]),
                max(b[2], r.bbox[2]),
                max(b[3], r.bbox[3]),
            )
        )
    return out


def location_iou(gold_pages: set[int], gold: dict[int, BBox], pred: dict[int, BBox]) -> float:
    """Mean per-page IoU over every page either side touches (one-sided pages score 0)."""
    pages = gold_pages | set(gold) | set(pred)
    if not pages:
        return 0.0
    total = 0.0
    for p in pages:
        if p in gold and p in pred:
            total += bbox_iou(gold[p], pred[p])
    return total / len(pages)


def best_same_page_iou(a: dict[int, BBox], b: dict[int, BBox]) -> float:
    """Highest IoU over pages present on both sides (the set-matching fallback score)."""
    return max((bbox_iou(a[p], b[p]) for p in set(a) & set(b)), default=0.0)


# ---------------------------------------------------------------------------
# Set matching
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SetRef:
    """What set matching needs to know about one set (gold or predicted)."""

    number: str  # normalized; "" when missing
    boxes: dict[int, BBox] = field(default_factory=dict)
    first_page: int | None = None

    def order_key(self, idx: int) -> tuple[float, float, int]:
        """Document order: first page, then top edge on that page, then list position."""
        page = self.first_page if self.first_page is not None else math.inf
        top = self.boxes[self.first_page][1] if self.first_page in self.boxes else math.inf
        return (page, top, idx)


@dataclass(frozen=True)
class SetPair:
    gold: int | None
    pred: int | None
    method: Literal["number", "iou"] | None = None  # None: unmatched


def match_sets(
    gold: Sequence[SetRef], pred: Sequence[SetRef], iou_threshold: float = SET_IOU_THRESHOLD
) -> list[SetPair]:
    """One-to-one set matching.

    1. Equal non-empty normalized numbers pair up in document order (so the *n*-th gold
       "3" pairs with the *n*-th predicted "3").
    2. Remaining sets are assigned by Hungarian on :func:`best_same_page_iou`; a pair is
       kept only when its IoU is ``>= iou_threshold``.

    Returns matched pairs first (gold document order), then missed gold, then spurious pred.
    """
    g_order = sorted(range(len(gold)), key=lambda i: gold[i].order_key(i))
    p_order = sorted(range(len(pred)), key=lambda i: pred[i].order_key(i))

    by_num: dict[str, list[int]] = defaultdict(list)
    for i in p_order:
        if pred[i].number:
            by_num[pred[i].number].append(i)
    pairs: dict[int, SetPair] = {}
    used_pred: set[int] = set()
    for gi in g_order:
        queue = by_num.get(gold[gi].number) if gold[gi].number else None
        if queue:
            pi = queue.pop(0)
            pairs[gi] = SetPair(gi, pi, "number")
            used_pred.add(pi)

    rest_g = [i for i in g_order if i not in pairs]
    rest_p = [i for i in p_order if i not in used_pred]
    if rest_g and rest_p:
        m = np.array(
            [[best_same_page_iou(gold[g].boxes, pred[p].boxes) for p in rest_p] for g in rest_g]
        )
        rows, cols = linear_sum_assignment(m, maximize=True)
        for r, c in zip(rows.tolist(), cols.tolist(), strict=True):
            if m[r, c] >= iou_threshold:
                pairs[rest_g[r]] = SetPair(rest_g[r], rest_p[c], "iou")
                used_pred.add(rest_p[c])

    out = [pairs[g] for g in g_order if g in pairs]
    out += [SetPair(g, None) for g in g_order if g not in pairs]
    out += [SetPair(None, p) for p in p_order if p not in used_pred]
    return out


# ---------------------------------------------------------------------------
# Component matching
# ---------------------------------------------------------------------------


def _match_text(desc: str | None, catalog: str | None) -> str:
    return norm_text_loose(f"{desc or ''} {catalog or ''}")


def component_similarity(gold: FlatComponent, pred: Component) -> float:
    """``token_set_ratio`` of description + catalog (0..100); both empty counts as 100."""
    a = _match_text(gold.description, gold.catalog_number)
    b = _match_text(pred.description.value, pred.catalog_number.value)
    if not a and not b:
        return 100.0
    return float(fuzz.token_set_ratio(a, b))


def gold_values(c: FlatComponent) -> dict[str, str | int | None]:
    return {
        "qty": c.qty,
        "qty_unit": c.qty_unit,
        "description": c.description,
        "catalog_number": c.catalog_number,
        "mfr": c.mfr,
        "finish": c.finish,
        "notes": c.notes,
    }


def pred_values(c: Component) -> dict[str, str | int | None]:
    return {
        "qty": c.qty.value,
        "qty_unit": c.qty_unit,
        "description": c.description.value,
        "catalog_number": c.catalog_number.value,
        "mfr": c.mfr.value,
        "finish": c.finish.value,
        "notes": c.notes.value,
    }


def norm_field(name: str, value: str | int | None) -> str | int | None:
    """Normalized comparison key of one field value (``""``/``None`` mean empty)."""
    if name == "qty":
        return norm_qty(value)
    sval = None if value is None else str(value)
    if name in ("description", "notes"):
        return norm_text(sval)
    if name == "finish":
        return norm_finish(sval)
    return norm_code_value(sval)


def field_equal(name: str, gold: str | int | None, pred: str | int | None) -> bool:
    return norm_field(name, gold) == norm_field(name, pred)


def _content_key(values: dict[str, str | int | None]) -> tuple[str, ...]:
    return tuple(repr(norm_field(k, v)) for k, v in sorted(values.items()))


def _pred_key(c: Component) -> tuple[str, ...]:
    confs = (c.qty, c.description, c.catalog_number, c.mfr, c.finish, c.notes)
    return (*_content_key(pred_values(c)), *(repr(f.confidence) for f in confs))


def match_components(
    gold: Sequence[FlatComponent],
    pred: Sequence[Component],
    min_similarity: float = MIN_COMPONENT_SIMILARITY,
) -> list[tuple[int | None, int | None, float | None]]:
    """Hungarian component matching; returns ``(gold_idx, pred_idx, similarity)`` triples.

    The assignment maximizes similarity, with tiny tie-breaks on plain ``ratio`` and the
    number of exactly-equal fields so equal-similarity candidates resolve to the closest
    one. Rows and columns are put in a canonical content order first, which makes the
    result independent of the input component order. Pairs below ``min_similarity`` are
    split into a missed gold and a spurious prediction.
    """
    g_idx = sorted(range(len(gold)), key=lambda i: (_content_key(gold_values(gold[i])), i))
    p_idx = sorted(range(len(pred)), key=lambda i: (_pred_key(pred[i]), i))
    sims: dict[tuple[int, int], float] = {}
    out: list[tuple[int | None, int | None, float | None]] = []
    matched_g: set[int] = set()
    matched_p: set[int] = set()
    if g_idx and p_idx:
        score = np.zeros((len(g_idx), len(p_idx)))
        for r, gi in enumerate(g_idx):
            gv = gold_values(gold[gi])
            ga = _match_text(gold[gi].description, gold[gi].catalog_number)
            for c, pi in enumerate(p_idx):
                pv = pred_values(pred[pi])
                sim = component_similarity(gold[gi], pred[pi])
                sims[gi, pi] = sim
                pa = _match_text(pred[pi].description.value, pred[pi].catalog_number.value)
                exact = sum(field_equal(k, gv[k], pv[k]) for k in gv)
                score[r, c] = sim + 1e-3 * fuzz.ratio(ga, pa) + 1e-5 * exact
        rows, cols = linear_sum_assignment(score, maximize=True)
        for r, c in zip(rows.tolist(), cols.tolist(), strict=True):
            gi, pi = g_idx[r], p_idx[c]
            if sims[gi, pi] >= min_similarity:
                out.append((gi, pi, sims[gi, pi]))
                matched_g.add(gi)
                matched_p.add(pi)
    out.sort(key=lambda t: t[0] if t[0] is not None else -1)
    out += [(gi, None, None) for gi in sorted(set(range(len(gold))) - matched_g)]
    out += [(None, pi, None) for pi in sorted(set(range(len(pred))) - matched_p)]
    return out
