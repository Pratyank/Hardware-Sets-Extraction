# Decision log

Decisions made while building, newest last. Each entry says what was decided, why, and what it affects.
Checkpoint reports are kept here too.

## 2026-10-10: Phase 0 / 1

- **Checkpoint 0 was approved by the user as proposed.** This covers the splits in `data/splits.json`, the gold
  page windows for hfh (20–40), bridgeport (3–18) and sjc (711–724), the strikethrough fix, gitignoring the
  ruflo tooling, and OCR in Docker. The user then went AFK and asked me to continue autonomously and log
  decisions here.
- **The repo root is the plan's `hwsets/` directory.** Package code is in `src/hwsets/` (src layout, hatchling,
  uv).
- **The token cache is sharded per page** (`data/tokens/<sha16>/p0001.tokens.json` plus `manifest.json`, and an
  `index.json` mapping doc_id to sha). Project manuals run to 3,930 pages, and the UI's
  `tokens?page=n` and the pipeline only need a few pages each. Rows are compact arrays, and token ids are
  implied (`p{page}_w{i}`), so they are stable.
- **Rendering is on demand, not for every page.** `ingest` renders only hardware-candidate pages, and
  `hwsets render` or the UI render the rest lazily. Rendering 17.6k pages at 150 DPI would cost GBs for
  little use.
- **Strikethrough** (`Token.strike`): MuPDF reports strikeout per span (`char_flags & 1` with
  `TEXT_COLLECT_STYLES`). Struck tokens are kept in the cache as evidence, and later stages exclude them from
  values. This is one rule for every book (sjc, hfh and valor all have redlines). `INGEST_VERSION` was
  bumped to 2.
- **OCR:** the user installed `tesseract-ocr` and `ocrmypdf`. Pages with fewer than 5 words that contain images
  are OCR'd and marked `ocr=True`. These are bridgeport rev-0's cut sheets, the oswego geotech appendix and
  covers. None of them are hardware pages, so OCR mainly tests page detection against noisy OCR'd catalog
  pages.
- **Schema additions beyond §4 of the plan:**
  - `Token.ocr` and `Token.strike`
  - `HardwareSet.notes`, for set-level lines such as `Doors:`, `Operation:` and `Notes:` (the plan says these go
    into "the set's notes")
  - `FlatDocument.gold_pages`
  - `PageInfo` / `TokenDocument`
- **Gold files cover page windows for the three large books.** Eval scores only gold sets whose header page
  lies in `gold_pages`, plus predicted sets located in that window.
- **Gold labelling runs in parallel:** 4 agents with 2 books each. They work from page images, are allowed the
  raw `hwsets tokens` dump for exact spellings, and are forbidden from extractor code or output. The
  conventions are in `docs/gold-guidelines.md`.

## 2026-10-10: Core pipeline (Phases 2–5b), built on dev books only

- **Header-driven section detection replaces lexicon page scoring.** The survey showed the lexicon score misses
  about 30% of set pages, for example jc-ryan, where headers read "Set:" and no finish codes are printed.
  Hardware pages are now the pages holding headers of the induced signature, plus continuation pages, ending
  at `END OF SECTION`. Lexicon scoring is kept only as a diagnostic (`hwsets pages`).
- **Header induction:** one permissive grammar parses every header candidate, and the signature with the most
  support wins. A candidate followed by component rows gains score; one with nothing after it, and no NOT USED,
  loses score. This keeps spec prose ("Group 1 …", "Set 2 …") out. It fixed usi and forest-park, which have a
  single set each.
- **Chrome zone widened from 8% to 12%.** The shubie running header is 4 lines deep and ends at y=72 of 792.
  Set-header lines are protected from being treated as chrome, so digit normalization cannot collapse them.
- **Column roles are per layout cluster,** not per document. One PDF (morris-bank) binds two schedules with
  different column x positions. Two pages share a layout when at least 80% of their anchors align within 9 pt.
- **Finish legends are role evidence too.** `10BE`, `EB` and `313` (morris-bank) are not in the BHMA lexicon,
  but the book's own finish legend defines them. Quantity evidence is discounted when the column's median
  number is above 100, because BHMA finish numbers look like counts.
- **Multi-set headers** ("#B1 and #B2"): one set per id. They share the same lines and components, and only
  the first id owns the header tokens.
- **Rows printed as `1 NOTE …`** go to the set's notes, not to components.
- **NOT USED** is recognized only on the header line or on the first line after it, as the plan specifies.
  "N/A" elsewhere is ordinary text; morris-bank wraps "x N/A" inside door descriptions.
- **Parenthetical text stays in its cell.** It is not moved to notes, because whether a parenthetical is a note
  or part of a catalog is subjective. Notes come from note columns, `Note:` / `Properties:` sub-lines and
  set-level lines.
- **Set numbers are normalized for display** ("001" → "1"), as the plan says. The raw tokens stay in
  `token_ids`.
- **Dev results** (the 10 dev books and 21 negatives): all 21 negatives give 0 sets. Set counts match the
  survey on 9 of 10 dev books. starhardware gives 70 against about 74, missing its multi-set and
  sentence-form headers; its ruled-grid layout is the weakest case.
- **Incident:** I ran `hwsets extract` once on lyons, a gold book, while its gold file was still being drafted.
  I saw only the summary counts (29 sets, 156 components) and deleted the result immediately. The gold agent
  works only from page images and never reads extractor output, so its labels are unaffected. As a fix, the
  CLI now refuses gold books until their gold file has `"_final": true`, and refuses held-out books without
  `--allow-holdout`.

## 2026-10-10: Gold labels (Checkpoint 6a)

- **Gold labels:** four labelling agents produced gold for 8 books, 279 sets and 2,184 components in total. Each
  agent transcribed from page images and then cross-checked its JSON against the raw tokens with a throwaway
  script; no extractor code was involved. I spot-checked valor p10 (a redline) and roselle p16 (a ruled
  grid) against the rendered images, and both match exactly. All 8 files are marked `"_final": true`.
- **Uncertain cells** (`_uncertain` in the files), by book:
  - **gerrard (4):** note lines under rows, such as "Active Leaf" and "Shared with D147A".
  - **jc-ryan (1):** a two-line catalog cell.
  - **lyons (2):** parentheticals.
  - **hfh (4):** the struck alternates `2 (1)` and `3 (2)`; a trailing lone "-"; a row whose only text is
    "ALL HARDWARE BY DOOR MANUFACTURER".
  - **bridgeport (4):** instruction lines inside the catalog column.
  - **sjc:** nine "Moved to …" stubs are marked not_used and uncertain. The redline duplicates 14B and 10C are
    resolved to the live set. The parentheticals in 07A and 07B are also marked.
- **Convention fix:** the agents disagreed about parentheticals printed inside a cell. Two moved them to
  notes; the others kept them in the cell. I standardized on keeping them in the cell, because that is
  objective and grounded in the cell boundary. Seven gold cells were fixed mechanically and tagged
  `_convention_fix`, and the guideline was updated. This is a labelling-convention decision, not one driven by
  the extractor.

## 2026-10-10: Evaluation and error analysis (Checkpoint 6b)

The first `hwsets eval` was blind: the extractor had never been run on a gold book, apart from the logged
lyons incident, and no rule had been tuned on gold.

| metric | blind baseline | now |
|---|---|---|
| set recall / precision | 88.2% / 99.2% | **100% / 99.3%** |
| component F1 | 97.4% | 98.6% |
| description exact | 91.4% | 98.6% |
| catalog exact | 94.0% | ≈97.5% |
| manufacturer exact | 97.0% | ≈97.3% (jc-ryan 59.6% is the outlier) |
| finish exact | 99.9% | 99.9% |
| qty exact | 99.7% | 99.8% |
| mfr↔finish confusions | **0** | **0** |
| set_fully_correct | 31.2% | **75.6%** |

**Error categories found, and the general fix for each.** Each fix was checked against the dev books and the
negatives (still 0 sets) to make sure nothing regressed.

1. **Segmentation.** Roselle had zero recall because its set ids sit in a table SET column with no keyword.
   Fix: bare-id header induction. Ids must be unique and ascending at one left x, and the lines must carry
   manufacturer or finish codes. The SET column gets the `set_no` role, and its stacked text becomes the set
   description.
2. **Text joining.** Same-line tokens were glued together ("W/KEYFOB"). Now only a hyphen broken across a line
   wrap is joined without a space.
3. **Description/catalog split.** The split was applied even in books that have no catalog column (valor). It
   now runs only when the description column demonstrably also holds model numbers.
4. **Column roles.** A column-header row repeated at the top of every page was being removed as chrome before
   it could serve as evidence. Header rows are now read before chrome removal, as the plan says.
   Manufacturer–catalog merged cells ("VON DUPRIN - 6200 SERIES") are now split based on a document-level
   majority.
5. **Row assembly.**
   - Ruled tables: drawn horizontal rules are now captured at ingest (INGEST_VERSION 3) and act as exact row
     boundaries.
   - Vertically centred cells (jc-ryan): a fragment much closer to the next row whose matching cells are
     empty attaches forward.
   - A line that fills three value columns starts a new row.
   - Door-size lines ("965 x 2134 …") are set-level.
   - When a quantity column exists, quantities come only from it.
6. **Notes.** A note aligned with the description column is set-level, matching the gold convention; only an
   indented note belongs to its item. Revision tags (`[BULLETIN …]`) go to notes. Prose blocks after
   "Operational Description:" and similar intros are set-level until a quantity-led row starts.
7. **Redlines.** A strike drawn as a vector line through a token's middle band now marks the token struck, in
   addition to MuPDF's strikeout flag.
8. **Test-suite bugs.** The property and unit suite (245 tests) found 8 bugs, each pinned by a strict xfail
   test and then fixed; the tests now pass as regression tests. They covered collision codes counted as
   words, 4-digit model numbers read as counts, sparse first pages, a sparse quantity column, "DOOR …" rows
   taken as set-level lines, first rows taken as titles, and hyphen joining (2 bugs).

**Still open**, in order of how many errors each would remove:
- jc-ryan manufacturer column (59.6%).
- hfh (36% fully correct): struck rows that carry no strike flag and no drawing, and leftover revision tags.
- Spurious components in lyons (90% precision).
- Roselle notes column.
- sjc location IoU (0.78).

## 2026-10-10: After Checkpoint 6b

- **More general fixes, each verified on the dev books and the negatives:**
  - A document-wide item vocabulary: a quantity-less line whose description is printed elsewhere as its own item
    starts a new row. This applies only on pages without row rules.
  - Row-ruled page detection: at least 6 wide horizontal rules.
  - Revision tags are kept only on revised rows, meaning rows whose own text is bold.
  - Ragged or centred cells keep their column role: an adjacent look-alike column gets the same role (jc-ryan's
    manufacturer column).
  - The set preamble before the item table is set-level (lyons door grids with room names).
  - Gold set_fully_correct is now **87.1%**: lyons 100%, sjc 96%, valor 95%, gerrard 91%, bridgeport 87%,
    roselle 76%, jc-ryan 74%, hfh 72%.
- **Positional template** (`columns/template.py`) is wired in, but only for layouts with at most 3 column
  anchors that have neither a manufacturer nor a finish column, i.e. genuinely unaligned lists. On
  starhardware's table it was splitting continuation lines, so tables keep the column model.
- **Confidence calibration:** a per-field isotonic map (pool-adjacent-violators, blocks of at least 20) fitted
  on the gold books (`hwsets calibrate` → `data/calibration.json`), with raw scores reduced per wrapped line.
  The fit is in-sample on gold. The held-out reliability table is the out-of-sample check.
- **Lookup codes:** blocks of at least 2 key legend lines on the set's own pages resolve components whose
  description or catalog is only a key. The legend tokens are cited in the new
  `Component.resolved_from_code_tokens` field (schema updated). No surveyed book uses this format; it is
  covered by synthetic tests.
- **Golden gate** (`tests/golden`): fails when set recall or set_fully_correct drops by more than 1 point
  against `tests/golden/snapshot.json`. Run `make snapshot` to refresh it after an intended change.
- **LLM layer is not built.** After the error analysis no cluster of rule-resistant errors is left. The
  remaining errors are individual ambiguities (a struck-quantity glyph, unlabelled wraps). This is explained in
  the README.
- **Process:** two commits went in with a hidden failure because exit codes were piped through `tail`. Both
  were fixed immediately. All commits now go through `make check` (lint, types and the full test suite).

## 2026-10-10: Held-out evaluation

- **Held-out gold** for oswego (pp 418–445, 39 sets, 376 components) and livelle-vol1 (pp 643–662, 68 sets, 445
  components) was drafted from page images by a separate agent (gold-holdout) after development was frozen.
  I spot-checked oswego p430 and livelle p655 against the images (exact match, including wrapped catalog cells
  and NOTE rows kept out of components), then marked both files `_final`.
- **Result, measured once:** set recall 100%, set precision 100%, component F1 99.9%, set_fully_correct 94.4%
  (oswego 89.7%, livelle 97.1%). There were no manufacturer↔finish confusions. The gold-fitted calibration
  holds: fields scored ≥ 0.9 are 99.8% exact.
- **Not fixed, deliberately:** the two error classes it shows (`NOTE:` rows merging into the component above
  in oswego, and a trailing foot mark dropped in `LP200A 6'` in livelle). Fixing them would tune on the hold-out
  and spoil it as a measurement. Both are listed as known failures in the README.
- `eval/holdout/report.*` is committed next to `eval/report.*`.

## 2026-10-10: Docker verified, CI added

- **Docker verified.** With Docker Desktop running, `make docker` built the image. Under `docker compose up` the
  container reached `healthy`, preloaded the 3 demo books, and served the UI and API on :8000. Uploading an
  image-only PDF (Valor p8 rasterized, no text layer) went through OCR inside the image and returned 5 sets. OCR
  output is noisier than a text layer: `04` came out as `4`, and one set's rows merged. The test upload's files
  were removed afterwards.
- **CI** (`.github/workflows/ci.yml`): `make check` plus a Docker build. Run in a clean clone, this gives
  314 passed and 1 skipped (the golden gate, which needs the uncommitted token cache).
- **Not done, because these need the user's accounts and are outward-facing:**
  - pushing to GitHub (the `origin` remote has no `main` branch yet);
  - deploying to Fly.io or Render. The deploy would also publish the specbook PDFs' extracted contents, which
    is the user's call.
