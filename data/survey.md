# Phase 0 survey: specbook formats

43 PDFs across 21 project folders were ingested (17,637 pages). **20 PDFs contain hardware sets.** Two of them
duplicate another PDF in the same project, which leaves **18 distinct books**. 23 PDFs have no sets; these are
the negatives (see the end of this file).

For every book, pages were checked against text dumps and 2–4 rendered pages were viewed. The rendered pages
are listed in `pages_viewed` in each book's survey JSON.

Abbreviations used in the table:
- **Hdr row**: whether the book has a column header row such as `QTY DESCRIPTION CATALOG NUMBER FINISH MFR`.
- **Legend**: whether the book has a manufacturer abbreviation legend.
- **Scan**: whether the hardware pages are scanned images. No book's hardware pages are scanned.
- **NU**: the NOT USED style.
- In column orders, *icon* is a cut-sheet or electrified glyph.

## Per-book survey

| # | Book (doc id prefix) | Set pages | Fmt | Header as printed | Sets | Column order | Hdr row | Legend | Lookup codes | Scan | Multi-page sets | NU | Quirks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `valor-acres-building-e--087100` | 7–18 | list | `Hardware Group No. 01: (Door U1 – …)` | 37 | qty, unit, desc, finish | `Qty Description` | no | no | no | ~10 | none | No mfr or catalog column. Descriptions wrap and interleave with the finish. Bulletin strikethrough. |
| 2 | `roselle-public-library--087100` | 15–17 | **table** (ruled grid) | `SET` cell: `1.1` + stacked description lines | 33 | set, type(desc), `MFR - catalog` merged, qty, finish, notes | `SET HARDWARE TYPE MANUFACTURER - PRODUCT QTY. FINISH NOTES` | no | no | no | none | none | Mfr and catalog share one cell. Qty `--` means null. Finishes look like `613 (OIL RUBBED BRONZE)`. |
| 3 | `jc-ryan-2--087100` | 24–46 | list | `Set: EX-1.0`, `Set: 2.5` | 37 | qty, desc, catalog, mfr | no | no | no | no | EX-2.0 (p24–25) | 15.0 is "all hardware by door manufacturer" | **No finish column.** Mfrs are full names (Pemko, Sargent…). Hinge rows have no qty. Cells are vertically centred. |
| 4 | `81-85-bridgeport--08-70-00` (+ `-rev-0` duplicate) | 3–49 | list (supplier submittal) | `Heading #17` | 90 | qty, desc, catalog, finish | no | finish legend p2 (full mfr names) | no | p50–238 of rev-0 are scanned cut sheets with no sets | #17, #55, #59, #60 | none | No mfr column. `Item #` door rows and a door-size line precede components. Quantities are project totals. Finish repeats inside the catalog. |
| 5 | `2353-gerrard-street-shelter--hdw-spec` (+ arch-specs duplicate pp164–182) | 19–36 | list | `Set #AL 01`, `Set #01`, `Set #U-02` | 35 | qty, desc, catalog, finish, mfr | no | **yes** p18 (HA, DE, CMND) + finish list | no | no | none | none | `Doors:` lines and an operational description per set. "By Security Provider" rows. Finishes `S`, `No Finish`. |
| 6 | `hfh-dg-hospital--08-71-00-door-hardware` | 20–183 | **table** (Allegion grid) | `Hardware Group No. 001` / `No.263` | 190 | qty, unit, desc, catalog, icon, icon, finish, mfr | yes, repeated every page | no | no | no | many; orphan headers at page bottom | none (gaps) | **Redline V16→V17: struck text is still in the text layer** (`SCH (BES)`, `2 (1) EA`). `[BULLETIN 023]` tags. Heavy cell wraps. |
| 7 | `shubie-center` | 174–175 | list | `Hardware Group No. 01` | 3 | qty, unit, desc, catalog, finish, mfr | no | no | no | no | none | none | Unit `EA-R`. `UNK` mfr. `For use on Door #(s):`. |
| 8 | `forest-park-school` | 262–263 | list | `Set #1` | 1 | qty, desc, catalog, finish, mfr | no | **yes** p261–262 | no | no | Set #1 (p262–263) | none | Decimal quantities (`3.0`). `C-R` mfr. ABH is used but missing from the legend. |
| 9 | `ami-copy` | 397–419 | list | `Hardware Group No. 01`, `X03A` | 44 | qty, unit, desc, catalog, finish, mfr | yes, per set | no | no | no | none | gaps | Wrapped catalog text lands after finish/mfr in token order. Operational paragraphs. |
| 10 | `lyons-township-hs` | 285–294 | list | `Hardware Group No. 05 - Not Used` | 29 | qty, unit, desc, catalog, finish, mfr | yes, per set | no | no | no | none | **4×** `- Not Used` | Door-number grid with room names wrapped over several lines. |
| 11 | `market-view-apartments` | 770–780 | list | `Hardware Group No. 01 - ⚡ A/G EXT PR …` | 24 | qty, unit, desc, catalog, finish, mfr | yes | no | no | no | none | group 03 `HARDWARE BY DOOR MFG.` | `B/O` and `TBD` as mfr. Finish wraps (`630-/316`). `*` catalog prefixes. |
| 12 | `morris-bank` | 233–263 **and** 283–290 | list | `Set #101`, `Set #CR38` | 31 + 18 | qty, desc, catalog, [handing], finish, mfr | yes | **yes** p230/p280 (PE Pemko, SA Sargent…) | option-code legend p231 | no | none | none | **Two copies of 08 71 00 in one PDF**, describing the same doors per opening vs consolidated. Pemko rows end `… PE` with no finish. |
| 13 | `national-doors-and-hardware` | 406–412 | list | `Hardware Group No. 01` | 15 | qty, unit, desc, catalog, finish, mfr | yes, per set | **yes** p406 table | no | no | none | none | Unlabelled door grid. Wraps land after finish/mfr. |
| 14 | `sat-tdp` | 715–836 | list | `Hardware Group No. 101T.1` | 178 | qty, unit, desc, catalog, finish, mfr | yes, per set | no | no | no | none seen | none | Free-form ids (`C200CT`, `XCY714ETW`). Catalogs contain `26D`/`32D`. Div 28 rows use `UNK`/`B/O` with no finish. |
| 15 | `sjc-well-behavioral` | 711–748 | list | `HW 01 Interior Single Bedroom - …` | ~80 live | qty+unit cell, desc, model, finish, manf | `Quantity Description Model Number Finish Manf` | in prose p694–696 | no | no | yes | `HW 15 Not Used`; `HW 13 Moved to …` | **Redline: deleted sets, headers and rows are struck but present.** IDs repeat 2–3×. `As Req` qty. `TBD`/`---`. |
| 16 | `starhardware` | 25–26, 53–113 | **table** (bordered grid per set) | `Hardware Group/Set #A1 – Entry Unit Doors`; `#B1 and #B2`; sentence form | ~74 | qty, unit, desc, catalog (paragraph), finish, mfr | no | **yes** p24, p51 (2-letter: IV, SC, PE…) | no | no | #01 (57–59), #10 (80–81)… | none | Rotated copyright watermark tokens in every row. `__ Ea.` blank qty. Multi-set headers. Prose catalogs with images. |
| 17 | `the-door-company-copy` | 389–421 | list | `HARDWARE GROUP NO. 103` | 44 | qty, unit, desc, catalog, icon, finish, mfr | yes, per set | no | no | no | headers split from body across pages | 001/002 placeholders | `PART N -` auto-numbering junk on every line. `BY DIV 28` rows. |
| 18 | `usi` | 563 | list | `Set: 1.0` | 1 | qty+desc, catalog, finish, mfr | yes | **yes** p563 (GS, PE, RU, RO) | no | no | none | none | Only set is in 08 41 26. 08 71 00 was issued by addendum and is not in the book. |
| 19 | `village-of-oswego` | 418–445 | list | `HARDWARE GROUP NO. 02` | 39 | qty, unit, desc, catalog, finish, mfr | no | no | no | no (scans are geotech appendix) | op-text onto next page | gaps | Same template as Door Company without the PART junk. Unlabelled door line. `B/O`. |
| 20 | `livelle-…-vol1-rev1` | 643–700 | list | `Set: 47.1`, `Set: MISC` | ~161 | qty, desc, catalog, finish, mfr, icon | yes | in prose (`McKinney (MK)`) | no | no | yes | 147–151 vendor placeholders (`00` mfr) | PE/NO/AL collisions in catalogs and notes. `626` used as a catalog number. |

## Format clusters

| Cluster | Signature | Books |
|---|---|---|
| **C1 Group template** | `Hardware Group No. NN` list output from the Openings Studio / Comsense family. qty, unit, desc, catalog, finish, mfr; header row per set; wraps land after finish/mfr | ami, lyons, market-view, national, sat-tdp, shubie, door-company, oswego |
| **C1t Group template, table + redline** | Same headers rendered as a grid with a repeated header row. Struck revision text in the text layer | hfh-hospital |
| **C2 `Set:` template** | `Set: N.N`, `Description:`, `Notes:/Operation:` blocks. qty, desc, catalog, [finish], mfr | jc-ryan (no finish, full mfr names), livelle-vol1, usi |
| **C3 `Set #` template + legends** | `Set #ID`, `Doors:` line, separate mfr, finish and option legends | gerrard, morris-bank, forest-park |
| **C4 Ruled table** | Grid with a header row; merged or prose cells | roselle (merged `MFR - catalog`), starhardware (per-set grids, prose catalogs) |
| **C5 Minimal list** | qty, unit, desc, finish only; no mfr, no catalog | valor-acres |
| **C6 Supplier submittal** | `Heading #N`, `Item #` door rows, project-total quantities, no mfr column | bridgeport |
| **C7 `HW NN` redline** | `HW 01 <title>`, risk line, `Quantity Description Model Number Finish Manf`, heavy strikethrough | sjc |

## Cross-cutting findings that change the build

1. **Strikethrough (redline) text is in the text layer** in sjc (whole deleted sets), hfh (deleted catalog and mfr
   values) and valor (bulletin edits). PyMuPDF exposes it: `get_text("dict", flags=TEXT_COLLECT_STYLES)` sets
   span `char_flags & 1`. On sjc p718 this flags 93 struck spans, and on hfh p26 it flags 6. Proposed fix:
   ingest records `strike: bool` per token, and layout drops struck tokens while keeping them as evidence. This
   is a general rule, not a per-book branch.
2. **Wrapped cells land after the finish/mfr in token order** in C1, C2, C4 and C5. Reading order must come from
   geometry (row bands plus column bands), never from PyMuPDF's word order. This confirms the plan's
   continuation-merge design.
3. **Missing columns are common.** valor has no mfr or catalog, jc-ryan has no finish, and bridgeport has no mfr.
   Role assignment must allow a role to be absent rather than forcing all six.
4. **The page detector misses about 30% of set pages and flags spec prose.** Most misses are continuation pages
   and books without lexicon hits (jc-ryan, gerrard, morris copy 1). The survey's page ranges become
   detector test data. Planned fix: score pages, then grow contiguous runs from strong seeds through the
   whole `08 71 00` section, using the induced header signature.
5. **Duplicates must stay on the same side of the split:** gerrard ×2, bridgeport ×2, morris (two copies inside
   one PDF).
6. **Non-hardware sets look like sets.** The hfh index is a door→set index, and starhardware 08 17 13 repeats set
   #103.
7. **Scanned pages:** none of the hardware pages are scanned. Image-only pages are bridgeport rev-0's cut sheets,
   the oswego geotech appendix, and cover/drawing pages. Tesseract is not installed on this host (sudo needed).
   OCR stays optional and is added in the Docker image.

## Negatives (no hardware sets; kept in dev to test precision)

- woodridge (08 71 00 pp631–647 is a proprietary spec with no schedule)
- livelle vol2, vol3, vol4
- hfh `08-71-00-01` door index
- the hollow-metal, wood-door, access-door, glazing, mirror, window-film and storefront sections from roselle,
  jc-ryan, bridgeport and valor

Raw per-book survey JSON (all 18 fields, including `pages_viewed`) is in `data/survey/<doc_id>.json`.
