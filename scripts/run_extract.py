"""Debug: run the pipeline on one ingested (dev) book and print a summary."""

import sys
import time
from pathlib import Path

from hwsets.ingest.store import TokenStore
from hwsets.pipeline import extract

store = TokenStore(Path("data/tokens"))
doc = sys.argv[1]
meta = store.resolve(doc)
sha = meta["sha256"]
pages = store.pages(sha)
t0 = time.time()
tokens = {p.page: store.page_tokens(sha, p.page) for p in pages}
t1 = time.time()
res = extract(meta["source_pdf"], pages, tokens)
t2 = time.time()
print(
    f"load {t1 - t0:.1f}s extract {t2 - t1:.1f}s  pages={res.hardware_pages[:3]}..{res.hardware_pages[-3:]} sets={len(res.sets)}"
)
for k, v in res.column_roles.items():
    print("  col", k, v)
verbose = "-v" in sys.argv
for s in res.sets[: (999 if verbose else 4)]:
    print(
        f"SET {s.set_number.value!r} [{s.status}] desc={s.description.value!r} conf={s.confidence} comps={len(s.components)} pages={[r.page for r in s.location.regions]}"
    )
    for c in s.components:
        print(
            f"    {c.qty.value!s:>4} {c.qty_unit or '':4} | {c.description.value} | {c.catalog_number.value} | fin={c.finish.value} | mfr={c.mfr.value} ({c.mfr_resolved}) | notes={(c.notes.value or '')[:40]}"
        )
print("warnings:", len(res.warnings))
for w in res.warnings[:15]:
    print("  ", w)
