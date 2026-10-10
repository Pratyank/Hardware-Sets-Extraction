"""Preload the three demo books into the review UI (idempotent).

For each demo book: ingest it if its tokens are not cached yet (same worker the CLI's
``hwsets ingest`` uses), extract with ``pipeline.extract`` + the cached drawn rules (same as
``hwsets extract``), write ``<data>/results/<doc_id>.json`` and render its hardware pages to PNG.

    uv run python scripts/demo.py               # data dir ./data
    uv run python scripts/demo.py --data path/to/data

A book whose PDF is not under ``<data>/raw`` and whose tokens are not cached is skipped with a
note; the script only fails if no demo book could be prepared.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from hwsets.api.storage import atomic_write_text
from hwsets.cli import RenderMode, _ingest_one
from hwsets.ingest import render
from hwsets.ingest.store import TokenStore, doc_id_for, sha256_file
from hwsets.pipeline import extract

DEMO_BOOKS: dict[str, str] = {
    "valor-acres-building-e--087100-door-hardware-rev-2": "list format, redlines",
    "roselle-public-library--087100-fl-door-hardware-ifb-revised": "ruled table",
    "lyons-township-hs--project-manual-1": "project manual, NOT USED sets",
}


def _find_pdfs(raw: Path, wanted: set[str]) -> dict[str, Path]:
    """Demo doc id -> PDF under ``raw`` (ids are derived from paths exactly as the CLI does)."""
    found: dict[str, Path] = {}
    if not raw.is_dir():
        return found
    for pdf in sorted(raw.rglob("*.pdf")):
        if "uploads" in pdf.relative_to(raw).parts[:1]:
            continue
        doc_id = doc_id_for(pdf, raw)
        if doc_id in wanted:
            found[doc_id] = pdf
    return found


def _check_not_holdout(data: Path) -> None:
    splits = data / "splits.json"
    if not splits.is_file():
        return
    holdout = set(json.loads(splits.read_text("utf-8")).get("holdout", {}))
    leaked = holdout & set(DEMO_BOOKS)
    if leaked:
        raise SystemExit(f"refusing to process held-out books: {sorted(leaked)}")


def prepare(data: Path, doc_id: str, pdf: Path | None) -> int | None:
    """Ingest (if needed), extract and render one book. Returns its set count or None."""
    raw, tokens_root, pages_root = data / "raw", data / "tokens", data / "pages"
    store = TokenStore(tokens_root)
    t0 = time.perf_counter()
    if pdf is not None:
        _, n_pages, _cands, cached = _ingest_one(
            pdf,
            raw_root=raw,
            tokens_root=tokens_root,
            pages_root=pages_root,
            mode=RenderMode.candidates,
            force=False,
        )
        store.register(doc_id, pdf.relative_to(raw).as_posix(), sha256_file(pdf), n_pages)
        state = "cached" if cached else "ingested"
    elif doc_id in store.index():
        state = "tokens-only"
    else:
        print(f"skip    {doc_id}: no PDF under {raw} and no cached tokens")
        return None

    source_pdf, pages_info, tokens = store.load_all(doc_id)
    result = extract(source_pdf, pages_info, tokens, store.load_rules(doc_id))
    atomic_write_text(data / "results" / f"{doc_id}.json", result.model_dump_json(indent=1))
    if pdf is not None and result.hardware_pages:
        sha = store.resolve(doc_id)["sha256"]
        render.render_pages(pdf, pages_root, sha, result.hardware_pages)
    n_comp = sum(len(s.components) for s in result.sets)
    not_used = sum(1 for s in result.sets if s.status == "not_used")
    print(
        f"{state:11} {doc_id}: sets={len(result.sets)} components={n_comp} "
        f"not_used={not_used} pages={_span(result.hardware_pages)} "
        f"({time.perf_counter() - t0:.1f}s)"
    )
    return len(result.sets)


def _span(pages: list[int]) -> str:
    return f"{pages[0]}-{pages[-1]}" if pages else "-"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=Path("data"), help="data directory")
    args = ap.parse_args(argv)
    data: Path = args.data
    _check_not_holdout(data)
    pdfs = _find_pdfs(data / "raw", set(DEMO_BOOKS))
    ready = 0
    for doc_id, why in DEMO_BOOKS.items():
        print(f"--      {doc_id} [{why}]")
        if prepare(data, doc_id, pdfs.get(doc_id)) is not None:
            ready += 1
    print(f"demo: {ready}/{len(DEMO_BOOKS)} books ready in {data / 'results'}")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
