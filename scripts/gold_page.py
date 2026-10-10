"""Print the gold sets located on one page (for spot-checking gold against the image)."""

import json
import sys
from pathlib import Path

doc, page = sys.argv[1], int(sys.argv[2])
d = json.loads(Path(f"data/gold/{doc}.gold.json").read_text())
for s in d["sets"]:
    if page not in s["location"]["pages"]:
        continue
    print(
        f"SET {s['set_number']} [{s['status']}] desc={s.get('description')!r} pages={s['location']['pages']}"
    )
    for c in s["components"]:
        u = " ?" if c.get("_uncertain") else ""
        print(
            f"  {c.get('qty')!s:>4} {c.get('qty_unit') or '':4}| {c.get('description')} | {c.get('catalog_number')} | fin={c.get('finish')} | mfr={c.get('mfr')} | n={c.get('notes')}{u}"
        )
