"""Evaluation metrics: normalization, matching and every metric on hand-built fixtures."""

from __future__ import annotations

import math
import random

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from hwsets.eval import aggregate, evaluate_document, gold_to_result
from hwsets.eval.matching import (
    SetRef,
    bbox_iou,
    location_iou,
    match_components,
    match_sets,
)
from hwsets.eval.metrics import bucket_index, code_role, fuzzy_score
from hwsets.eval.normalize import normalize_set_number, parse_page_window
from hwsets.eval.schema import FIELDS, DocEval
from hwsets.models import (
    DocumentResult,
    Field,
    FlatComponent,
    FlatDocument,
    FlatLocation,
    FlatSet,
    PageRegion,
)


def fc(
    desc: str | None,
    cat: str | None = None,
    mfr: str | None = None,
    finish: str | None = None,
    *,
    qty: int | None = 1,
    unit: str | None = None,
    notes: str | None = None,
) -> FlatComponent:
    return FlatComponent(
        qty=qty, qty_unit=unit, description=desc, catalog_number=cat, mfr=mfr, finish=finish,
        notes=notes,
    )  # fmt: skip


def fset(
    num: str,
    page: int = 1,
    y: float = 0.0,
    *,
    comps: list[FlatComponent] | None = None,
    status: str = "active",
    pages: list[int] | None = None,
) -> FlatSet:
    pages = pages or [page]
    regions = [PageRegion(page=p, bbox=(0.0, y, 100.0, y + 50.0)) for p in pages]
    return FlatSet(
        set_number=num,
        status=status,  # type: ignore[arg-type]
        location=FlatLocation(pages=pages, regions=regions, line_range=(f"L{num}", f"L{num}e")),
        components=comps or [],
    )


def gdoc(*sets: FlatSet, gold_pages: str | None = None) -> FlatDocument:
    return FlatDocument(source_pdf="book.pdf", gold_pages=gold_pages, sets=list(sets))


def sfield(v: str | None, conf: float = 1.0) -> Field[str]:
    return Field[str](value=v, confidence=conf)


HW = [
    fc("HINGE", "5BB1 4.5 X 4.5", "IVE", "652", qty=3),
    fc("LOCKSET", "ND50PD RHO", "SCH", "626"),
    fc("CLOSER", "4040XP", "LCN", "689"),
    fc("STOP", "WS406", "VON", "630"),
]


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("001", "1"),
        ("01A", "1A"),
        ("EX-01.0", "EX-1.0"),
        ("  3a ", "3A"),
        ("hw  -  07", "HW - 7"),
        ("0", "0"),
        ("000", "0"),
        ("10", "10"),
        ("1.05", "1.05"),
        ("A01", "A1"),
        (None, ""),
    ],
)
def test_normalize_set_number(raw: str | None, expected: str) -> None:
    assert normalize_set_number(raw) == expected


def test_parse_page_window() -> None:
    assert parse_page_window(None) is None
    assert parse_page_window("  ") is None
    assert parse_page_window("20-22") == {20, 21, 22}
    assert parse_page_window("7-9, 20") == {7, 8, 9, 20}
    for bad in ("x", "5-3", "1--2"):
        with pytest.raises(ValueError):
            parse_page_window(bad)


def test_bucket_index_edges() -> None:
    confs = (0.0, 0.19, 0.2, 0.5, 0.79, 0.8, 0.89, 0.9, 1.0)
    assert "".join(str(bucket_index(c)) for c in confs) == "001234455"


def test_fuzzy_score() -> None:
    assert fuzzy_score(None, "") == 1.0
    assert fuzzy_score("x", None) == 0.0
    assert fuzzy_score("Hinge", "HINGE ") == 1.0
    assert fuzzy_score("HINGE", "HINGES") == pytest.approx(10 / 11)


# ---------------------------------------------------------------------------
# Geometry and matching
# ---------------------------------------------------------------------------


def test_bbox_and_location_iou() -> None:
    assert bbox_iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(1 / 3)
    assert bbox_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    box = (0.0, 0.0, 10.0, 10.0)
    # page 2 present only in gold -> scores 0
    assert location_iou({1, 2}, {1: box, 2: box}, {1: box}) == pytest.approx(0.5)
    assert location_iou({1}, {1: box}, {1: box, 3: box}) == pytest.approx(0.5)


def _ref(num: str, page: int, y: float) -> SetRef:
    return SetRef(normalize_set_number(num), {page: (0.0, y, 100.0, y + 50.0)}, page)


def test_match_sets_duplicates_pair_in_document_order() -> None:
    gold = [_ref("1", 1, 0), _ref("2", 1, 100), _ref("1", 2, 0)]
    # list order differs from document order: pred[2] is the first "1" on the page
    pred = [_ref("1", 2, 0), _ref("2", 1, 100), _ref("001", 1, 0)]
    pairs = {(p.gold, p.pred, p.method) for p in match_sets(gold, pred)}
    assert pairs == {(0, 2, "number"), (1, 1, "number"), (2, 0, "number")}


def test_match_sets_iou_fallback() -> None:
    gold = [_ref("3", 1, 0), _ref("4", 1, 200)]
    # missing number, overlapping 3's region by IoU 50/150 = 1/3 >= 0.3
    pred = [SetRef("", {1: (0.0, 25.0, 100.0, 75.0)}, 1), SetRef("", {1: (0, 240, 100, 290)}, 1)]
    out = match_sets(gold, pred)
    matched = [(p.gold, p.pred, p.method) for p in out if p.gold is not None and p.pred is not None]
    # 4 vs pred[1]: overlap 10/90 = 0.11 < 0.3 -> missed + spurious
    assert matched == [(0, 0, "iou")]
    assert sum(p.pred is None for p in out) == 1
    assert sum(p.gold is None for p in out) == 1


def test_match_sets_iou_hungarian_is_global() -> None:
    gold = [_ref("", 1, 0), _ref("", 1, 30)]
    pred = [SetRef("", {1: (0.0, 30.0, 100.0, 80.0)}, 1), SetRef("", {1: (0, 0, 100, 50)}, 1)]
    matched = {(p.gold, p.pred) for p in match_sets(gold, pred)}
    assert matched == {(0, 1), (1, 0)}


def test_match_components_threshold_and_order() -> None:
    pred = gold_to_result(gdoc(fset("1", comps=[HW[2], HW[0], fc("ZZZ", "QQQ-9")]))).sets[0]
    out = match_components(HW[:3], pred.components)
    assert (0, 1, 100.0) in out
    assert (2, 0, 100.0) in out
    assert (1, None, None) in out  # LOCKSET missed
    assert (None, 2, None) in out  # ZZZ spurious


# ---------------------------------------------------------------------------
# Document metrics on hand-built fixtures
# ---------------------------------------------------------------------------


def test_set_recall_precision_status() -> None:
    gold = gdoc(
        fset("1", y=0, comps=HW[:1]),
        fset("2", y=100, comps=HW[1:2]),
        fset("3", y=200, status="not_used"),
        fset("4", y=300, comps=HW[2:3]),
    )
    pred = gold_to_result(gold)
    del pred.sets[3]  # miss set 4
    pred.sets[2].status = "active"  # wrong status on 3
    extra = gold_to_result(gdoc(fset("9", page=2, comps=HW[3:]))).sets[0]
    pred.sets.append(extra)
    ev = evaluate_document(pred, gold)
    m = ev.metrics
    assert (m.set_recall, m.set_precision, m.set_f1) == (0.75, 0.75, 0.75)
    assert m.status_accuracy == pytest.approx(2 / 3)
    assert m.set_fully_correct == 0.5  # sets 1 and 2 of 4
    kinds = sorted(e.kind for e in ev.errors)
    assert kinds == ["missed_set", "spurious_set", "wrong_status"]
    missed = next(e for e in ev.errors if e.kind == "missed_set")
    assert (missed.set_idx, missed.page, missed.line_id) == (None, 1, "L4")


def test_field_accuracy_and_confusion() -> None:
    gold = gdoc(fset("1", comps=HW))
    pred = gold_to_result(gold)
    c = pred.sets[0].components
    c[0].mfr, c[0].finish = sfield("652"), sfield("IVE")  # swapped
    c[1].mfr, c[1].finish = sfield("sch."), sfield("US26D")  # equivalent after normalization
    c[2].mfr, c[2].finish, c[2].notes = sfield(None), sfield(None), sfield("LCN 689")
    c[3].mfr, c[3].finish = sfield("XYZ"), sfield(None)
    ev = evaluate_document(pred, gold)
    acc = ev.metrics.field_accuracy
    assert acc["mfr"] == 0.25
    assert acc["finish"] == 0.25
    assert acc["notes"] == 0.75
    assert acc["qty"] == acc["description"] == acc["catalog_number"] == acc["qty_unit"] == 1.0
    assert ev.totals.confusion == {
        "mfr": {"mfr": 1, "finish": 1, "other": 1, "missing": 1},
        "finish": {"mfr": 1, "finish": 1, "other": 1, "missing": 1},
    }
    assert ev.metrics.set_fully_correct == 0.0
    severities = sorted({e.kind for e in ev.errors})
    assert severities == ["wrong_field", "wrong_finish", "wrong_mfr"]


def test_code_role_prefers_own_role() -> None:
    comp = gold_to_result(gdoc(fset("1", comps=[fc("X", mfr="PE", finish="PE")]))).sets[0]
    assert code_role("PE", "finish", comp.components[0]) == "finish"
    assert code_role("PE", "mfr", comp.components[0]) == "mfr"


def test_qty_and_null_rules() -> None:
    gold = gdoc(
        fset(
            "1",
            comps=[
                fc("HINGE", "5BB1", qty=3, unit="EA"),
                fc("SILENCER", "SR64", qty=None, unit="PR", notes=None),
                fc("CLOSER", "4040XP", qty=2),
            ],
        )
    )
    pred = gold_to_result(gold)
    c = pred.sets[0].components
    c[0].qty = Field[int | str](value="3", confidence=1.0)  # digit string == 3
    c[0].qty_unit = "ea."
    c[1].qty = Field[int | str](value="PR", confidence=1.0)  # non-numeric -> null == null
    c[1].notes = sfield("")  # "" == null
    c[2].qty = Field[int | str](value=3, confidence=1.0)
    ev = evaluate_document(pred, gold)
    assert ev.metrics.field_accuracy["qty"] == pytest.approx(2 / 3)
    assert ev.metrics.field_accuracy["qty_unit"] == 1.0
    assert ev.metrics.field_accuracy["notes"] == 1.0
    wrong = [e for e in ev.errors if e.kind == "wrong_qty"]
    assert [(e.gold, e.pred) for e in wrong] == [(2, 3)]


def test_missed_and_spurious_components_and_fuzzy() -> None:
    gold = gdoc(fset("1", comps=HW[:3]))
    pred = gold_to_result(gold)
    c = pred.sets[0].components
    c[0].description = sfield("HINGES")
    c[2] = c[2].model_copy(
        update={"description": sfield("KICK PLATE"), "catalog_number": sfield("K1050")}
    )
    ev = evaluate_document(pred, gold)
    t = ev.totals
    assert (t.n_gold_components, t.n_pred_components, t.n_matched_components) == (3, 3, 2)
    assert ev.metrics.component_recall == pytest.approx(2 / 3)
    assert ev.metrics.component_precision == pytest.approx(2 / 3)
    assert ev.metrics.field_accuracy["description"] == 0.5
    assert ev.metrics.fuzzy["description"] == pytest.approx((10 / 11 + 1) / 2)
    assert ev.metrics.fuzzy["catalog_number"] == 1.0
    assert (ev.sets[0].n_missed_components, ev.sets[0].n_spurious_components) == (1, 1)
    assert not ev.sets[0].fully_correct


def test_spurious_component_breaks_fully_correct() -> None:
    gold = gdoc(fset("1", comps=HW[:2]))
    pred = gold_to_result(gdoc(fset("1", comps=[*HW[:2], fc("SILENCER", "SR64")])))
    ev = evaluate_document(pred, gold)
    assert ev.metrics.component_recall == 1.0
    assert ev.metrics.component_precision == pytest.approx(2 / 3)
    assert ev.metrics.set_fully_correct == 0.0


def test_location_iou_per_set() -> None:
    gold = gdoc(fset("1", y=0, pages=[1, 2]), fset("2", page=3, y=0))
    pred = gold_to_result(gold)
    pred.sets[0].location.regions = [PageRegion(page=1, bbox=(0.0, 0.0, 100.0, 50.0))]
    pred.sets[1].location.regions = [PageRegion(page=3, bbox=(0.0, 25.0, 100.0, 75.0))]
    ev = evaluate_document(pred, gold)
    assert [s.location_iou for s in ev.sets] == pytest.approx([0.5, 1 / 3])
    assert ev.metrics.location_iou == pytest.approx((0.5 + 1 / 3) / 2)


def test_reliability_table() -> None:
    gold = gdoc(fset("1", comps=HW[:1]))
    pred = gold_to_result(gold, confidence=0.5)
    pred.sets[0].components[0].mfr = sfield("SCH", conf=0.95)
    ev = evaluate_document(pred, gold)
    buckets = [(b.count, b.correct, b.accuracy) for b in ev.totals.reliability]
    empty = (0, 0, None)
    assert buckets == [empty, empty, (5, 5, 1.0), empty, empty, (1, 0, 0.0)]


def test_gold_window() -> None:
    gold = gdoc(
        fset("1", page=1, comps=HW[:1]),
        fset("2", page=2, comps=HW[1:2]),
        fset("3", page=3, pages=[3, 4], comps=HW[2:3]),
        fset("4", page=4, comps=HW[3:]),
        gold_pages="2-3",
    )
    pred = gold_to_result(gold)
    pred.sets[2].set_number = sfield("33")  # unmatched by number
    pred.sets[2].location.regions = [PageRegion(page=3, bbox=(500.0, 500.0, 600.0, 600.0))]
    ev = evaluate_document(pred, gold)
    assert (ev.totals.n_gold_sets, ev.totals.n_pred_sets, ev.totals.n_matched_sets) == (2, 2, 1)
    assert ev.metrics.set_recall == 0.5
    assert {s.gold_idx for s in ev.sets if s.gold_idx is not None} == {1, 2}
    assert {s.pred_idx for s in ev.sets if s.pred_idx is not None} == {1, 2}


def test_document_duplicates_and_missing_numbers() -> None:
    gold = gdoc(
        fset("1", y=0, comps=HW[:1]),
        fset("1", y=100, comps=HW[1:2]),
        fset("2", y=200, comps=HW[2:3]),
    )
    pred = gold_to_result(gold)
    pred.sets[2].set_number = sfield(None)  # number not read -> IoU fallback
    pred.sets.reverse()  # list order must not matter; document order does
    ev = evaluate_document(pred, gold)
    assert ev.metrics.set_recall == 1.0
    assert ev.metrics.set_fully_correct == 1.0
    assert [(s.gold_idx, s.pred_idx, s.method) for s in ev.sets] == [
        (0, 2, "number"),
        (1, 1, "number"),
        (2, 0, "iou"),
    ]
    assert ev.totals.n_matched_by_iou == 1


def test_doc_id_default_and_override() -> None:
    gold = gdoc(fset("1"))
    pred = gold_to_result(gold)
    assert evaluate_document(pred, gold).doc_id == "book"
    assert evaluate_document(pred, gold, doc_id="abc").doc_id == "abc"


def test_aggregate_micro_and_macro() -> None:
    g1 = gdoc(fset("1", comps=HW[:2]), fset("2", y=100))
    g2 = gdoc(fset("1", comps=HW[2:]), fset("2", y=100), fset("3", y=200), fset("4", y=300))
    p1 = gold_to_result(g1)
    p2 = gold_to_result(g2)
    del p2.sets[1:]
    d1, d2 = evaluate_document(p1, g1), evaluate_document(p2, g2)
    s = aggregate([d1, d2])
    assert s.n_docs == 2
    assert s.metrics.set_recall == pytest.approx(3 / 6)
    assert s.macro["set_recall"] == pytest.approx((1.0 + 0.25) / 2)
    assert s.totals.fields["mfr"].total == 4
    assert s.metrics.set_fully_correct == pytest.approx(3 / 6)
    assert s.totals.reliability[5].count == 4 * 6
    assert aggregate([]).n_docs == 0
    DocEval.model_validate_json(d1.model_dump_json())  # JSON round trip
    assert type(s).model_validate_json(s.model_dump_json()) == s


# ---------------------------------------------------------------------------
# Hypothesis properties
# ---------------------------------------------------------------------------

WORDS = ["HINGE", "LOCKSET", "CLOSER", "STOP", "SILENCER", "KICK", "PLATE", "EXIT", "DEVICE"]
CATS = ["5BB1", "ND50PD", "4040XP", "WS406", "SR64", "K1050", "99EO", "4.5 X 4.5", "RHO"]
MFRS = ["IVE", "SCH", "LCN", "VON", "PE", "NO", "GLY", "ZER"]
FINS = ["626", "652", "689", "630", "US26D", "US32D", "PE", "AL", "BLK"]


@st.composite
def components(draw: st.DrawFn) -> FlatComponent:
    opt = st.none() | st.just("")
    return fc(
        desc=draw(st.lists(st.sampled_from(WORDS), max_size=3).map(" ".join) | opt),
        cat=draw(st.sampled_from(CATS) | st.none()),
        mfr=draw(st.sampled_from(MFRS) | st.none()),
        finish=draw(st.sampled_from(FINS) | st.none()),
        qty=draw(st.integers(1, 12) | st.none()),
        unit=draw(st.sampled_from(["EA", "PR", "SET"]) | st.none()),
        notes=draw(st.sampled_from(["NOTE A", "BY OTHERS", "(1)"]) | st.none()),
    )


@st.composite
def gold_docs(draw: st.DrawFn, min_sets: int = 0) -> FlatDocument:
    nums = draw(st.lists(st.integers(1, 300), min_size=min_sets, max_size=8, unique=True))
    sets = []
    for i, n in enumerate(nums):
        raw = draw(st.sampled_from([str(n), f"{n:03d}", f"{n}A", f"EX-{n:02d}.0"]))
        page = draw(st.integers(1, 4))
        status = draw(st.sampled_from(["active", "active", "not_used"]))
        comps = [] if status == "not_used" else draw(st.lists(components(), max_size=5))
        sets.append(fset(raw, page=page, y=60.0 * i, comps=comps, status=status))
    return gdoc(*sets)


SETTINGS = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@SETTINGS
@given(gold_docs())
def test_self_evaluation_is_perfect(gold: FlatDocument) -> None:
    ev = evaluate_document(gold_to_result(gold, confidence=1.0), gold)
    m = ev.metrics
    assert m.set_recall == m.set_precision == 1.0
    assert all(m.field_accuracy[f] == 1.0 for f in FIELDS)
    assert m.fuzzy == {"description": 1.0, "catalog_number": 1.0}
    assert m.set_fully_correct == 1.0
    assert m.status_accuracy == 1.0
    assert m.location_iou == 1.0
    assert ev.errors == []
    assert sum(ev.totals.confusion[r]["missing"] for r in ("mfr", "finish")) == 0
    rel = ev.totals.reliability
    assert sum(b.count for b in rel[:5]) == 0
    assert rel[5].accuracy in (None, 1.0)


@st.composite
def mutated(draw: st.DrawFn) -> tuple[FlatDocument, DocumentResult]:
    gold = draw(gold_docs())
    pred = gold_to_result(gold)
    for s in pred.sets:
        if draw(st.booleans()):
            s.set_number = sfield(draw(st.sampled_from(["", "999", s.set_number.value or ""])))
        if draw(st.integers(0, 4)) == 0:
            s.status = "not_used" if s.status == "active" else "active"
        for c in list(s.components):
            roll = draw(st.integers(0, 5))
            if roll == 0:
                s.components.remove(c)
            elif roll == 1:
                c.mfr, c.finish = c.finish, c.mfr
            elif roll == 2:
                c.qty = Field[int | str](value=draw(st.integers(1, 5)), confidence=0.3)
            c.description.confidence = draw(st.floats(0, 1))
        if draw(st.booleans()):
            s.components.extend(
                gold_to_result(gdoc(fset("x", comps=[draw(components())]))).sets[0].components
            )
    return gold, pred


@SETTINGS
@given(mutated(), st.randoms(use_true_random=False))
def test_metrics_invariant_under_permutation(
    case: tuple[FlatDocument, DocumentResult], rnd: random.Random
) -> None:

    gold, pred = case
    base = evaluate_document(pred, gold)
    shuffled = pred.model_copy(deep=True)
    rnd.shuffle(shuffled.sets)
    for s in shuffled.sets:
        rnd.shuffle(s.components)
    gold_shuffled = gold.model_copy(deep=True)
    rnd.shuffle(gold_shuffled.sets)
    for gs in gold_shuffled.sets:
        rnd.shuffle(gs.components)
    for ev in (evaluate_document(shuffled, gold), evaluate_document(pred, gold_shuffled)):
        assert (ev.metrics, ev.totals) == (base.metrics, base.totals)


@SETTINGS
@given(gold_docs(min_sets=1), st.data())
def test_deleting_k_sets_lowers_recall_by_k_over_n(gold: FlatDocument, data: st.DataObject) -> None:
    n = len(gold.sets)
    k = data.draw(st.integers(0, n))
    drop = set(data.draw(st.permutations(range(n)))[:k])
    pred = gold_to_result(gold)
    pred.sets = [s for i, s in enumerate(pred.sets) if i not in drop]
    m = evaluate_document(pred, gold).metrics
    assert math.isclose(m.set_recall, 1 - k / n)
    assert m.set_precision == 1.0
    assert math.isclose(m.set_fully_correct, 1 - k / n)
