# PLAN.md — Hardware Set Extractor (Fresco take-home)

This is the build plan for this repository. Read it fully before writing code. Work phase by phase, and stop at each **checkpoint** to report results before continuing.

---

## 0. Context

### The task
Extract every **hardware set** from Division 08 (Openings) specbook PDFs. For each set, output:

- `set_number`: e.g. `"1"`, `"3A"`, `"15"`, `"EX-3.0"`
- `description`: optional heading, e.g. `"ENTRANCE DOORS"`
- `location`: page(s) plus a bounding box per page, and a line range
- `components[]`: each with `qty`, `description`, `catalog_number`, `mfr`, `finish`, `notes`

Sets appear in two forms:
- **List format:** a header line followed by component lines.
- **Table format:** a schedule in which rows are grouped under set headers.

A typical project has 5–30 sets with 3–15 components each.

### Grading criteria (from the brief)
- Find **all** sets.
- Get 90%+ of sets and components right.
- Map fields to the right columns, **especially manufacturer vs. finish**.
- Give meaningful location data.
- Work across different specbook formats.

**Bonus:** a feedback UI for corrections, confidence scores, and resolution of shorthand codes from a lookup table on the same page.

### Caveats the system must handle
1. **Manufacturer vs. finish codes are ambiguous.** "PE" can mean Pemko or Painted Enamel; "NO" can mean Norton or the word "No." Resolve them from the column's context, never from the value alone.
2. **Set boundaries can be subtle.** Sometimes there's only a blank row or a change in set number.
3. **"NOT USED" / "N/A" sets must still be extracted.**
4. **Sets can span page breaks.**
5. **Column layouts differ between specbooks.**
6. **Missing quantities become `null`, never a guess.**

### What we're competing against
A previous candidate's repo (ziw224/door-hardware-set-extractor) used:
- pypdf text with no bounding boxes (`bbox=None`);
- four hard-coded header regexes, one per format;
- manufacturer and finish assigned **by position within each line**;
- no table handling;
- gold labels drafted from its own output, on a single specbook;
- a JSON editor UI with no PDF view.

We must clearly beat it on every one of these.

### Core thesis
> Deterministic, grounded, document-level inference. Every extracted value points to real words on the page with their coordinates. Structural decisions (where sets start, which column is which) are made across the whole document, not per value. LLMs are an optional layer, added only where the evaluation shows the rules fail.

---

## 1. Non-negotiable rules for this build

1. **Python 3.12, managed with `uv`.** No other languages.
2. **Every extracted value is grounded.** It must carry the `token_ids` it came from. No value may contain text that doesn't appear in the source tokens, apart from normalization (trimming, case) and lookup-code expansions, which must cite their legend tokens.
3. **No per-specbook special cases.** No `if filename == ...` or format-specific branches keyed on a book. Generalize through scoring and inference. If a rule only helps one book, flag it in the checkpoint report.
4. **Hold-out discipline.** Two specbooks are held out (chosen in Phase 0). Never open, render, or debug on them while developing. They're only run in the final evaluation.
5. **Never guess quantities.** Missing → `null`.
6. **Gold labels must be independent of the extractor.** Draft them by viewing rendered page images, never by running or reading the extractor's output.
7. **Keep pure stages pure.** Layout, segmentation, column inference and validation are pure functions of tokens. I/O lives only in `ingest/`, `cli.py`, `api/`, and `llm/`.
8. **Ask before adding a dependency** that isn't listed in §3.
9. **Small, reviewable commits**, with a conventional message per logical change.
10. **No secrets in the repo.** The LLM layer is optional and reads `ANTHROPIC_API_KEY` from the environment.

---

## 2. Repository layout

```
hwsets/
  pyproject.toml
  README.md
  PLAN.md
  Makefile
  Dockerfile
  docker-compose.yml
  data/
    raw/                 # specbook PDFs (gitignored; user downloads from Drive)
    tokens/              # cached ingest output, *.tokens.json (gitignored)
    pages/               # rendered PNGs for UI and gold drafting (gitignored)
    gold/                # hand-verified gold labels, *.gold.json (committed)
    survey.md            # Phase 0 output (committed)
    splits.json          # dev / gold / holdout assignment (committed)
  src/hwsets/
    __init__.py
    models.py            # pydantic schema (single source of truth)
    ingest/
      pdf.py             # PyMuPDF → tokens
      ocr.py             # OCR fallback for pages with no text layer
      render.py          # page → PNG
    layout/
      lines.py           # tokens → lines
      columns.py         # x-position clustering → column bands
      chrome.py          # running header/footer removal
      stream.py          # continuous multi-page line stream
    segment/
      headers.py         # header-candidate scoring + per-doc pattern induction
      sets.py            # line stream → set spans (incl. NOT USED)
    columns/
      lexicon.py         # mfr + finish lexicons, collision set
      features.py        # per-column feature distributions
      assign.py          # role assignment (Hungarian) + margins
      template.py        # positional template inference for list format
    components/
      parse.py           # rows → Component (qty, desc/catalog split, notes)
      lookup.py          # same-page code legend resolution
    validate.py          # invariants + per-field confidence
    pipeline.py          # orchestrates pure stages
    llm/                 # Phase 5 only
      interface.py       # LLM protocol: live + replay
      tasks.py
    eval/
      metrics.py
      report.py
    api/
      server.py          # FastAPI
      static/            # review UI (vanilla JS + CSS, no build step)
    cli.py               # `hwsets extract|eval|serve|ingest`
  tests/
    unit/
    property/            # Hypothesis
    fixtures/            # small synthetic token files
    golden/              # end-to-end snapshot tests on gold books
```

---

## 3. Dependencies

Runtime:
- `pymupdf` (fitz): words, bounding boxes, font flags, rendering.
- `pydantic>=2`
- `numpy`, `scipy`: `scipy.optimize.linear_sum_assignment` for role assignment.
- `typer`: CLI.
- `fastapi`, `uvicorn`
- `rapidfuzz`: fuzzy matching of codes and header keywords.
- OCR: `ocrmypdf` + Tesseract, as a system dependency, invoked only for pages with no text layer. Optional at runtime; skip gracefully if not installed.

Dev:
- `pytest`, `hypothesis`, `ruff`, `mypy` (strict on `src/`).

Phase 5 only: `anthropic`.

---

## 4. Data model (`models.py`)

This is the single source of truth. Export its JSON Schema to `schema.json` with `make schema`.

```python
TokenId = str  # f"p{page}_w{index}"

class Token(BaseModel):
    id: TokenId
    page: int                 # 1-based
    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 in PDF points
    font_size: float
    bold: bool
    block: int
    line: int                 # PyMuPDF block/line indices (hints only)

class Line(BaseModel):
    id: str
    page: int
    token_ids: list[TokenId]
    bbox: tuple[float, float, float, float]
    text: str                 # tokens joined with single spaces

class Field(BaseModel, Generic[T]):
    value: T | None
    token_ids: list[TokenId] = []
    confidence: float         # 0..1
    source: Literal["rule", "lookup", "llm", "human"] = "rule"

class Component(BaseModel):
    qty: Field[int | str]     # int when numeric; keep units like "PR" in qty_unit
    qty_unit: str | None      # "EA", "PR", "SET", or None
    description: Field[str]
    catalog_number: Field[str]
    mfr: Field[str]           # raw code as printed, e.g. "PE"
    mfr_resolved: str | None  # e.g. "Pemko", if a legend or lexicon resolves it
    finish: Field[str]        # raw code, e.g. "626"
    notes: Field[str]
    resolved_from_code: str | None  # lookup-code bonus: "A" → full item

class PageRegion(BaseModel):
    page: int
    bbox: tuple[float, float, float, float]

class Location(BaseModel):
    regions: list[PageRegion]   # one per page spanned
    line_range: tuple[str, str] # first and last Line.id

class HardwareSet(BaseModel):
    set_number: Field[str]
    description: Field[str]
    status: Literal["active", "not_used"]
    status_text: str | None     # e.g. "NOT USED"
    location: Location
    components: list[Component]
    confidence: float           # set-level aggregate

class DocumentResult(BaseModel):
    source_pdf: str
    hardware_pages: list[int]
    column_roles: dict[str, str]  # diagnostic: column band → role, with margins
    sets: list[HardwareSet]
    warnings: list[str]
```

Also provide a **flat export** (`--flat`) matching the brief's plain shape (`set_number`, `description`, `location`, `components[]` with plain values), for graders who want simple JSON.

---

## 5. Phases

### Phase 0: Survey and splits

**Goal:** know the real distribution of formats before writing any parser.

Steps:
1. `hwsets ingest data/raw/` writes tokens and renders PNGs for every PDF.
2. Find candidate hardware pages per PDF with a cheap score: keywords (`HARDWARE SET`, `SET NO`, `HEADING`, `HARDWARE GROUP`, `HW-`) plus the density of tokens that appear in the manufacturer and finish lexicons (see Phase 2 for the lexicons, and seed them now).
3. **View 2–3 rendered hardware pages per specbook** and record in `data/survey.md`, one row per book:
   - list or table format;
   - the header pattern as printed;
   - column order;
   - whether it has a header row;
   - whether it has a manufacturer legend;
   - whether it has lookup codes;
   - whether it's scanned;
   - multi-page sets seen;
   - NOT USED style;
   - quirks.
4. Group the books into format clusters. Pick **6–8 gold books** that cover every cluster and **2 held-out books** from different clusters. Write `data/splits.json`.

**Checkpoint 0:** report the survey table, the format clusters, the proposed splits, and any book that looks unusual (scanned, rotated, two-column pages). Wait for approval.

### Phase 1: Ingest

`ingest/pdf.py`:
- `page.get_text("words")` for words and bounding boxes. Use `page.get_text("dict")` for font size and bold (`flags & 16`, or "Bold" in the font name). Join them on bounding-box overlap.
- Stable token IDs `p{page}_w{i}`, in reading order.
- If a page has fewer than 5 words but has images → `ocr.py`. Run `ocrmypdf` on that page and re-extract; mark its tokens `ocr=True`.
- Handle page rotation. Normalize bounding boxes to the page as displayed.

`ingest/render.py`: 150 DPI PNG per page. Store the scale factor so the UI can map PDF points to pixels.

Cache keyed by PDF sha256.

Tests: token IDs are stable across runs; every bbox is inside the page rect; the PNG scale round-trips.

### Phase 2: Layout

**`lines.py`**: group tokens into lines with a y-overlap tolerance (half the median token height). Sort by x within each line. Handle wrapped cells (see `columns.py`).

**`chrome.py`**: running headers and footers. Normalize the text of lines in the top and bottom 8% of each page (digits → `#`). Any normalized line appearing on 50% or more of the hardware pages is chrome; drop it. Also drop repeated table header rows ("QTY DESCRIPTION CATALOG…") after their first appearance, but **keep them as column-role evidence**.

**`columns.py`**: collect the token left edges (x0) across all lines in the hardware section. Run a 1-D kernel density estimate or histogram, and take peaks with enough support (they must appear in 15% or more of component-like lines) as column anchors. Assign each token to the nearest band. Lines whose tokens fit the bands are "tabular"; if most lines don't fit, the document is "list" format.

Wrapped cells: a line that has tokens **only** in description or notes bands and no quantity is a continuation of the row above. Merge it.

**`stream.py`**: join all hardware pages into one ordered line stream. **A page break is never a segment boundary.**

### Phase 3: Segmentation (set boundaries, NOT USED)

**`headers.py`**: score every line as a possible header.

| Feature | Signal |
|---|---|
| Contains a set-number token | Regex family: `^\d{1,3}[A-Z]?$`, `^[A-Z]{1,4}-?\d+(\.\d+)?[A-Z]?$`, zero-padded `^0\d{1,3}$` |
| Keyword nearby | `SET`, `HEADING`, `GROUP`, `HW`, `HARDWARE`, `NO.`, `#` (fuzzy) |
| Typography | bold, font size above the body median, all caps |
| Geometry | larger gap above than the median line spacing; left-aligned at a recurring x |
| Not a component | no finish or manufacturer lexicon hits; no quantity-plus-unit pattern at the start |

**Per-document pattern induction:**
1. Take the high-scoring candidates and turn each into a *shape signature*: keyword(s) + number shape + typography + x-anchor.
2. Choose the signature with the most support (at least 3 hits, or every hit if the book has fewer than 3 sets).
3. Re-scan the stream and mark every line matching that signature as a header.

This replaces hand-written regexes per format.

**Table format with a set-number column:** if column inference (Phase 4) finds a set-number column, a boundary is wherever that value changes. A blank row is only *supporting* evidence.

**`sets.py`**: split the stream at the headers.
- **Description:** the remainder of the header line after the set number, or the next line if it is all caps with no lexicon hits.
- **NOT USED:** if the header line, or the first non-empty line after it, matches `NOT USED|N/?A|OMITTED|DELETED|VOID` as a standalone phrase (not inside another word), set `status="not_used"`, `components=[]`, and keep `status_text`.
- **Location:** for each page touched, the union bbox of the set's lines. `line_range` covers its first and last line.
- **Set numbers:** normalize `001` → `"1"` for display, but keep the raw text in `token_ids`. Record duplicates as a warning, never merge them silently.

**Set-level non-component lines:** recognize lines like `DOORS:`, `OPERATION:`, `NOTES:`, `Description:` and the door-number lists. Attach them to the set's notes, not to components.

### Phase 4: Column roles (manufacturer vs. finish)

This is the headline feature. Make it excellent and well explained.

**`lexicon.py`**:
- `MFR_CODES`: code → canonical name. Seed it with common BHMA and industry abbreviations: IVE/Ives, SCH/Schlage, LCN, VON/Von Duprin, PEM/PE/Pemko, GLY/Glynn-Johnson, NGP/National Guard, ROC/Rockwood, HAG/Hager, MK/McKinney, SAR/Sargent, COR/Corbin Russwin, YAL/Yale, ZER/Zero, RIX/Rixson, DOR/Dorma, NOR/NO/Norton, BES/Best, STA/Stanley, ABH, TRI/Trimco, BOM/Bommer, HES/Hes, SEC/Securitron, and so on.
- `FINISH_CODES`: BHMA numbers (600–700 range: 605, 606, 612, 613, 619, 625, 626, 628, 630, 652, 689, 690, 693, 695…) and US equivalents (US3, US4, US10, US10B, US15, US26, US26D, US28, US32, US32D…), plus AL, BLK, BSP, DKB, GRY, PC, SP and similar.
- `COLLISIONS`: codes that appear in both lists or are common words (PE, NO, BL, AL, SP, ST, …). These score **zero** for both roles.
- During Phase 0, extend the lexicons from what's actually seen. Write the evidence (book, page) for every addition into a comment.

**`features.py`**: for each column band (table format) or line position from the right (list format: last, second-to-last…), compute a feature vector over **all** rows in the document:
- fraction of values that are manufacturer codes;
- fraction that are finish codes;
- fraction matching quantity patterns;
- fraction that look like catalog numbers (alphanumerics with digits and dashes, length 3 or more);
- mean word count and fraction of dictionary words (description);
- fraction that are empty.

**`assign.py`**:
1. Build a score matrix of columns × roles {qty, description, catalog, mfr, finish, notes, set_no, ignore}.
2. Solve it with `linear_sum_assignment`, allowing `ignore` and `notes` to be used more than once.
3. Record the **margin** for each column: the best role's score minus the second best.
4. Apply priors that adjust the scores:
   - A header row ("MFR", "MFG", "FIN", "FINISH", "QTY", "CAT", "PRODUCT") adds a strong prior.
   - A manufacturer legend in the book (lines like `PE – Pemko`, `IVE – Ives`) overrides lexicon entries and promotes those codes to strong manufacturer evidence.
5. **Resolve ambiguous values by their column.** A value takes its column's role, so "PE" in the manufacturer column becomes Pemko and "PE" in the finish column becomes Painted Enamel. Put the role's resolution into `mfr_resolved` when it's known.

**`template.py`** (list format with no aligned columns):
1. Take the lines with confident lexicon hits at the end.
2. Infer the dominant positional template, e.g. `[qty] desc… catalog… mfr finish` or `[qty] desc… catalog… finish mfr`.
3. Apply that one template to every line. Lines that don't fit get lower confidence and a warning.

**Tests:**
- Property test (Hypothesis): generate synthetic tables with a random column order, random rows drawn from the lexicons, and injected collision codes (PE, NO). Assert the role assignment is invariant under column permutation, and that a collision code is resolved to its column's role every time.
- Unit test: a document whose manufacturer column contains "PE" alongside SCH/LCN/IVE → Pemko; a document whose finish column contains "PE" alongside 626/630 → finish.

### Phase 5a: Components

**`parse.py`**:
- **Quantity:** only from the quantity column or leading position. Accept `\d+`, `\d+ ?(EA|PR|SET|LOT)`, or a unit alone with no number → `qty=None, qty_unit=unit`. Otherwise `null`. **Never default to 1.**
- **Description vs. catalog split:** inside the description and catalog span, the catalog number starts at the first token that looks like a model (letter+digit mix, dashes, slashes, decimal sizes like `4.5 X 4.5` belong to the catalog). Everything before that is the description. Use the column band when the table gives one.
- **Notes:** a trailing note column, text in parentheses, `NOTE:` markers, `@`-prefixed continuation lines, or footnote markers (`*`, `(1)`).
- **Continuation rows:** merge them (see `columns.py`).

**`lookup.py`** (bonus): find legend blocks on the same page or within the same set, such as `A  –  Hinges: 5BB1 4.5 x 4.5 …` or tables keyed by single letters or numbers. When a component's catalog or description field is just a key ("A"), fill `resolved_from_code` and cite the legend tokens.

### Phase 5b: Validation and confidence (`validate.py`)

Invariants. Violations produce warnings and lower confidence; they never crash.
- Every `Field` with a value has at least one token, and its tokens belong to the set's lines.
- `qty` is an int or `null`.
- `mfr` values agree with the role of their column.
- A set has at least one component, unless it's `not_used`.
- Set numbers are unique within a document (duplicates are flagged).

Field confidence is a weighted combination of:
- whether the value matches the lexicon;
- the column's role margin;
- how well the line fits the template;
- whether the validator passed.

Set confidence is the mean of its component confidences, scaled by how strongly its header matched. Calibrate the weights against the gold set in Phase 6 and report a reliability table (confidence buckets vs. actual accuracy).

### Phase 6: Gold labels and evaluation

**Gold drafting (independent of the extractor):**
- For each gold book, view the rendered hardware pages and write `data/gold/<book>.gold.json` in the flat schema. Location is the page plus a rough bbox (in PDF points) for each set.
- **Never run the extractor on a book before its gold file is finished.**
- Mark uncertain cells with `"_uncertain": true` so the user can verify them in the UI.

**Checkpoint 6a:** report the gold files and the list of uncertain cells. The user verifies them in the UI before metrics are trusted.

**`eval/metrics.py`**:
- **Set matching:** match predicted sets to gold sets by normalized set number. If set numbers are missing, fall back to IoU of the location regions.
- **Set metrics:** recall and precision. Also check `not_used` status separately.
- **Component matching:** within a matched set, use the Hungarian algorithm on description and catalog similarity.
- **Field accuracy:** for each field, exact match after normalization (case, whitespace, `US26D`≡`626` equivalence table), plus a fuzzy score for description.
- **Manufacturer vs. finish confusion matrix:** predicted role vs. gold role for every code token.
- **Location:** mean IoU per set and page.
- **`set_fully_correct`:** the percentage of sets where every component is exactly right. This is the brief's "~90%" figure.

**`eval/report.py`**: writes `eval/report.md` and `eval/report.json` with:
- a per-book table;
- totals;
- the confusion matrix;
- the reliability table;
- the 10 worst errors, each with page, line and a link into the UI.

**Coverage run over all books:** sets found per book, warnings, crashes, books where 0 sets were found.

**Held-out run:** only at the end, reported separately.

**Checkpoint 6b:** report the full eval and the error analysis, grouped into categories (segmentation, column roles, description/catalog split, quantity, location). Propose fixes, ordered by how many errors each would remove. **Do not overfit.** Every fix must be a general rule.

### Phase 7: Review UI (`api/`)

FastAPI endpoints:
- `GET /docs/list`
- `GET /docs/{id}/result`
- `GET /docs/{id}/page/{n}.png`
- `GET /docs/{id}/tokens?page=n`
- `PUT /docs/{id}/sets/{set_idx}` saves a correction
- `POST /docs/{id}/export-gold`

Frontend: `static/index.html` with vanilla JS. No build step.
- **Left panel:** document picker, then a list of sets with confidence badges. NOT USED sets show as greyed.
- **Centre panel:** the page image with absolutely positioned overlay rectangles. Set regions are lightly tinted. Clicking a set scrolls to its page or pages.
- **Right panel:** the selected set's components as an editable table, with each cell colored by confidence (green above 0.85, amber 0.6–0.85, red below 0.6).
- **Hovering or focusing a cell** highlights its source tokens on the page. This is the key demo moment.
- **Editing** marks the field as `source="human"`. "Save" writes `data/corrections/<doc>.json`. "Export as gold" converts the corrected result into the gold format.
- **Keyboard:** `j`/`k` move between sets; `n` jumps to the next low-confidence field.

Show the column-role diagnostics for each document: "Column at x≈412 → MFR (margin 0.71)".

### Phase 8 (optional): LLM layer

Only start this if Checkpoint 6b shows a cluster of errors that rules can't reasonably fix.

- `llm/interface.py`: a `Protocol` with a `LiveLLM` implementation (Anthropic API) and a `ReplayLLM` implementation (reads recorded responses from `data/llm_cache/` keyed by a prompt hash). The default is replay, so reviewers can run everything without an API key.
- Tasks, each given the page image plus the relevant lines with their token IDs:
  - `classify_header_candidates`: when no signature reaches the support threshold.
  - `split_desc_catalog`: when the split heuristic's confidence is below a threshold.
  - `resolve_low_margin_column`: when a column's role margin is below a threshold.
- **The LLM answers only with token IDs and enum roles,** as JSON validated by pydantic. On a validation failure, send the error back once for a retry; if it fails again, keep the rule-based value.
- Every LLM-sourced field has `source="llm"`.
- Report before/after metrics per book. If the overall gain is under 1 point, disable it by default and explain why in the README.

### Phase 9: Ship

**Makefile targets:**
- `setup`
- `ingest`
- `extract` (one or all PDFs)
- `eval`
- `serve`
- `test`
- `lint`
- `schema`
- `demo` (preloads 3 books into the UI)

**Docker:**
- A single image with Tesseract installed.
- `docker compose up` serves the UI on :8000, preloaded with the processed demo books.

**Deploy:** to Fly.io or Render, with the demo books' results baked in. Uploading new PDFs works when the server has CPU; no API key is needed.

**README sections:**
1. One-paragraph summary plus a screenshot.
2. Quickstart: three commands, relative paths only.
3. Architecture diagram and stage descriptions.
4. **How each caveat is handled.** One short section per caveat, with a pointer to the code that handles it.
5. Eval results table, confusion matrix, held-out results, known failures (with honest examples).
6. Design decisions and tradeoffs:
   - deterministic first;
   - why there are no per-format parsers;
   - the LLM layer's measured effect;
   - what we'd do with more time.
7. How AI was used in development, and where it wasn't trusted (gold labels independent of the extractor, every rule tested).
8. Output schema, and the flat export.

**Demo video script (~4 min)** goes in `docs/demo-script.md`:
1. The problem and the thesis (30s).
2. The confusion matrix, then the same "PE" resolving differently in two books (45s).
3. Three books in the UI: a list format, a table format, and a multi-page or NOT USED set (2 min).
4. Hover a field to see its tokens light up, then correct one field (30s).
5. Tradeoffs and next steps (30s).

---

## 6. Testing strategy (summary)

- **Unit tests** for every pure stage, on small fixtures built from tokens.
- **Property tests (Hypothesis):**
  - Column-permutation invariance for role assignment.
  - Collision codes take their column's role.
  - A page break inserted inside a set never splits it.
  - A blank row inside a set doesn't split it unless a header follows.
  - NOT USED sets always produce zero components.
  - No component is lost: rows in = components out (excluding chrome).
  - Missing quantity → `null`.
- **Golden tests:** run the pipeline on the gold books and snapshot the metrics. CI fails if `set_recall` or `set_fully_correct` drops by more than 1 point.
- `ruff`, `mypy --strict` on `src/`.

## 7. Priority if time runs short

1. Set recall plus location bounding boxes.
2. Column-role inference (manufacturer vs. finish).
3. Honest eval and the README.
4. The UI's token highlighting.
5. The UI's corrections.
6. Confidence calibration.
7. Lookup codes.
8. The LLM layer.

## 8. Checkpoint protocol

At each checkpoint, report:
- what was built;
- test status;
- metrics, if any;
- surprises;
- any rule that felt book-specific;
- the next step you propose.

Then wait for approval. Never mark a phase done with failing tests.
