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
