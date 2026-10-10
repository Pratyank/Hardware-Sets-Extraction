"""Evaluation against gold labels: matching, metrics and reports (PLAN.md Phase 6)."""

from hwsets.eval.convert import gold_to_result
from hwsets.eval.metrics import aggregate, evaluate_document
from hwsets.eval.normalize import normalize_set_number, parse_page_window
from hwsets.eval.schema import DocEval, EvalSummary

__all__ = [
    "DocEval",
    "EvalSummary",
    "aggregate",
    "evaluate_document",
    "gold_to_result",
    "normalize_set_number",
    "parse_page_window",
]
