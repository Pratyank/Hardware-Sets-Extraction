"""Debug helper: print visual lines with token x-positions for a page (dev books only)."""

import sys
from pathlib import Path

from hwsets.ingest.store import TokenStore
from hwsets.layout.lines import group_lines

store = TokenStore(Path("data/tokens"))
doc, pages = sys.argv[1], sys.argv[2]
sha = store.resolve(doc)["sha256"]
a, _, b = pages.partition("-")
for p in range(int(a), int(b or a) + 1):
    toks = store.page_tokens(sha, p)
    by_id = {t.id: t for t in toks}
    print(f"===== page {p}")
    for ln in group_lines(toks):
        cells = []
        prev = None
        for tid in ln.token_ids:
            t = by_id[tid]
            if prev is None or t.bbox[0] - prev.bbox[2] > 6:
                cells.append(f"|{t.bbox[0]:.0f}:{t.text}")
            else:
                cells.append(t.text)
            prev = t
        b_ = "B" if by_id[ln.token_ids[0]].bold else " "
        print(f"{ln.bbox[1]:6.1f}{b_} " + " ".join(cells))
