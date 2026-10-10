"""Group eval field mismatches by doc and field (from eval/report.json)."""

import json
import sys
from collections import Counter
from pathlib import Path

r = json.loads(Path("eval/report.json").read_text())
want = sys.argv[1] if len(sys.argv) > 1 else None
n_show = int(sys.argv[2]) if len(sys.argv) > 2 else 6
for d in r["docs"]:
    if want and want not in d["doc_id"]:
        continue
    c = Counter()
    ex: dict[str, list[str]] = {}
    for s in d["sets"]:
        for comp in s["components"]:
            for diff in comp["diffs"]:
                f = diff["field"] if isinstance(diff, dict) else str(diff)
                c[f] += 1
                ex.setdefault(f, []).append(f"{s['set_number']}: {diff}")
        if s["n_missed_components"] or s["n_spurious_components"]:
            c["missed/spurious comps"] += s["n_missed_components"] + s["n_spurious_components"]
    print(f"== {d['doc_id'][:50]} {dict(c)}")
    for f, lst in ex.items():
        for e in lst[:n_show]:
            print("   ", f, "|", e[:230])
