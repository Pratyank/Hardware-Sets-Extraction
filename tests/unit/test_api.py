"""Review API tests against a synthetic data dir (tests/fixtures/api_data.py)."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient

from hwsets.api import server
from hwsets.api.server import create_app
from hwsets.ingest import render
from hwsets.models import FlatDocument, HardwareSet


def _load_fixture() -> ModuleType:
    path = Path(__file__).parents[1] / "fixtures" / "api_data.py"
    spec = importlib.util.spec_from_file_location("api_data", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


fx = _load_fixture()
DOC = fx.DOC_ID


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    fx.build_data_dir(tmp_path)
    return tmp_path


@pytest.fixture
def client(data_dir: Path) -> TestClient:
    return TestClient(create_app(data_dir))


def _set(client: TestClient, idx: int) -> dict[str, Any]:
    r = client.get(f"/api/docs/{DOC}/result")
    assert r.status_code == 200
    s: dict[str, Any] = r.json()["sets"][idx]
    return s


# -- listing and reading ------------------------------------------------------------


def test_list_docs_only_lists_extracted_documents(client: TestClient) -> None:
    r = client.get("/api/docs/list")
    assert r.status_code == 200
    docs = r.json()
    assert [d["doc_id"] for d in docs] == [DOC]
    d = docs[0]
    assert d["source_pdf"] == fx.SOURCE_PDF
    assert d["n_sets"] == 3
    assert d["n_pages"] == 2
    assert d["has_corrections"] is False
    assert d["mean_confidence"] == pytest.approx((0.71 + 0.83 + 0.95) / 3, abs=1e-3)


def test_list_docs_empty_data_dir(tmp_path: Path) -> None:
    c = TestClient(create_app(tmp_path))
    assert c.get("/api/docs/list").json() == []


def test_result_round_trips_document(client: TestClient) -> None:
    r = client.get(f"/api/docs/{DOC}/result")
    assert r.status_code == 200
    body = r.json()
    assert body["source_pdf"] == fx.SOURCE_PDF
    assert [s["set_number"]["value"] for s in body["sets"]] == ["01", "02", "03"]
    assert body["sets"][2]["status"] == "not_used"
    assert body["column_roles"]["x≈400"] == "MFR (margin 0.71)"
    assert body["warnings"]


def test_pages_reports_sizes_and_scale(client: TestClient) -> None:
    r = client.get(f"/api/docs/{DOC}/pages")
    assert r.status_code == 200
    body = r.json()
    assert body["scale"] == pytest.approx(render.SCALE)
    assert body["dpi"] == render.DPI
    assert [(p["page"], p["width"], p["height"]) for p in body["pages"]] == [
        (1, fx.W, fx.H),
        (2, fx.W, fx.H),
    ]


def test_tokens_of_page(client: TestClient) -> None:
    r = client.get(f"/api/docs/{DOC}/tokens", params={"page": 2})
    assert r.status_code == 200
    toks = r.json()
    assert toks[0]["id"] == "p2_w0"
    assert all(t["page"] == 2 for t in toks)
    # every token id cited by the result resolves to a real token
    cited = {
        tid
        for s in client.get(f"/api/docs/{DOC}/result").json()["sets"]
        for c in s["components"]
        for f in ("qty", "description", "catalog_number", "mfr", "finish", "notes")
        for tid in c[f]["token_ids"]
    }
    p1 = {t["id"] for t in client.get(f"/api/docs/{DOC}/tokens?page=1").json()}
    assert cited <= p1 | {t["id"] for t in toks}


def test_tokens_requires_valid_page(client: TestClient) -> None:
    assert client.get(f"/api/docs/{DOC}/tokens").status_code == 422
    assert client.get(f"/api/docs/{DOC}/tokens?page=0").status_code == 422
    assert client.get(f"/api/docs/{DOC}/tokens?page=3").status_code == 404


# -- page images ----------------------------------------------------------------------


def test_page_png_renders_lazily_and_caches(client: TestClient, data_dir: Path) -> None:
    cached = render.png_path(data_dir / "pages", fx.SHA, 1)
    assert not cached.exists()
    r = client.get(f"/api/docs/{DOC}/page/1.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert "max-age" in r.headers["cache-control"]
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert cached.exists()
    # served from cache even once the PDF is gone
    (data_dir / "raw" / fx.SOURCE_PDF).unlink()
    assert client.get(f"/api/docs/{DOC}/page/1.png").status_code == 200
    assert client.get(f"/api/docs/{DOC}/page/2.png").status_code == 404


def test_page_png_404_without_pdf_or_cache(tmp_path: Path) -> None:
    fx.build_data_dir(tmp_path, with_pdf=False)
    c = TestClient(create_app(tmp_path))
    assert c.get(f"/api/docs/{DOC}/page/1.png").status_code == 404


@pytest.mark.parametrize("page", ["0", "3", "-1"])
def test_page_png_bounds(client: TestClient, page: str) -> None:
    assert client.get(f"/api/docs/{DOC}/page/{page}.png").status_code == 404


def test_page_png_non_integer(client: TestClient) -> None:
    assert client.get(f"/api/docs/{DOC}/page/abc.png").status_code == 422


# -- corrections -------------------------------------------------------------------------


def test_put_correction_round_trip_marks_human(client: TestClient, data_dir: Path) -> None:
    s = _set(client, 0)
    s["components"][3]["mfr"]["value"] = "PEMKO"
    s["components"][0]["qty"]["value"] = 4
    s["description"]["value"] = "Office doors"
    r = client.put(f"/api/docs/{DOC}/sets/0", json=s)
    assert r.status_code == 200, r.text
    saved = r.json()["set"]
    mfr = saved["components"][3]["mfr"]
    assert (mfr["value"], mfr["source"], mfr["confidence"]) == ("PEMKO", "human", 1.0)
    assert saved["components"][0]["qty"]["source"] == "human"
    assert saved["description"]["source"] == "human"
    # unchanged fields keep the extractor's provenance
    assert saved["components"][1]["mfr"]["source"] == "rule"
    assert saved["components"][3]["finish"]["confidence"] == pytest.approx(0.9)

    on_disk = json.loads((data_dir / "corrections" / f"{DOC}.json").read_text())
    assert list(on_disk) == ["0"]
    HardwareSet.model_validate(on_disk["0"])

    # corrections override the set in /result, and a fresh app sees them too
    fresh = TestClient(create_app(data_dir))
    again = _set(fresh, 0)
    assert again["components"][3]["mfr"]["value"] == "PEMKO"
    assert _set(fresh, 1)["components"][0]["mfr"]["source"] == "rule"
    listed = fresh.get("/api/docs/list").json()[0]
    assert listed["has_corrections"] is True
    # the raw extractor output is untouched
    raw = json.loads((data_dir / "results" / f"{DOC}.json").read_text())
    assert raw["sets"][0]["components"][3]["mfr"]["value"] == "PE"


def test_put_keeps_client_human_mark_and_new_rows(client: TestClient) -> None:
    s = _set(client, 1)
    s["components"][0]["finish"]["source"] = "human"  # verified, value unchanged
    new = json.loads(json.dumps(s["components"][0]))
    new["description"]["value"] = "WALL STOP"
    s["components"].append(new)
    saved = client.put(f"/api/docs/{DOC}/sets/1", json=s).json()["set"]
    assert saved["components"][0]["finish"]["source"] == "human"
    assert saved["components"][0]["finish"]["confidence"] == 1.0
    assert len(saved["components"]) == 5
    assert saved["components"][4]["description"]["source"] == "human"


def test_multiple_corrections_accumulate(client: TestClient, data_dir: Path) -> None:
    for idx in (2, 0):
        s = _set(client, idx)
        s["set_number"]["value"] = f"X{idx}"
        assert client.put(f"/api/docs/{DOC}/sets/{idx}", json=s).status_code == 200
    on_disk = json.loads((data_dir / "corrections" / f"{DOC}.json").read_text())
    assert sorted(on_disk) == ["0", "2"]


def test_delete_correction_reverts(client: TestClient) -> None:
    s = _set(client, 0)
    s["set_number"]["value"] = "99"
    client.put(f"/api/docs/{DOC}/sets/0", json=s)
    r = client.delete(f"/api/docs/{DOC}/sets/0")
    assert r.status_code == 200
    assert r.json()["set"]["set_number"]["value"] == "01"
    assert _set(client, 0)["set_number"]["value"] == "01"
    assert client.get("/api/docs/list").json()[0]["has_corrections"] is False
    assert client.delete(f"/api/docs/{DOC}/sets/7").status_code == 404


@pytest.mark.parametrize("idx", [3, 99, -1])
def test_put_set_index_bounds(client: TestClient, idx: int) -> None:
    s = _set(client, 0)
    assert client.put(f"/api/docs/{DOC}/sets/{idx}", json=s).status_code == 404


def test_put_rejects_invalid_body(client: TestClient) -> None:
    s = _set(client, 0)
    s["components"][0]["qty"]["confidence"] = 7
    assert client.put(f"/api/docs/{DOC}/sets/0", json=s).status_code == 422
    s = _set(client, 0)
    s["unexpected"] = True
    assert client.put(f"/api/docs/{DOC}/sets/0", json=s).status_code == 422
    s = _set(client, 0)
    s["location"]["regions"][0]["page"] = 40
    assert client.put(f"/api/docs/{DOC}/sets/0", json=s).status_code == 422
    assert client.put(f"/api/docs/{DOC}/sets/0", content=b"not json").status_code == 422


# -- export ------------------------------------------------------------------------------


def test_export_gold_uses_corrections(client: TestClient, data_dir: Path) -> None:
    s = _set(client, 0)
    s["components"][3]["mfr"]["value"] = "PEMKO"
    client.put(f"/api/docs/{DOC}/sets/0", json=s)
    r = client.post(f"/api/docs/{DOC}/export-gold")
    assert r.status_code == 200
    flat = FlatDocument.model_validate(r.json())
    assert flat.source_pdf == fx.SOURCE_PDF
    assert flat.gold_pages == "1-2"
    assert [x.set_number for x in flat.sets] == ["01", "02", "03"]
    assert flat.sets[0].components[3].mfr == "PEMKO"
    assert flat.sets[1].location.pages == [1, 2]
    assert flat.sets[2].status == "not_used"
    out = data_dir / "corrections" / f"{DOC}.gold.json"
    assert FlatDocument.model_validate_json(out.read_text()) == flat
    assert not (data_dir / "gold").exists()


# -- unknown documents and traversal -------------------------------------------------------


@pytest.mark.parametrize(
    "doc_id",
    [
        "nope",
        "unextracted",
        "..",
        "...",
        "%2e%2e",
        "..%2f..%2fetc",
        "DEMO--BOOK",
        "demo--book.json",
    ],
)
def test_unknown_or_malicious_doc_ids(client: TestClient, doc_id: str) -> None:
    for url in (
        f"/api/docs/{doc_id}/result",
        f"/api/docs/{doc_id}/pages",
        f"/api/docs/{doc_id}/tokens?page=1",
        f"/api/docs/{doc_id}/page/1.png",
    ):
        assert client.get(url).status_code == 404, url
    assert client.post(f"/api/docs/{doc_id}/export-gold").status_code == 404
    s = _set(client, 0)
    assert client.put(f"/api/docs/{doc_id}/sets/0", json=s).status_code == 404


def test_traversal_via_index_source_pdf_is_refused(data_dir: Path) -> None:
    """A poisoned index entry must not make the server read PDFs outside raw/."""
    outside = data_dir / "outside.pdf"
    (data_dir / "raw" / fx.SOURCE_PDF).rename(outside)
    idx_path = data_dir / "tokens" / "index.json"
    idx = json.loads(idx_path.read_text())
    idx[DOC]["source_pdf"] = "../outside.pdf"
    idx_path.write_text(json.dumps(idx))
    c = TestClient(create_app(data_dir))
    assert c.get(f"/api/docs/{DOC}/page/1.png").status_code == 404


def test_unknown_api_route_is_json_404(client: TestClient) -> None:
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["detail"] == "not found"


# -- static UI ----------------------------------------------------------------------------


def test_static_ui_served(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_module_level_app_uses_env(monkeypatch: pytest.MonkeyPatch, data_dir: Path) -> None:
    monkeypatch.setenv("HWSETS_DATA", str(data_dir))
    reloaded = importlib.reload(server)
    try:
        docs = TestClient(reloaded.app).get("/api/docs/list").json()
        assert [d["doc_id"] for d in docs] == [DOC]
    finally:
        monkeypatch.delenv("HWSETS_DATA")
        importlib.reload(server)
