"""Debug: run header induction over a page range of a dev book."""

import sys
from pathlib import Path

from hwsets.ingest.store import TokenStore
from hwsets.layout.lines import group_lines
from hwsets.segment.headers import induce_headers

store = TokenStore(Path("data/tokens"))
doc, pages = sys.argv[1], sys.argv[2]
sha = store.resolve(doc)["sha256"]
a, _, b = pages.partition("-")
toks, lines = {}, []
for p in range(int(a), int(b or a) + 1):
    pt = store.page_tokens(sha, p)
    toks.update({t.id: t for t in pt})
    lines += group_lines(pt)
ind = induce_headers(lines, toks)
print("candidates", ind.candidates, "sig", ind.signature, ind.warnings)
for h in ind.headers:
    d = " ".join(toks[i].text for i in h.desc_token_ids)
    print(f"  {h.line_id:10} ids={h.set_ids} desc={d[:60]!r}")
