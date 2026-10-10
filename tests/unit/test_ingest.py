"""Phase 1 ingest tests on small synthetic PDFs (no dependency on data/raw)."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from hwsets.ingest import render
from hwsets.ingest.pdf import extract_document
from hwsets.ingest.store import TokenStore, doc_id_for, sha256_file

LINES = [
    ("HARDWARE SET NO. 01", True),
    ("3 EA HINGE 5BB1 4.5 X 4.5 652 IVE", False),
    ("1 EA CLOSER 4040XP 689 LCN", False),
]


def _make_pdf(path: Path, rotation: int = 0) -> Path:
    doc = pymupdf.open()
    for _ in range(2):
        page = doc.new_page(width=612, height=792)
        y = 72.0
        for text, bold in LINES:
            page.insert_text((72, y), text, fontname="hebo" if bold else "helv", fontsize=10)
            y += 18
        page.set_rotation(rotation)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def pdf(tmp_path: Path) -> Path:
    return _make_pdf(tmp_path / "book.pdf")


def test_token_ids_are_stable_across_runs(pdf: Path) -> None:
    _, a = extract_document(pdf)
    _, b = extract_document(pdf)
    assert [[t.model_dump() for t in p] for p in a] == [[t.model_dump() for t in p] for p in b]
    assert a[0][0].id == "p1_w0"
    assert a[1][0].id == "p2_w0"
    assert [t.id for t in a[0]] == [f"p1_w{i}" for i in range(len(a[0]))]


def test_words_and_typography(pdf: Path) -> None:
    _, pages = extract_document(pdf)
    words = [t.text for t in pages[0]]
    assert words[:4] == ["HARDWARE", "SET", "NO.", "01"]
    assert "5BB1" in words and "LCN" in words
    header = pages[0][0]
    assert header.bold
    body = next(t for t in pages[0] if t.text == "HINGE")
    assert not body.bold
    assert body.font_size == pytest.approx(10, abs=0.5)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_bboxes_inside_displayed_page(tmp_path: Path, rotation: int) -> None:
    pdf = _make_pdf(tmp_path / f"r{rotation}.pdf", rotation)
    infos, pages = extract_document(pdf)
    for info, toks in zip(infos, pages, strict=True):
        assert info.rotation == rotation
        if rotation in (90, 270):
            assert (info.width, info.height) == (792, 612)
        for t in toks:
            x0, y0, x1, y1 = t.bbox
            assert 0 <= x0 <= x1 <= info.width
            assert 0 <= y0 <= y1 <= info.height


def test_rotated_bbox_matches_rendered_text(tmp_path: Path) -> None:
    """A token's displayed bbox must cover ink in the rendered (rotated) PNG."""
    pdf = _make_pdf(tmp_path / "r90.pdf", 90)
    _, pages = extract_document(pdf)
    tok = next(t for t in pages[0] if t.text == "HARDWARE")
    with pymupdf.open(pdf) as doc:
        pix = doc[0].get_pixmap(dpi=render.DPI, alpha=False)
    x0, y0, x1, y1 = render.points_to_pixels(tok.bbox)
    dark = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            if sum(pix.pixel(x, y)[:3]) < 384:
                dark += 1
    assert dark > 20


def test_png_scale_round_trip(pdf: Path, tmp_path: Path) -> None:
    sha = sha256_file(pdf)
    (png,) = render.render_pages(pdf, tmp_path / "pages", sha, [1])
    with pymupdf.open(pdf) as doc:
        rect = doc[0].rect
    pix = pymupdf.Pixmap(str(png))
    assert abs(pix.width - rect.width * render.SCALE) <= 1
    assert abs(pix.height - rect.height * render.SCALE) <= 1
    bbox = (72.0, 60.5, 300.25, 80.0)
    back = render.pixels_to_points(render.points_to_pixels(bbox))
    assert all(abs(a - b) <= 1 / render.SCALE for a, b in zip(bbox, back, strict=True))


def test_store_round_trip_and_cache(pdf: Path, tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens")
    sha = sha256_file(pdf)
    assert not store.is_cached(sha)
    infos, pages = extract_document(pdf)
    store.write("book.pdf", sha, infos, pages)
    assert store.is_cached(sha)
    assert store.pages(sha) == infos
    assert store.page_tokens(sha, 2) == pages[1]
    assert store.tokens(sha) == [t for p in pages for t in p]
    store.register("book", "book.pdf", sha, len(infos))
    assert store.resolve("book")["sha256"] == sha
    with pytest.raises(KeyError):
        store.resolve("missing")


def test_doc_id_is_slug(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    (raw / "Valor Acres  Bldg E").mkdir(parents=True)
    p = raw / "Valor Acres  Bldg E" / "087100-DOOR HARDWARE_Rev 2.pdf"
    p.write_bytes(b"%PDF-1.4")
    assert doc_id_for(p, raw) == "valor-acres-bldg-e--087100-door-hardware-rev-2"


def test_strikethrough_detected(tmp_path: Path) -> None:
    """A redline deletion (text with a strike line through it) is flagged, others are not."""
    path = tmp_path / "strike.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "SCH", fontname="helv", fontsize=10)
    page.insert_text((120, 100), "BES", fontname="helv", fontsize=10)
    # strike through "SCH" only
    page.draw_line((70, 96.5), (95, 96.5), color=(0, 0, 0), width=0.8)
    doc.save(path)
    doc.close()
    _, pages = extract_document(path)
    flags = {t.text: t.strike for t in pages[0]}
    assert flags == {"SCH": True, "BES": False}
