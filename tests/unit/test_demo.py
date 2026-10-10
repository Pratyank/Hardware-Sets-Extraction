"""scripts/demo.py: preloads available demo books, skips missing ones, is idempotent."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ROOT = Path(__file__).parents[2]
demo = _load(ROOT / "scripts" / "demo.py", "hwsets_demo_script")
upload_tests = _load(Path(__file__).with_name("test_api_upload.py"), "hwsets_upload_tests")


def test_demo_preloads_available_book_and_skips_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pdf = tmp_path / "raw" / "Valor Acres Building E" / "087100 Door Hardware Rev 2.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(upload_tests._schedule_pdf())

    assert demo.main(["--data", str(tmp_path)]) == 0
    doc_id = "valor-acres-building-e--087100-door-hardware-rev-2"
    result = json.loads((tmp_path / "results" / f"{doc_id}.json").read_text("utf-8"))
    assert len(result["sets"]) == 2
    assert list((tmp_path / "pages").rglob("p0001.png"))
    index = json.loads((tmp_path / "tokens" / "index.json").read_text("utf-8"))
    assert list(index) == [doc_id]
    out = capsys.readouterr().out
    assert "1/3 books ready" in out and out.count("skip") == 2

    # Second run hits the token cache and rewrites the same result.
    assert demo.main(["--data", str(tmp_path)]) == 0
    assert "cached" in capsys.readouterr().out


def test_demo_fails_when_nothing_available(tmp_path: Path) -> None:
    assert demo.main(["--data", str(tmp_path)]) == 1


def test_demo_refuses_holdout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "splits.json").write_text(json.dumps({"holdout": {"secret-book": {}}}))
    monkeypatch.setitem(demo.DEMO_BOOKS, "secret-book", "x")
    with pytest.raises(SystemExit):
        demo.main(["--data", str(tmp_path)])
