# Gold labelling guidelines

Gold files are the ground truth used by `hwsets eval`. They must be **independent of the extractor**:
draft them by looking at rendered page images. Never run, read, or look at extractor output (`hwsets extract`,
`src/hwsets/{layout,segment,columns,components,pipeline}`), and never copy values from it.

Allowed tools (these show raw PDF text only, not extraction):
- `uv run hwsets render <doc_id> <pages>` renders PNGs. View them with an image viewer or the Read tool. This is
  the primary source.
- `uv run hwsets tokens <doc_id> <page> [--grep TEXT]` prints raw words grouped by PDF line, with bboxes in PDF
  points. Use it to copy exact spellings and to get set bounding boxes. Struck-through words are prefixed `~`.
  Raw PDF line grouping is often wrong: wrapped cells appear out of order. **The image decides.**
- `uv run hwsets gold-check data/gold/<doc_id>.gold.json` validates the schema.

## File format (`data/gold/<doc_id>.gold.json`)

```json
{
  "source_pdf": "<doc_id>",
  "gold_pages": "7-18",
  "_annotator": "agent-name, drafted from page images",
  "sets": [
    {
      "set_number": "01",
      "description": "ENTRANCE DOORS",
      "status": "active",
      "location": {"pages": [7, 8], "regions": [
        {"page": 7, "bbox": [36.0, 410.2, 576.0, 760.0]},
        {"page": 8, "bbox": [36.0, 60.0, 576.0, 140.5]}
      ]},
      "components": [
        {"qty": 3, "qty_unit": "EA", "description": "HINGE", "catalog_number": "5BB1 4.5 X 4.5 NRP",
         "mfr": "IVE", "finish": "652", "notes": null}
      ]
    }
  ]
}
```

## Field conventions

- **Scope:** label every set whose header lies inside `gold_pages`. If a set starts inside the window and
  continues past its end, label the whole set. Sets that are entirely struck through (redline-deleted) are
  **not** labelled.
- **set_number:** the identifier as printed, without the keyword: `Hardware Group No. 01` → `"01"`,
  `Set: EX-1.0` → `"EX-1.0"`, `Heading #17` → `"17"`, `HW 02A` → `"02A"`, `Set #AL 01` → `"AL 01"`.
  Keep leading zeros. Eval normalizes them.
- **description:** the set's heading or title text if printed (`"ENTRANCE DOORS"`, the text after `Description:`,
  or the title after `HW 01`). Use null if there is none. Never put door-number lists, "Provide each … door(s)
  with the following", or operational narratives here.
- **status:** `"not_used"` when the set is marked NOT USED / N/A / OMITTED / DELETED / VOID. Such sets have
  `components: []`.
- **location:** `pages` lists every page the set touches. Give one region per page: a rough bbox in PDF points
  (x0, y0, x1, y1, origin top-left, as printed by `hwsets tokens`) covering the header through the last
  component or note line on that page. ±10 pt is fine.
- **components:** one per hardware item row. These are **not** components:
  - door lists (`Doors: 101, 102`, `Item #` rows)
  - door-size lines
  - `Provide each…` lines
  - column header rows
  - operational descriptions
  - `Notes:` blocks belonging to the set
  - legends

  "By others" items that occupy a row (e.g. `1 EA POWER SUPPLY BY DIV 28`) **are** components.
- **qty:** an integer as printed. Use null when no number is printed (blank, `--`, `As Req`, `__`). Never guess.
  Write decimals like `3.0` as `3`.
- **qty_unit:** uppercase and without punctuation: `EA`, `PR`, `SET`, `LOT`, `EA-R`. Normalize `Ea.` → `EA` and
  `Pair` → `PR`. Use null if no unit is printed.
- **description:** the item name as printed (`HINGE`, `CLOSER`, `EXIT DEVICE`). Join wrapped lines of the same
  cell with a single space, in visual reading order.
- **catalog_number:** model and options as printed (`ND80PD RHO 10-025`). Join wrapped continuation lines with
  a single space. When the manufacturer and catalog share one cell (`IVES - 5BB1 4.5" x 4.5"`), split them:
  mfr `IVES`, catalog `5BB1 4.5" x 4.5"`.
- **mfr:** the manufacturer code or name **exactly as printed** (`IVE`, `PE`, `Pemko`, `B/O`). Use null if the
  book has no manufacturer column or the cell is blank. Do not expand codes.
- **finish:** the finish code exactly as printed (`626`, `US26D`, `BLK`, `630-316`). Use null if blank or if
  there is no finish column.
- **notes:** text in a dedicated notes column, or a note printed on that item's row (e.g. a parenthetical
  that is not part of the catalog). Otherwise null.
- **Struck-through text** is deleted and never appears in any value. If a row shows `SCH ~~BES~~`, the mfr is
  whichever value is *not* struck.
- **Uncertainty:** add `"_uncertain": true` to a component or set you are unsure about, plus
  `"_uncertain_note": "why"`. Do not skip hard cases. Label them and mark them.

## Process

1. Look at the window's pages as images, in order, and list every set header.
2. Transcribe each set, using `hwsets tokens` for exact strings and bboxes.
3. Run `gold-check`. Check that the set count and order match the images.
4. Re-view each page image once more against your JSON. Check especially manufacturer vs. finish, the
   quantities, and the sets that span pages.
