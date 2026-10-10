"""Refresh tests/golden/snapshot.json from eval/report.json (run `hwsets eval` first).

Only after an intended improvement; never to hide a regression.
"""

import json
from pathlib import Path

r = json.loads(Path("eval/report.json").read_text())
m = r["summary"]["metrics"]
snap = {
    "set_recall": round(m["set_recall"], 4),
    "set_fully_correct": round(m["set_fully_correct"], 4),
    "component_f1": round(m.get("component_f1", 0.0), 4),
    "per_book": {
        d["doc_id"]: {
            "set_recall": round(d["metrics"]["set_recall"], 4),
            "set_fully_correct": round(d["metrics"]["set_fully_correct"], 4),
        }
        for d in r["docs"]
    },
}
Path("tests/golden/snapshot.json").write_text(json.dumps(snap, indent=1) + "\n")
print({k: v for k, v in snap.items() if k != "per_book"})
