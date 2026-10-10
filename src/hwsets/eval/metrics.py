"""Evaluation metrics: one predicted ``DocumentResult`` against one gold ``FlatDocument``.

Definitions (see PLAN.md Phase 6):

* **Gold window** -- when ``gold.gold_pages`` is set, only gold sets whose *first* page is
  in the window and predicted sets whose first region page is in the window are scored.
* **Set matching** -- :func:`hwsets.eval.matching.match_sets` (normalized number, then
  same-page IoU >= 0.3 via Hungarian).
* **Component matching** -- :func:`hwsets.eval.matching.match_components`.
* **Field accuracy** -- exact after normalization (``null == null`` is correct), over
  matched components only.
* **set_fully_correct** -- matched, same status, every gold component matched with all
  fields exact, and no spurious component; denominator = all gold sets in the window.
* Vacuous ratios (zero denominator) are reported as 1.0.
"""

from __future__ import annotations

from pathlib import Path

from rapidfuzz import fuzz

from hwsets.eval.matching import (
    SetRef,
    field_equal,
    gold_values,
    location_iou,
    match_components,
    match_sets,
    page_boxes,
    pred_values,
)
from hwsets.eval.normalize import (
    norm_code_value,
    norm_finish,
    norm_text,
    normalize_set_number,
    parse_page_window,
)
from hwsets.eval.schema import (
    BUCKETS,
    CONFIDENCE_FIELDS,
    FIELDS,
    FUZZY_FIELDS,
    GOLD_ROLES,
    PRED_ROLES,
    SEVERITY,
    ComponentEval,
    Count,
    DocEval,
    ErrorItem,
    ErrorKind,
    EvalSummary,
    FieldDiff,
    Mean,
    Metrics,
    ReliabilityBucket,
    SetEval,
    Totals,
)
from hwsets.models import Component, DocumentResult, FlatComponent, FlatDocument, FlatSet

__all__ = ["aggregate", "bucket_index", "code_role", "evaluate_document", "fuzzy_score"]

_FIELD_ERROR_KIND: dict[str, ErrorKind] = {
    "mfr": "wrong_mfr",
    "finish": "wrong_finish",
    "qty": "wrong_qty",
}


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------


def bucket_index(confidence: float) -> int:
    """Reliability bucket of a confidence: ``[0,.2) [.2,.4) [.4,.6) [.6,.8) [.8,.9) [.9,1]``."""
    for i, (lo, hi) in enumerate(BUCKETS):
        if lo <= confidence < hi:
            return i
    return len(BUCKETS) - 1


def fuzzy_score(gold: str | None, pred: str | None) -> float:
    """``rapidfuzz.fuzz.ratio / 100`` on casefolded text; both empty -> 1, one empty -> 0."""
    a, b = norm_text(gold), norm_text(pred)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return float(fuzz.ratio(a, b)) / 100.0


def _same_code(a: str, b: str | int | None) -> bool:
    if b is None or not norm_code_value(str(b)):
        return False
    return norm_code_value(a) == norm_code_value(str(b)) or norm_finish(a) == norm_finish(str(b))


def code_role(code: str, gold_role: str, pred: Component) -> str:
    """Where a gold mfr/finish code landed in the prediction.

    ``gold_role`` if the predicted field of that role holds the code; else the other code
    role if *that* field holds it; else ``"other"`` if any other predicted field contains it
    as a whitespace-separated token; else ``"missing"`` (absent, or a different value).
    """
    other_role = "finish" if gold_role == "mfr" else "mfr"
    values = pred_values(pred)
    if _same_code(code, values[gold_role]):
        return gold_role
    if _same_code(code, values[other_role]):
        return other_role
    for name in ("qty_unit", "description", "catalog_number", "notes"):
        text = values[name]
        if isinstance(text, str) and any(_same_code(code, tok) for tok in text.split()):
            return "other"
    return "missing"


def _opt_str(v: str | int | None) -> str | None:
    return None if v is None else str(v)


def _first_page_gold(s: FlatSet) -> int | None:
    pages = set(s.location.pages) | {r.page for r in s.location.regions}
    return min(pages) if pages else None


def _first_page_pred(regions_pages: list[int]) -> int | None:
    return min(regions_pages) if regions_pages else None


def _empty_totals() -> Totals:
    return Totals(
        fields={f: Count() for f in FIELDS},
        fuzzy={f: Mean() for f in FUZZY_FIELDS},
        confusion={g: dict.fromkeys(PRED_ROLES, 0) for g in GOLD_ROLES},
        reliability=[ReliabilityBucket(lo=lo, hi=hi) for lo, hi in BUCKETS],
    )


# ---------------------------------------------------------------------------
# Per-set evaluation
# ---------------------------------------------------------------------------


def _eval_components(
    gs: FlatSet, comps: list[Component], t: Totals
) -> tuple[list[ComponentEval], int, int, bool]:
    """Score the components of one matched set, accumulating into ``t``."""
    evals: list[ComponentEval] = []
    n_missed = n_spurious = 0
    all_exact = True
    for gi, pi, sim in match_components(gs.components, comps):
        if gi is None or pi is None:
            evals.append(ComponentEval(gold_idx=gi, pred_idx=pi))
            if pi is None:
                n_missed += 1
            else:
                n_spurious += 1
            all_exact = False
            continue
        g: FlatComponent = gs.components[gi]
        p: Component = comps[pi]
        gv, pv = gold_values(g), pred_values(p)
        correct = {f: field_equal(f, gv[f], pv[f]) for f in FIELDS}
        confs = {f: getattr(p, f).confidence for f in CONFIDENCE_FIELDS}
        diffs = [
            FieldDiff(field=f, gold=gv[f], pred=pv[f], confidence=confs.get(f))
            for f in FIELDS
            if not correct[f]
        ]
        for f in FIELDS:
            t.fields[f] = t.fields[f].add(Count(correct=int(correct[f]), total=1))
        for f in FUZZY_FIELDS:
            score = fuzzy_score(_opt_str(gv[f]), _opt_str(pv[f]))
            t.fuzzy[f] = t.fuzzy[f].add(Mean(sum=score, count=1))
        for role in GOLD_ROLES:
            code = gv[role]
            if isinstance(code, str) and norm_code_value(code):
                t.confusion[role][code_role(code, role, p)] += 1
        for f, conf in confs.items():
            b = t.reliability[bucket_index(conf)]
            b.count += 1
            b.correct += int(correct[f])
        all_exact = all_exact and all(correct.values())
        evals.append(
            ComponentEval(
                gold_idx=gi, pred_idx=pi, similarity=sim, field_correct=correct, diffs=diffs
            )
        )
    t.n_gold_components += len(gs.components)
    t.n_pred_components += len(comps)
    t.n_matched_components += len(gs.components) - n_missed
    return evals, n_missed, n_spurious, all_exact


def _set_errors(doc_id: str, se: SetEval) -> list[ErrorItem]:
    def err(
        kind: ErrorKind,
        message: str = "",
        field: str | None = None,
        gold: str | int | None = None,
        pred: str | int | None = None,
    ) -> ErrorItem:
        return ErrorItem(
            doc_id=doc_id,
            kind=kind,
            severity=SEVERITY[kind],
            set_number=se.set_number,
            set_idx=se.pred_idx,
            page=se.page,
            line_id=se.line_id,
            field=field,
            gold=gold,
            pred=pred,
            message=message,
        )

    if se.pred_idx is None:
        return [err("missed_set", message=f"gold set {se.set_number} not found")]
    if se.gold_idx is None:
        return [err("spurious_set", message=f"predicted set {se.set_number} not in gold")]
    out: list[ErrorItem] = []
    if not se.status_correct:
        out.append(err("wrong_status", gold=se.gold_status, pred=se.pred_status))
    for ce in se.components:
        if ce.pred_idx is None:
            out.append(err("missed_component", message=f"gold component #{ce.gold_idx}"))
        elif ce.gold_idx is None:
            out.append(err("spurious_component", message=f"predicted component #{ce.pred_idx}"))
        for d in ce.diffs:
            kind = _FIELD_ERROR_KIND.get(d.field, "wrong_field")
            out.append(
                err(
                    kind,
                    field=d.field,
                    gold=d.gold,
                    pred=d.pred,
                    message=f"component #{ce.gold_idx}: {d.field}",
                )
            )
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_document(
    pred: DocumentResult, gold: FlatDocument, doc_id: str | None = None
) -> DocEval:
    """Evaluate one document. ``doc_id`` defaults to the stem of ``pred.source_pdf``."""
    doc_id = doc_id or Path(pred.source_pdf).stem
    window = parse_page_window(gold.gold_pages)

    gold_idx: list[int] = []
    gold_refs: list[SetRef] = []
    for i, g_set in enumerate(gold.sets):
        fp = _first_page_gold(g_set)
        if window is None or (fp is not None and fp in window):
            gold_idx.append(i)
            boxes = page_boxes(g_set.location.regions)
            gold_refs.append(SetRef(normalize_set_number(g_set.set_number), boxes, fp))
    pred_idx: list[int] = []
    pred_refs: list[SetRef] = []
    for i, p_set in enumerate(pred.sets):
        fp = _first_page_pred([r.page for r in p_set.location.regions])
        if window is None or (fp is not None and fp in window):
            pred_idx.append(i)
            boxes = page_boxes(p_set.location.regions)
            pred_refs.append(SetRef(normalize_set_number(p_set.set_number.value), boxes, fp))

    t = _empty_totals()
    t.n_gold_sets, t.n_pred_sets = len(gold_idx), len(pred_idx)
    set_evals: list[SetEval] = []
    for pair in match_sets(gold_refs, pred_refs):
        gi = gold_idx[pair.gold] if pair.gold is not None else None
        pi = pred_idx[pair.pred] if pair.pred is not None else None
        gs = gold.sets[gi] if gi is not None else None
        ps = pred.sets[pi] if pi is not None else None
        ref = gold_refs[pair.gold] if pair.gold is not None else pred_refs[pair.pred or 0]
        line_range = (gs.location.line_range if gs else None) or (
            ps.location.line_range if ps else None
        )
        se = SetEval(
            set_number=(gs.set_number if gs else ps.set_number.value if ps else None) or "",
            gold_idx=gi,
            pred_idx=pi,
            method=pair.method,
            page=ref.first_page,
            line_id=(line_range[0] or None) if line_range else None,
            gold_status=gs.status if gs else None,
            pred_status=ps.status if ps else None,
        )
        if gs is not None and ps is not None:
            t.n_matched_sets += 1
            t.n_matched_by_iou += int(pair.method == "iou")
            se.status_correct = gs.status == ps.status
            t.status = t.status.add(Count(correct=int(se.status_correct), total=1))
            if gs.location.regions:
                g_boxes = page_boxes(gs.location.regions)
                se.location_iou = location_iou(
                    set(gs.location.pages), g_boxes, page_boxes(ps.location.regions)
                )
                t.location = t.location.add(Mean(sum=se.location_iou, count=1))
            comps, n_missed, n_spur, exact = _eval_components(gs, ps.components, t)
            se.components, se.n_missed_components, se.n_spurious_components = (
                comps,
                n_missed,
                n_spur,
            )
            se.fully_correct = se.status_correct and exact
            t.n_fully_correct += int(se.fully_correct)
        set_evals.append(se)

    for b in t.reliability:
        b.accuracy = b.correct / b.count if b.count else None
    errors = [e for se in set_evals for e in _set_errors(doc_id, se)]
    return DocEval(
        doc_id=doc_id,
        source_pdf=gold.source_pdf,
        gold_pages=gold.gold_pages,
        totals=t,
        metrics=Metrics.from_totals(t),
        sets=set_evals,
        errors=errors,
    )


def aggregate(docs: list[DocEval]) -> EvalSummary:
    """Micro-average (sum counts, then divide) plus a macro mean of per-doc headline rates."""
    t = _empty_totals()
    for d in docs:
        s = d.totals
        t.n_gold_sets += s.n_gold_sets
        t.n_pred_sets += s.n_pred_sets
        t.n_matched_sets += s.n_matched_sets
        t.n_matched_by_iou += s.n_matched_by_iou
        t.status = t.status.add(s.status)
        t.n_gold_components += s.n_gold_components
        t.n_pred_components += s.n_pred_components
        t.n_matched_components += s.n_matched_components
        for f, c in s.fields.items():
            t.fields[f] = t.fields.get(f, Count()).add(c)
        for f, m in s.fuzzy.items():
            t.fuzzy[f] = t.fuzzy.get(f, Mean()).add(m)
        for g, row in s.confusion.items():
            for p, n in row.items():
                t.confusion[g][p] += n
        t.location = t.location.add(s.location)
        t.n_fully_correct += s.n_fully_correct
        for acc, b in zip(t.reliability, s.reliability, strict=True):
            acc.count += b.count
            acc.correct += b.correct
    for b in t.reliability:
        b.accuracy = b.correct / b.count if b.count else None
    keys = ("set_recall", "set_precision", "set_f1", "set_fully_correct", "location_iou")
    macro = {k: sum(getattr(d.metrics, k) for d in docs) / len(docs) for k in keys} if docs else {}
    return EvalSummary(n_docs=len(docs), totals=t, metrics=Metrics.from_totals(t), macro=macro)
