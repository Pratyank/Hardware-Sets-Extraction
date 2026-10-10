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
