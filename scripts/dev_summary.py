"""Run the pipeline over dev + negative books only (never gold/holdout) and summarize."""

import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from hwsets.ingest.store import TokenStore
from hwsets.pipeline import extract

SPLITS = json.loads(Path("data/splits.json").read_text())
DOCS = SPLITS["dev"] + SPLITS["negatives"]
FORBIDDEN = set(SPLITS["holdout"]) | set(SPLITS["gold"]) | set(SPLITS["duplicates"])


def run(doc: str) -> str:
    assert doc not in FORBIDDEN
    store = TokenStore(Path("data/tokens"))
    meta = store.resolve(doc)
    pages = store.pages(meta["sha256"])
    t = time.time()
    res = extract(
        meta["source_pdf"],
        pages,
        {p.page: store.page_tokens(meta["sha256"], p.page) for p in pages},
    )
    n_c = sum(len(s.components) for s in res.sets)
    nu = sum(s.status == "not_used" for s in res.sets)
    empty = sum(s.status == "active" and not s.components for s in res.sets)
    pg = f"{res.hardware_pages[0]}-{res.hardware_pages[-1]}" if res.hardware_pages else "-"
    return f"{doc[:45]:45} sets={len(res.sets):4} comps={n_c:5} not_used={nu:2} empty={empty:2} pages={pg:9} warn={len(res.warnings):3} {time.time() - t:5.1f}s"


if __name__ == "__main__":
    with ProcessPoolExecutor(8) as pool:
        for line in pool.map(run, DOCS):
            print(line)
