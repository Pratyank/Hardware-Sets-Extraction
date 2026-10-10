"""POST /api/docs/upload: a generated PDF goes through ingest + extract and becomes reviewable."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from hwsets.api.server import create_app
from hwsets.api.upload import slugify_filename

COL_X = (72.0, 100.0, 140.0, 270.0, 450.0, 500.0)  # qty unit description catalog finish mfr
ROWS: list[tuple[str, bool]] = [
    ("HARDWARE SET NO. 01", True),
    ("ENTRANCE DOORS", False),
    ("QTY|UNIT|DESCRIPTION|CATALOG NUMBER|FINISH|MFR", False),
    ("3|EA|HINGE|5BB1 4.5 X 4.5|652|IVE", False),
    ("1|EA|LOCKSET|ND50PD RHO|626|SCH", False),
    ("1|EA|CLOSER|4040XP|689|LCN", False),
    ("", False),
    ("HARDWARE SET NO. 02", True),
    ("OFFICE", False),
    ("3|EA|HINGE|5BB1 4.5 X 4.5|652|IVE", False),
    ("1|EA|OFFICE LOCK|ND50PD RHO|626|SCH", False),
    ("1|EA|STOP|WS406|630|IVE", False),
]


def _schedule_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    y = 110.0
    for text, bold in ROWS:
        y += 14.0 + (10.0 if bold else 0.0)
        cells = text.split("|") if "|" in text else [text]
        for x, cell in zip(COL_X, cells, strict=False):
            if cell:
                page.insert_text((x, y), cell, fontname="hebo" if bold else "helv", fontsize=9)
    data: bytes = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def client(data_dir: Path) -> TestClient:
    return TestClient(create_app(data_dir, max_upload_bytes=2 * 1024 * 1024))


def test_upload_pdf_extracts_two_sets(client: TestClient, data_dir: Path) -> None:
    pdf = _schedule_pdf()
    r = client.post(
        "/api/docs/upload",
        files={"file": ("Door Schedule.pdf", pdf, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["doc_id"] == "uploads--door-schedule"
    assert body["n_sets"] == 2
    assert (data_dir / "results" / "uploads--door-schedule.json").is_file()
    stored = list((data_dir / "raw" / "uploads").glob("*.pdf"))
    assert len(stored) == 1 and len(stored[0].stem) == 16

    # The uploaded book is now a regular reviewable document.
    docs = {d["doc_id"]: d for d in client.get("/api/docs/list").json()}
    assert docs["uploads--door-schedule"]["n_sets"] == 2
    res = client.get("/api/docs/uploads--door-schedule/result").json()
    assert [s["set_number"]["value"] for s in res["sets"]] == ["1", "2"]
    png = client.get("/api/docs/uploads--door-schedule/page/1.png")
    assert png.status_code == 200 and png.content.startswith(b"\x89PNG")

    # Re-uploading the same bytes is idempotent (same id, cached tokens).
    again = client.post(
        "/api/docs/upload",
        files={"file": ("Door Schedule.pdf", pdf, "application/pdf")},
    )
    assert again.json()["doc_id"] == "uploads--door-schedule"


def test_non_pdf_rejected(client: TestClient, data_dir: Path) -> None:
    r = client.post(
        "/api/docs/upload", files={"file": ("notes.pdf", b"hello world", "application/pdf")}
    )
    assert r.status_code == 415
    r = client.post("/api/docs/upload", files={"file": ("a.png", b"%PDF-1.7 fake", "image/png")})
    assert r.status_code == 415
    uploads = data_dir / "raw" / "uploads"
    assert not uploads.exists() or not any(uploads.iterdir())


def test_not_multipart_rejected(client: TestClient) -> None:
    r = client.post(
        "/api/docs/upload", content=b"%PDF-1.7", headers={"content-type": "application/pdf"}
    )
    assert r.status_code == 415


def test_missing_file_field(client: TestClient) -> None:
    r = client.post("/api/docs/upload", data={"other": "x"}, files={"nope": ("x.txt", b"x")})
    assert r.status_code == 422


def test_empty_and_corrupt_pdf_unprocessable(client: TestClient) -> None:
    assert (
        client.post(
            "/api/docs/upload", files={"file": ("e.pdf", b"", "application/pdf")}
        ).status_code
        == 422
    )
    r = client.post(
        "/api/docs/upload", files={"file": ("c.pdf", b"%PDF-1.7\ngarbage", "application/pdf")}
    )
    assert r.status_code == 422


def test_oversize_rejected(client: TestClient, data_dir: Path) -> None:
    big = b"%PDF-1.7\n" + b"0" * (3 * 1024 * 1024)
    r = client.post("/api/docs/upload", files={"file": ("big.pdf", big, "application/pdf")})
    assert r.status_code == 413
    uploads = data_dir / "raw" / "uploads"
    assert not uploads.exists() or not any(uploads.iterdir())


def test_oversize_rejected_while_streaming(data_dir: Path) -> None:
    # Content-Length within the slack, but the file part itself is over the limit.
    client = TestClient(create_app(data_dir, max_upload_bytes=1000))
    r = client.post(
        "/api/docs/upload", files={"file": ("big.pdf", b"%PDF-" + b"0" * 2000, "application/pdf")}
    )
    assert r.status_code == 413


def test_path_traversal_in_filename_is_neutralised(client: TestClient, data_dir: Path) -> None:
    r = client.post(
        "/api/docs/upload",
        files={"file": ("../../../etc/Passwd Schedule.pdf", _schedule_pdf(), "application/pdf")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["doc_id"] == "uploads--passwd-schedule"
    written = [p for p in data_dir.rglob("*") if p.is_file()]
    assert all(p.resolve().is_relative_to(data_dir.resolve()) for p in written)
    assert not (data_dir.parent / "etc").exists()


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("..\\..\\windows\\evil.PDF", "evil"),
        ("/abs/path/My Book (rev 2).pdf", "my-book-rev-2"),
        ("....pdf", "document"),
        (None, "document"),
        ("x" * 200 + ".pdf", "x" * 60),
    ],
)
def test_slugify_filename(name: str | None, slug: str) -> None:
    assert slugify_filename(name) == slug
