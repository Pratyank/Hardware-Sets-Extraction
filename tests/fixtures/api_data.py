"""Synthetic data directory for the review API tests (and for smoke-running the UI).

Builds, under a given root::

    raw/demo/book.pdf          2-page PDF drawn word by word (so token bboxes are exact)
    tokens/                    TokenStore with hand-made Token / PageInfo objects
    results/demo--book.json    a DocumentResult citing those tokens

Usage: ``uv run python tests/fixtures/api_data.py /tmp/hwsets-demo`` then
``HWSETS_DATA=/tmp/hwsets-demo uv run uvicorn hwsets.api.server:app``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from hwsets.ingest.store import TokenStore
from hwsets.models import (
    Component,
    DocumentResult,
    Field,
    HardwareSet,
    Location,
    PageInfo,
    PageRegion,
    Token,
)

DOC_ID = "demo--book"
SOURCE_PDF = "demo/book.pdf"
SHA = "ab" * 32
W, H = 612.0, 792.0
SIZE = 9.0
COLS = {"qty": 60, "unit": 84, "desc": 112, "cat": 236, "mfr": 400, "fin": 440, "notes": 480}


@dataclass
class PageBuilder:
    page: int
    tokens: list[Token] = field(default_factory=list)
    draws: list[tuple[float, float, str, bool]] = field(default_factory=list)

    def words(self, x: float, y: float, text: str, bold: bool = False) -> list[str]:
        """Place ``text`` word by word at baseline ``y``; return the new token ids."""
        font = "hebo" if bold else "helv"
        ids: list[str] = []
        for word in text.split():
            width = pymupdf.get_text_length(word, fontname=font, fontsize=SIZE)
            tid = f"p{self.page}_w{len(self.tokens)}"
            self.tokens.append(
                Token(
                    id=tid,
                    page=self.page,
                    text=word,
                    bbox=(x, y - SIZE * 0.78, x + width, y + SIZE * 0.22),
                    font_size=SIZE,
                    bold=bold,
                    block=0,
                    line=len(self.draws),
                )
            )
            self.draws.append((x, y, word, bold))
            ids.append(tid)
            x += width + pymupdf.get_text_length(" ", fontname=font, fontsize=SIZE)
        return ids


def _f[T](value: T | None, ids: list[str], conf: float) -> Field[T]:
    return Field[T](value=value, token_ids=ids if value is not None else [], confidence=conf)


def _row(  # noqa: PLR0917 - one positional arg per printed column reads like the row
    pb: PageBuilder,
    y: float,
    qty: int,
    unit: str,
    desc: str,
    cat: str,
    mfr: str,
    fin: str,
    notes: str | None = None,
    confs: tuple[float, ...] = (0.95, 0.9, 0.88, 0.92, 0.9, 0.8),
    mfr_resolved: str | None = None,
) -> Component:
    q_ids = pb.words(COLS["qty"], y, str(qty))
    pb.words(COLS["unit"], y, unit)
    d_ids = pb.words(COLS["desc"], y, desc)
    c_ids = pb.words(COLS["cat"], y, cat)
    m_ids = pb.words(COLS["mfr"], y, mfr)
    f_ids = pb.words(COLS["fin"], y, fin)
    n_ids = pb.words(COLS["notes"], y, notes) if notes else []
    return Component(
        qty=Field[int | str](value=qty, token_ids=q_ids, confidence=confs[0]),
        qty_unit=unit,
        description=_f(desc, d_ids, confs[1]),
        catalog_number=_f(cat, c_ids, confs[2]),
        mfr=_f(mfr, m_ids, confs[3]),
        mfr_resolved=mfr_resolved,
        finish=_f(fin, f_ids, confs[4]),
        notes=_f(notes, n_ids, confs[5]),
    )


def _bbox(
    pb: PageBuilder, first: int, last: int | None = None
) -> tuple[float, float, float, float]:
    toks = pb.tokens[first:last]
    return (
        min(t.bbox[0] for t in toks) - 4,
        min(t.bbox[1] for t in toks) - 4,
        max(t.bbox[2] for t in toks) + 4,
        max(t.bbox[3] for t in toks) + 4,
    )


def build_result() -> tuple[DocumentResult, list[PageBuilder]]:
    p1, p2 = PageBuilder(1), PageBuilder(2)
    p1.words(60, 40, "SECTION 08 71 00 - DOOR HARDWARE")

    # Set 01: single page, mixed confidence.
    s1_start = len(p1.tokens)
    n1 = p1.words(60, 80, "HARDWARE SET NO. 01", bold=True)
    d1 = p1.words(60, 94, "Office doors - single swing")
    comps1 = [
        _row(p1, 116, 3, "EA", "HINGE", "5BB1 4.5 X 4.5", "IVE", "652", mfr_resolved="Ives"),
        _row(p1, 130, 1, "EA", "LOCKSET", "ND50PD RHO", "SCH", "626", mfr_resolved="Schlage"),
        _row(
            p1,
            144,
            1,
            "EA",
            "CLOSER",
            "4040XP",
            "LCN",
            "689",
            "PROVIDE DROP PLATE",
            confs=(0.97, 0.9, 0.7, 0.55, 0.88, 0.62),
            mfr_resolved="LCN",
        ),
        _row(p1, 158, 1, "PR", "SILENCER", "SR64", "PE", "GRY", confs=(0.5, 0.8, 0.4, 0.3, 0.9, 0)),
    ]
    s1_end = len(p1.tokens)

    # Set 02: spans pages 1-2.
    s2_start = len(p1.tokens)
    n2 = p1.words(60, 220, "HARDWARE SET NO. 02", bold=True)
    d2 = p1.words(60, 234, "Stair doors - pair, fire rated")
    comps2 = [
        _row(p1, 256, 6, "EA", "HINGE", "5BB1HW 4.5 X 4.5 NRP", "IVE", "630"),
        _row(
            p1,
            270,
            2,
            "EA",
            "EXIT DEVICE",
            "98-L-F",
            "VON",
            "626",
            confs=(0.9, 0.84, 0.6, 0.9, 0.86, 0.8),
        ),
    ]
    s2_p1_end = len(p1.tokens)
    p2.words(60, 40, "SECTION 08 71 00 - DOOR HARDWARE")
    s2_p2_start = len(p2.tokens)
    comps2 += [
        _row(p2, 80, 2, "EA", "CLOSER", "4111 EDA", "LCN", "689", "VERIFY FRAME DEPTH"),
        _row(
            p2,
            94,
            1,
            "SET",
            "GASKETING",
            "S88BL",
            "PE",
            "BLK",
            confs=(0.9, 0.7, 0.65, 0.2, 0.9, 0.8),
        ),
    ]
    s2_p2_end = len(p2.tokens)

    # Set 03: NOT USED.
    s3_start = len(p2.tokens)
    n3 = p2.words(60, 150, "HARDWARE SET NO. 03", bold=True)
    p2.words(60, 164, "NOT USED")
    s3_end = len(p2.tokens)

    sets = [
        HardwareSet(
            set_number=_f("01", n1[-1:], 0.98),
            description=_f("Office doors - single swing", d1, 0.9),
            location=Location(
                regions=[PageRegion(page=1, bbox=_bbox(p1, s1_start, s1_end))],
                line_range=("p1_l2", "p1_l7"),
            ),
            components=comps1,
            confidence=0.71,
        ),
        HardwareSet(
            set_number=_f("02", n2[-1:], 0.97),
            description=_f("Stair doors - pair, fire rated", d2, 0.66),
            location=Location(
                regions=[
                    PageRegion(page=1, bbox=_bbox(p1, s2_start, s2_p1_end)),
                    PageRegion(page=2, bbox=_bbox(p2, s2_p2_start, s2_p2_end)),
                ],
                line_range=("p1_l8", "p2_l3"),
            ),
            components=comps2,
            confidence=0.83,
        ),
        HardwareSet(
            set_number=_f("03", n3[-1:], 0.99),
            description=Field[str](),
            status="not_used",
            status_text="NOT USED",
            location=Location(
                regions=[PageRegion(page=2, bbox=_bbox(p2, s3_start, s3_end))],
                line_range=("p2_l4", "p2_l5"),
            ),
            confidence=0.95,
        ),
    ]
    result = DocumentResult(
        source_pdf=SOURCE_PDF,
        hardware_pages=[1, 2],
        column_roles={
            "x≈60": "QTY (margin 0.92)",
            "x≈112": "DESCRIPTION (margin 0.64)",
            "x≈236": "CATALOG (margin 0.48)",
            "x≈400": "MFR (margin 0.71)",
            "x≈440": "FINISH (margin 0.88)",
        },
        sets=sets,
        warnings=["set 02: component count changes across page break (2 + 2)"],
    )
    return result, [p1, p2]


def build_data_dir(root: Path, *, with_pdf: bool = True) -> DocumentResult:
    result, builders = build_result()
    pages = [
        PageInfo(
            page=b.page, width=W, height=H, rotation=0, n_tokens=len(b.tokens), has_images=False
        )
        for b in builders
    ]
    TokenStore(root / "tokens").write(SOURCE_PDF, SHA, pages, [b.tokens for b in builders])
    TokenStore(root / "tokens").register(DOC_ID, SOURCE_PDF, SHA, len(pages))
    # A registered document without a result: must not be listed or served.
    TokenStore(root / "tokens").register("unextracted", "other.pdf", "cd" * 32, 1)
    if with_pdf:
        pdf = root / "raw" / SOURCE_PDF
        pdf.parent.mkdir(parents=True, exist_ok=True)
        doc = pymupdf.open()
        for b in builders:
            page = doc.new_page(width=W, height=H)
            for x, y, word, bold in b.draws:
                page.insert_text((x, y), word, fontname="hebo" if bold else "helv", fontsize=SIZE)
        doc.save(pdf)
        doc.close()
    (root / "results").mkdir(parents=True, exist_ok=True)
    (root / "results" / f"{DOC_ID}.json").write_text(result.model_dump_json(indent=1), "utf-8")
    return result


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "tmp-api-data")
    build_data_dir(out)
    print(f"wrote synthetic review data to {out}")
