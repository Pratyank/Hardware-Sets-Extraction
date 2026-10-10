"""On-disk token cache, keyed by PDF sha256.

Layout (all under ``data/tokens/``)::

    index.json                      doc_id -> {source_pdf, sha256, n_pages}
    <sha16>/manifest.json           TokenDocument header (pages, versions), no tokens
    <sha16>/p0001.tokens.json       compact token rows for page 1, ...

Pages are sharded so that callers (the pipeline, the UI's ``tokens?page=n``) load only the
pages they need from 1000+ page project manuals. Rows are stored as compact arrays; token ids
are implied by page and row index (``p{page}_w{i}``), which keeps ids stable across runs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from hwsets.models import PageInfo, Rule, Token

INGEST_VERSION = 3
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def doc_id_for(pdf: Path, raw_root: Path) -> str:
    """Human-readable, filesystem-safe id derived from the PDF's path under ``raw_root``."""
    rel = pdf.resolve().relative_to(raw_root.resolve()).with_suffix("")
    parts = [_SLUG_RE.sub("-", p.lower()).strip("-") for p in rel.parts]
    return "--".join(p for p in parts if p)


def _token_row(t: Token) -> list[Any]:
    return [t.text, *t.bbox, t.font_size, int(t.bold), t.block, t.line, int(t.ocr), int(t.strike)]


def _row_token(page: int, i: int, row: Sequence[Any]) -> Token:
    text, x0, y0, x1, y1, size, bold, block, line, is_ocr, strike = row
    # The cache is written by ``write`` from validated Tokens, so skip re-validation (hot path:
    # project manuals hold over a million tokens).
    return Token.model_construct(
        id=f"p{page}_w{i}",
        page=page,
        text=text,
        bbox=(x0, y0, x1, y1),
        font_size=size,
        bold=bool(bold),
        block=block,
        line=line,
        ocr=bool(is_ocr),
        strike=bool(strike),
    )


def _atomic_write(path: Path, payload: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


class TokenStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    # -- index ---------------------------------------------------------------
    @property
    def index_path(self) -> Path:
        return self.root / "index.json"

    def index(self) -> dict[str, dict[str, Any]]:
        if not self.index_path.exists():
            return {}
        data: dict[str, dict[str, Any]] = json.loads(self.index_path.read_text("utf-8"))
        return data

    def register(self, doc_id: str, source_pdf: str, sha256: str, n_pages: int) -> None:
        idx = self.index()
        idx[doc_id] = {"source_pdf": source_pdf, "sha256": sha256, "n_pages": n_pages}
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.index_path, json.dumps(dict(sorted(idx.items())), indent=1))

    # -- per document ----------------------------------------------------------
    def doc_dir(self, sha256: str) -> Path:
        return self.root / sha256[:16]

    def is_cached(self, sha256: str) -> bool:
        manifest = self.doc_dir(sha256) / "manifest.json"
        if not manifest.exists():
            return False
        data = json.loads(manifest.read_text("utf-8"))
        return bool(data.get("sha256") == sha256 and data.get("ingest_version") == INGEST_VERSION)

    def write(
        self,
        source_pdf: str,
        sha256: str,
        pages: list[PageInfo],
        tokens: list[list[Token]],
        rules: list[list[Rule]] | None = None,
    ) -> None:
        d = self.doc_dir(sha256)
        d.mkdir(parents=True, exist_ok=True)
        for info, page_rules in zip(pages, rules or [[] for _ in pages], strict=True):
            rows = [[*r.bbox, int(r.horizontal)] for r in page_rules]
            _atomic_write(
                d / f"p{info.page:04d}.rules.json", json.dumps(rows, separators=(",", ":"))
            )
        for info, page_tokens in zip(pages, tokens, strict=True):
            rows = [_token_row(t) for t in page_tokens]
            _atomic_write(
                d / f"p{info.page:04d}.tokens.json", json.dumps(rows, separators=(",", ":"))
            )
        manifest = {
            "source_pdf": source_pdf,
            "sha256": sha256,
            "ingest_version": INGEST_VERSION,
            "pages": [p.model_dump() for p in pages],
        }
        # Manifest last: its presence marks a complete cache entry.
        _atomic_write(d / "manifest.json", json.dumps(manifest, indent=1))

    def pages(self, sha256: str) -> list[PageInfo]:
        data = json.loads((self.doc_dir(sha256) / "manifest.json").read_text("utf-8"))
        return [PageInfo.model_validate(p) for p in data["pages"]]

    def page_tokens(self, sha256: str, page: int) -> list[Token]:
        rows = json.loads((self.doc_dir(sha256) / f"p{page:04d}.tokens.json").read_text("utf-8"))
        return [_row_token(page, i, r) for i, r in enumerate(rows)]

    def page_rules(self, sha256: str, page: int) -> list[Rule]:
        path = self.doc_dir(sha256) / f"p{page:04d}.rules.json"
        if not path.exists():
            return []
        rows = json.loads(path.read_text("utf-8"))
        return [Rule.model_construct(bbox=tuple(r[:4]), horizontal=bool(r[4])) for r in rows]

    def tokens(self, sha256: str, pages: Iterable[int] | None = None) -> list[Token]:
        wanted = [p.page for p in self.pages(sha256)] if pages is None else sorted(set(pages))
        return [t for p in wanted for t in self.page_tokens(sha256, p)]

    def load_all(self, doc_id: str) -> tuple[str, list[PageInfo], dict[int, list[Token]]]:
        """(source_pdf, pages, tokens_by_page) for one ingested document."""
        meta = self.resolve(doc_id)
        sha = meta["sha256"]
        pages = self.pages(sha)
        return meta["source_pdf"], pages, {p.page: self.page_tokens(sha, p.page) for p in pages}

    def load_rules(self, doc_id: str) -> dict[int, list[Rule]]:
        sha = self.resolve(doc_id)["sha256"]
        return {p.page: self.page_rules(sha, p.page) for p in self.pages(sha)}

    def resolve(self, doc_id: str) -> dict[str, Any]:
        try:
            return self.index()[doc_id]
        except KeyError as exc:
            raise KeyError(f"unknown document id: {doc_id!r} (run `hwsets ingest` first)") from exc
