"""Evaluation report writer: ``report.md`` (human) and ``report.json`` (everything)."""

from __future__ import annotations

import json
import math
from pathlib import Path

from hwsets.eval.schema import (
    FIELDS,
    FUZZY_FIELDS,
    GOLD_ROLES,
    PRED_ROLES,
    DocEval,
    ErrorItem,
    EvalSummary,
)

__all__ = ["error_link", "render_markdown", "worst_errors", "write_report"]

N_WORST = 10
_BOOK_HEADER = [
    *["doc", "pages", "gold", "pred", "matched", "R", "P", "F1", "status"],
    *["comp R", "comp P", "mfr", "finish", "qty", "loc IoU", "fully correct"],
]


def error_link(err: ErrorItem, ui_base: str = "http://localhost:8000") -> str:
    """UI deep link: ``{ui_base}/#doc={doc_id}&set={set_idx}``.

    A missed set has no predicted index, so it links to its gold page instead
    (``#doc={doc_id}&page={page}``).
    """
    base = ui_base.rstrip("/")
    if err.set_idx is not None:
        return f"{base}/#doc={err.doc_id}&set={err.set_idx}"
    if err.page is not None:
        return f"{base}/#doc={err.doc_id}&page={err.page}"
    return f"{base}/#doc={err.doc_id}"


def worst_errors(docs: list[DocEval], n: int = N_WORST) -> list[ErrorItem]:
    """The ``n`` most severe errors (missed set > wrong mfr/finish > wrong qty > others).

    Ties break deterministically on document, page, set number and field.
    """
    errors = [e for d in docs for e in d.errors]
    errors.sort(
        key=lambda e: (
            -e.severity,
            e.doc_id,
            e.page if e.page is not None else math.inf,
            e.set_number,
            e.field or "",
        )
    )
    return errors[:n]


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.1f}%"


def _cell(v: object) -> str:
    if v is None:
        return "∅"
    return str(v).replace("|", "\\|").replace("\n", " ")


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def render_markdown(
    summary: EvalSummary, docs: list[DocEval], ui_base: str = "http://localhost:8000"
) -> str:
    m, t = summary.metrics, summary.totals
    lines = ["# Evaluation report", "", f"Documents: {summary.n_docs}", "", "## Totals", ""]
    lines += _table(
        ["metric", "micro", "macro"],
        [
            ["set recall", _pct(m.set_recall), _pct(summary.macro.get("set_recall"))],
            ["set precision", _pct(m.set_precision), _pct(summary.macro.get("set_precision"))],
            ["set F1", _pct(m.set_f1), _pct(summary.macro.get("set_f1"))],
            ["not_used status accuracy", _pct(m.status_accuracy), "-"],
            ["component recall", _pct(m.component_recall), "-"],
            ["component precision", _pct(m.component_precision), "-"],
            ["component F1", _pct(m.component_f1), "-"],
            [
                "location IoU (mean)",
                f"{m.location_iou:.3f}",
                _f3(summary.macro.get("location_iou")),
            ],
            [
                "set_fully_correct",
                _pct(m.set_fully_correct),
                _pct(summary.macro.get("set_fully_correct")),
            ],
        ],
    )
    lines += [
        "",
        f"Sets: {t.n_gold_sets} gold, {t.n_pred_sets} predicted, {t.n_matched_sets} matched "
        f"({t.n_matched_by_iou} by IoU fallback). Components (in matched sets): "
        f"{t.n_gold_components} gold, {t.n_pred_components} predicted, "
        f"{t.n_matched_components} matched.",
        "",
        "## Per book",
        "",
    ]
    lines += _table(
        _BOOK_HEADER,
        [
            [
                _cell(d.doc_id),
                _cell(d.gold_pages or "all"),
                str(d.totals.n_gold_sets),
                str(d.totals.n_pred_sets),
                str(d.totals.n_matched_sets),
                _pct(d.metrics.set_recall),
                _pct(d.metrics.set_precision),
                _pct(d.metrics.set_f1),
                _pct(d.metrics.status_accuracy),
                _pct(d.metrics.component_recall),
                _pct(d.metrics.component_precision),
                _pct(d.metrics.field_accuracy.get("mfr")),
                _pct(d.metrics.field_accuracy.get("finish")),
                _pct(d.metrics.field_accuracy.get("qty")),
                f"{d.metrics.location_iou:.3f}",
                _pct(d.metrics.set_fully_correct),
            ]
            for d in docs
        ],
    )
    lines += ["", "## Field accuracy (matched components)", ""]
    rows = []
    for f in FIELDS:
        c = t.fields.get(f)
        fz = t.fuzzy.get(f) if f in FUZZY_FIELDS else None
        rows.append(
            [
                f,
                f"{c.correct}/{c.total}" if c else "0/0",
                _pct(c.accuracy) if c else "-",
                f"{fz.mean:.3f}" if fz else "-",
            ]
        )
    lines += _table(["field", "correct/total", "exact", "fuzzy"], rows)
    lines += [
        "",
        "## Manufacturer vs finish confusion",
        "",
        "Rows: the role of a gold code. Columns: where that code landed in the prediction "
        "(`missing` = absent or a different value).",
        "",
    ]
    lines += _table(
        ["gold \\ pred", *PRED_ROLES],
        [[g, *(str(t.confusion.get(g, {}).get(p, 0)) for p in PRED_ROLES)] for g in GOLD_ROLES],
    )
    lines += ["", "## Reliability (predicted field confidence vs exact accuracy)", ""]
    lines += _table(
        ["bucket", "count", "accuracy"],
        [
            [
                f"[{b.lo:.1f}, {b.hi:.1f}{']' if i == len(t.reliability) - 1 else ')'}",
                str(b.count),
                _pct(b.accuracy),
            ]
            for i, b in enumerate(t.reliability)
        ],
    )
    lines += ["", f"## {N_WORST} worst errors", ""]
    worst = worst_errors(docs)
    if not worst:
        lines.append("No errors.")
    else:
        lines += _table(
            ["#", "kind", "doc", "set", "page", "line", "field", "gold", "pred", "link"],
            [
                [
                    str(i),
                    e.kind,
                    _cell(e.doc_id),
                    _cell(e.set_number),
                    _cell(e.page),
                    _cell(e.line_id),
                    _cell(e.field),
                    _cell(e.gold),
                    _cell(e.pred),
                    f"[open]({error_link(e, ui_base)})",
                ]
                for i, e in enumerate(worst, 1)
            ],
        )
    return "\n".join(lines) + "\n"


def _f3(x: float | None) -> str:
    return "-" if x is None else f"{x:.3f}"


def write_report(
    summary: EvalSummary,
    docs: list[DocEval],
    out_dir: Path,
    ui_base: str = "http://localhost:8000",
) -> None:
    """Write ``out_dir/report.md`` and ``out_dir/report.json`` (creates ``out_dir``)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    worst = [
        {**e.model_dump(mode="json"), "link": error_link(e, ui_base)} for e in worst_errors(docs)
    ]
    payload = {
        "summary": summary.model_dump(mode="json"),
        "docs": [d.model_dump(mode="json") for d in docs],
        "worst_errors": worst,
    }
    (out_dir / "report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "report.md").write_text(render_markdown(summary, docs, ui_base), encoding="utf-8")
