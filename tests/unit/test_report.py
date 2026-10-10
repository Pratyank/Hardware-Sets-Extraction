"""Report writer: report.md / report.json content, worst-error ordering and UI links."""

from __future__ import annotations

import json
from pathlib import Path

from hwsets.eval import aggregate, evaluate_document, gold_to_result, write_report
from hwsets.eval.report import error_link, render_markdown, worst_errors
from hwsets.eval.schema import DocEval, ErrorItem
from hwsets.models import Field, FlatComponent, FlatDocument, FlatLocation, FlatSet, PageRegion


def _set(num: str, page: int, y: float, comps: list[FlatComponent]) -> FlatSet:
    return FlatSet(
        set_number=num,
        location=FlatLocation(
            pages=[page],
            regions=[PageRegion(page=page, bbox=(0.0, y, 100.0, y + 50.0))],
            line_range=(f"p{page}_l{int(y)}", f"p{page}_l{int(y) + 9}"),
        ),
        components=comps,
    )


def _docs() -> list[DocEval]:
    comps = [
        FlatComponent(qty=3, description="HINGE", catalog_number="5BB1", mfr="IVE", finish="652"),
        FlatComponent(
            qty=1, description="CLOSER", catalog_number="4040XP", mfr="LCN", finish="689"
        ),
    ]
    gold_a = FlatDocument(
        source_pdf="a.pdf",
        sets=[_set("1", 3, 0, comps), _set("2", 3, 100, comps[:1]), _set("3", 4, 0, [])],
    )
    pred_a = gold_to_result(gold_a)
    c0 = pred_a.sets[0].components[0]
    c0.mfr = Field[str](value="652", confidence=0.9)  # mfr and finish swapped
    c0.finish = Field[str](value="IVE", confidence=0.85)
    pred_a.sets[0].components[1].qty = Field[int | str](value=2, confidence=0.4)  # wrong qty
    pred_a.sets[1].components[0].notes = Field[str](value="x", confidence=0.1)  # other
    del pred_a.sets[2]  # missed set
    gold_b = FlatDocument(source_pdf="b.pdf", gold_pages="5-6", sets=[_set("7", 5, 0, comps)])
    return [
        evaluate_document(pred_a, gold_a, doc_id="doc-a"),
        evaluate_document(gold_to_result(gold_b), gold_b, doc_id="doc-b"),
    ]


def test_worst_errors_ordered_by_severity() -> None:
    worst = worst_errors(_docs())
    assert [e.kind for e in worst] == ["missed_set", "wrong_finish", "wrong_mfr", "wrong_qty",
                                       "wrong_field"]  # fmt: skip
    assert worst[0].page == 4 and worst[0].set_idx is None
    assert worst[1].line_id == "p3_l0" and worst[1].set_idx == 0
    assert len(worst_errors(_docs(), n=2)) == 2


def test_error_link() -> None:
    e = ErrorItem(doc_id="d", kind="wrong_qty", severity=2, set_number="1", set_idx=4, page=2)
    assert error_link(e, "http://ui:9/") == "http://ui:9/#doc=d&set=4"
    missed = e.model_copy(update={"set_idx": None})
    assert error_link(missed) == "http://localhost:8000/#doc=d&page=2"
    assert error_link(missed.model_copy(update={"page": None})).endswith("#doc=d")


def test_write_report(tmp_path: Path) -> None:
    docs = _docs()
    summary = aggregate(docs)
    out = tmp_path / "eval"
    write_report(summary, docs, out, ui_base="http://ui")
    payload = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert set(payload) == {"summary", "docs", "worst_errors"}
    assert payload["summary"]["n_docs"] == 2
    assert payload["summary"]["metrics"]["set_recall"] == 3 / 4
    assert [d["doc_id"] for d in payload["docs"]] == ["doc-a", "doc-b"]
    assert payload["worst_errors"][0]["link"] == "http://ui/#doc=doc-a&page=4"
    assert payload["summary"]["totals"]["confusion"]["mfr"]["finish"] == 1

    md = (out / "report.md").read_text(encoding="utf-8")
    for heading in (
        "## Totals",
        "## Per book",
        "## Field accuracy",
        "## Manufacturer vs finish confusion",
        "## Reliability",
        "## 10 worst errors",
    ):
        assert heading in md
    assert "| doc-a | all | 3 | 2 | 2 |" in md
    assert "| doc-b | 5-6 | 1 | 1 | 1 |" in md
    assert "| mfr | 4 | 1 | 0 | 0 |" in md  # gold role mfr: 4 kept, 1 landed in finish
    assert "| [0.9, 1.0] |" in md
    assert "[open](http://ui/#doc=doc-a&set=0)" in md


def test_render_markdown_no_errors() -> None:
    gold = FlatDocument(source_pdf="c.pdf", sets=[_set("1", 1, 0, [])])
    docs = [evaluate_document(gold_to_result(gold), gold)]
    md = render_markdown(aggregate(docs), docs)
    assert "No errors." in md
    assert "| set recall | 100.0% | 100.0% |" in md
