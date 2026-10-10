"""Golden regression gate: metrics on the gold books may not drop by more than one point.

Runs the real pipeline on the ingested gold books (data/tokens + data/gold). Skipped when the
specbook data is not available (it is not committed). Refresh the snapshot deliberately with
``make snapshot`` (runs eval, then scripts/update_snapshot.py) after an intended change;
never to hide a regression.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hwsets.eval import aggregate, evaluate_document
from hwsets.ingest.store import TokenStore
from hwsets.models import FlatDocument
from hwsets.pipeline import extract

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = json.loads((Path(__file__).parent / "snapshot.json").read_text("utf-8"))
TOLERANCE = 0.01


def _gold_docs() -> list[str]:
    gold_dir = ROOT / "data" / "gold"
    out = []
    for p in sorted(gold_dir.glob("*.gold.json")):
        data = json.loads(p.read_text("utf-8"))
        if data.get("_final") and p.name.removesuffix(".gold.json") in SNAPSHOT["per_book"]:
            out.append(p.name.removesuffix(".gold.json"))
    return out


def _available() -> bool:
    index = ROOT / "data" / "tokens" / "index.json"
    return index.exists() and all(d in json.loads(index.read_text()) for d in _gold_docs())


pytestmark = pytest.mark.skipif(not _available(), reason="specbook token cache not available")


def test_gold_metrics_do_not_regress() -> None:
    store = TokenStore(ROOT / "data" / "tokens")
    evals = []
    for doc_id in _gold_docs():
        source_pdf, pages, tokens = store.load_all(doc_id)
        result = extract(source_pdf, pages, tokens, store.load_rules(doc_id))
        gold = FlatDocument.model_validate_json(
            (ROOT / "data" / "gold" / f"{doc_id}.gold.json").read_text("utf-8")
        )
        de = evaluate_document(result, gold, doc_id=doc_id)
        evals.append(de)
        book = SNAPSHOT["per_book"][doc_id]
        assert de.metrics.set_recall >= book["set_recall"] - TOLERANCE, doc_id
    summary = aggregate(evals)
    assert summary.metrics.set_recall >= SNAPSHOT["set_recall"] - TOLERANCE
    assert summary.metrics.set_fully_correct >= SNAPSHOT["set_fully_correct"] - TOLERANCE
