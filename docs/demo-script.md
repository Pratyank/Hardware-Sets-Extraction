# Demo video script (~4 min)

Everything shown runs locally, deterministically, with no API key.

## Before recording

```bash
make setup
uv run python scripts/demo.py --pe-sample pe-finish.pdf   # preloads 3 books, writes the PE sample
make eval                                                 # refreshes eval/report.md
make serve                                                # http://localhost:8000
```

(`make demo` does the preload and then serves. With Docker: `docker compose up`, with the PDFs
under `./data/raw`.)

Open these tabs in order:

1. `eval/report.md` in an editor with Markdown preview, scrolled to **Manufacturer vs finish
   confusion**.
2. The review UI: `http://localhost:8000/#doc=valor-acres-building-e--087100-door-hardware-rev-2&set=0`

Set the browser to about 1440x900, zoom 100%, and close the help dialog. Numbers quoted below
come from the current report (8 gold books, 279 gold sets). If a re-run changes them, read the
numbers off the report rather than these notes.

---

## 1. Problem and thesis (0:00–0:30)

**Screen:** the Valor Acres hardware schedule page in the UI (page 7), no set selected.

**Say:**
> "Every door on a building project gets a hardware set: hinges, locks, closers, each with a
> catalogue number, a manufacturer and a finish. Estimators retype these schedules from PDF
> spec books by hand. Every book has its own layout: lists, ruled tables, 300-page project
> manuals, redlines. So a per-format parser doesn't scale.
> The thesis: treat the page as geometry. Find the set headers, infer the columns from how the
> tokens line up, and decide each column's role from what is in it. It's deterministic, and every
> value points back to the exact PDF tokens it came from."

## 2. Confusion matrix, and the same "PE" two ways (0:30–1:15)

**Screen:** `eval/report.md`, **Manufacturer vs finish confusion** table.

**Say (point at the off-diagonal cells):**
> "The hardest ambiguity in this domain is manufacturer versus finish. Codes like `PE` mean
> Pemko as a manufacturer and painted enamel as a finish. Across 8 hand-labelled books there are
> 1,482 manufacturer codes and 1,546 finish codes, and zero land in the wrong role. The `1` under
> *other* is one manufacturer code we failed to pick up at all, not a swap."

**Screen:** switch to the terminal and run:

```bash
uv run hwsets extract morris-bank--030f2d1d-morris-bank-macon-spec-manual-issued-for-const-1-26-26-full-specs --stdout \
  | python -c "import json,sys; s=json.load(sys.stdin)['sets'][0]; c=next(c for c in s['components'] if c['mfr']['value']=='PE'); print('set', s['set_number']['value'], '|', c['description']['value'], '| mfr', c['mfr']['value'], '->', c['mfr_resolved'], '| finish', c['finish']['value'])"
```

Expected output: `set 101 | Continuous Hinge | mfr PE -> Pemko | finish None`

**Say:**
> "Morris Bank, set 101: a continuous hinge with `PE` in the right-hand column and no finish
> printed. That column, at x≈503 on pages 233–290, scores as manufacturer with margin 0.87, so
> `PE` resolves to Pemko."

**Screen:** back in the UI, click **Upload PDF** (top bar) and choose `pe-finish.pdf`. The button
shows *Uploading %* and then *Extracting…*. A toast reads "Extracted 2 sets from pe-finish.pdf"
and the new document `uploads--pe-finish` opens.

**Click:** set **1** in the sidebar, then hover the **Finish** cell of the *CLOSER* row.

**Say:**
> "Same two letters in a different book. Here `PE` sits in the finish column, next to a column
> of real manufacturers: LCN, Ives, Schlage. The column decides, not the code. `PE` stays a
> finish, and the manufacturer is LCN. This book went through the same code path, live:
> upload, tokenize, extract."

## 3. Three books in the UI (1:15–3:15)

### 3a. List format with redlines: Valor Acres (1:15–1:55)

**Click:** document picker, then `valor-acres-building-e--087100-door-hardware-rev-2`. Then
click set **1** in the sidebar.

**Say:**
> "Left is the set list with confidence badges. Centre is the page with each set's region
> tinted. Right is the editable component table."

**Click:** press `j` a few times to step through sets 2 and 3. Set 3 spans pages 7–8, and the
viewer scrolls across the page break.

**Click:** the sidebar filter, type `12`, select set **12** (pages 9–10).

**Say:**
> "This book is a revision. The door list in set 12's heading is struck through on the page.
> Struck tokens are flagged at ingest, from the font flag or from a drawn line through the
> word's middle band, so deleted content doesn't leak into the output. The set also continues
> onto page 10 and stays one set."

**Click:** **Diagnostics** tab.

**Say:**
> "Column diagnostics show each inferred column, its role and the margin it won by. That's
> where a reviewer looks first when a book goes wrong."

### 3b. Ruled table: Roselle Public Library (1:55–2:35)

**Click:** document picker, then `roselle-public-library--087100-fl-door-hardware-ifb-revised`.
**Components** tab, set **1.2** (second in the list).

**Say:**
> "A completely different format: a dense ruled table with dotted set numbers like 1.2 and
> 3.5. There's no Roselle-specific code. The drawn rules feed the same row segmentation, and
> the same role assignment finds description, catalogue, finish and manufacturer."

**Click:** segmented control **Needs review**.

**Say (if the list is empty, which is expected for this book):**
> "'Needs review' filters to sets with a field below 0.6 confidence. Nothing in this book
> falls below that. Confidence is calibrated: in the report, fields at 0.9 or above are right
> 99.7% of the time."

**Click:** segmented control **All**.

### 3c. Project manual with NOT USED sets: Lyons Township HS (2:35–3:15)

**Click:** document picker, then `lyons-township-hs--project-manual-1`.

**Say:**
> "A 309-page project manual. The hardware schedule is pages 285 to 294, found by header
> induction and not by a page range anyone typed in."

**Click:** segmented control **Not used**. Four sets are listed: 5, 16, 21, 22. Click **5**.

**Say:**
> "Sets the architect retired still keep their numbers. They come out with status `not_used`
> and zero components, never as an empty active set. They show greyed out in the list."

**Click:** segmented control **All**, then set **6**.

## 4. Hover to see the evidence, then correct one field (3:15–3:45)

**Click:** in set 6 of Lyons, hover the **Catalog** cell of the first row, then the **MFR**
cell.

**Say:**
> "Hovering any field lights up its exact source tokens on the page, and the footer shows its
> confidence and token ids. Nothing in the output is generated text. It's all a pointer into
> the PDF."

**Click:** click into a **Description** cell (cells are edited in place), change one word, then
press `Esc` to leave the field. The cell turns *edited by you*.

**Say:**
> "Edits are marked as human-sourced with confidence 1.0..."

**Click:** **Save** (or `Ctrl S`). Toast: "Correction saved". Then **Export as gold**.

> "...saved to a corrections file, never over the extractor's output. Export turns the corrected
> book into a gold file for the evaluator, so the review UI is also the labelling tool."

## 5. Tradeoffs and next steps (3:45–4:15)

**Screen:** `eval/report.md`, **10 worst errors**.

**Say:**
> "Tradeoffs. Deterministic first: it's reproducible, cheap, needs no key, and every value is
> grounded. The cost is that unusual layouts need a rule, not a prompt. Here are the misses:
> quantities printed in a merged cell, and descriptions that run into a mounting note. Next
> steps: a narrow LLM fallback that may only answer with token ids for low-margin columns, more
> labelled books from more architects, and batch upload for whole project folders."

**End on:** the UI with the Lyons schedule page and a selected set highlighted.

---

### Click checklist

| t | action |
|---|---|
| 0:30 | `eval/report.md`, confusion table |
| 0:50 | terminal: Morris Bank `PE` -> Pemko |
| 1:00 | **Upload PDF** -> `pe-finish.pdf`, hover the Finish cell of CLOSER |
| 1:15 | Valor: set 1, `j` x2, filter `12`, **Diagnostics** |
| 1:55 | Roselle: set 1.2, **Needs review** |
| 2:35 | Lyons: **Not used**, set 5, **All**, set 6 |
| 3:15 | hover Catalog/MFR, edit Description, **Save**, **Export as gold** |
| 3:45 | report: 10 worst errors |
