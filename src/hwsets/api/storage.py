"""Filesystem access for the review API: results, corrections, tokens and page images.

Layout under the data directory::

    results/<doc_id>.json             DocumentResult written by the extractor (read-only here)
    corrections/<doc_id>.json         {"<set_idx>": HardwareSet, ...} saved by reviewers
    corrections/<doc_id>.gold.json    FlatDocument exported from the corrected result
    tokens/                           TokenStore (index.json is the registry of doc ids)
    pages/                            rendered PNG cache (ingest.render)
    raw/<source_pdf>                  original PDFs, used to render pages lazily

Every ``doc_id`` is checked against the token index before any path is built from it, so
request input never reaches the filesystem unvalidated. Writes are atomic (temp + rename).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hwsets.export import to_flat
from hwsets.ingest import render
from hwsets.ingest.store import TokenStore
from hwsets.models import (
    Component,
    DocumentResult,
    Field,
    FlatDocument,
    HardwareSet,
    PageInfo,
    Token,
)

_DOC_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
HUMAN_CONFIDENCE = 1.0


class NotFoundError(LookupError):
    """A document, set, page or file that the request refers to does not exist."""


class InvalidCorrectionError(ValueError):
    """A correction that parses as a HardwareSet but is inconsistent with the document."""


@dataclass(frozen=True)
class DocMeta:
    doc_id: str
    source_pdf: str
    sha256: str
    n_pages: int


def atomic_write_text(path: Path, payload: str) -> None:
    """Write ``payload`` to ``path`` via a unique temp file in the same dir, then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _mark_human[T](edited: Field[T], original: Field[T] | None) -> None:
    """A field whose value differs from the extractor's output is human-sourced."""
    if original is None:
        if edited.value is not None and edited.value != "":
            edited.source = "human"
            edited.confidence = HUMAN_CONFIDENCE
        return
    if edited.value != original.value:
        edited.source = "human"
        edited.confidence = HUMAN_CONFIDENCE
    elif edited.source == "human":
        edited.confidence = HUMAN_CONFIDENCE


def _component_fields(c: Component) -> list[Field[Any]]:
    return [c.qty, c.description, c.catalog_number, c.mfr, c.finish, c.notes]


def mark_human_edits(edited: HardwareSet, original: HardwareSet) -> HardwareSet:
    """Return a copy of ``edited`` where every field changed vs ``original`` is human."""
    out = edited.model_copy(deep=True)
    _mark_human(out.set_number, original.set_number)
    _mark_human(out.description, original.description)
    _mark_human(out.notes, original.notes)
    for i, comp in enumerate(out.components):
        orig = original.components[i] if i < len(original.components) else None
        orig_fields: list[Field[Any] | None] = (
            list(_component_fields(orig)) if orig is not None else [None] * 6
        )
        for f, o in zip(_component_fields(comp), orig_fields, strict=True):
            _mark_human(f, o)
    return out


class DataStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir
        self.results_dir = data_dir / "results"
        self.corrections_dir = data_dir / "corrections"
        self.pages_dir = data_dir / "pages"
        self.raw_dir = data_dir / "raw"
        self.tokens = TokenStore(data_dir / "tokens")
        self._lock = threading.Lock()  # serialises correction writes and page renders

    # -- documents -----------------------------------------------------------
    def doc(self, doc_id: str) -> DocMeta:
        """Resolve ``doc_id`` via the token index; the only gate from input to paths."""
        if not _DOC_ID_RE.fullmatch(doc_id):
            raise NotFoundError(f"unknown document: {doc_id!r}")
        meta = self.tokens.index().get(doc_id)
        if meta is None or not self._result_path(doc_id).is_file():
            raise NotFoundError(f"unknown document: {doc_id!r}")
        return DocMeta(
            doc_id=doc_id,
            source_pdf=str(meta["source_pdf"]),
            sha256=str(meta["sha256"]),
            n_pages=int(meta["n_pages"]),
        )

    def doc_ids(self) -> list[str]:
        return [d for d in sorted(self.tokens.index()) if _DOC_ID_RE.fullmatch(d)]

    def _result_path(self, doc_id: str) -> Path:
        return self.results_dir / f"{doc_id}.json"

    def _corrections_path(self, doc_id: str) -> Path:
        return self.corrections_dir / f"{doc_id}.json"

    def gold_path(self, doc_id: str) -> Path:
        return self.corrections_dir / f"{doc_id}.gold.json"

    def raw_result(self, doc: DocMeta) -> DocumentResult:
        text = self._result_path(doc.doc_id).read_text("utf-8")
        return DocumentResult.model_validate_json(text)

    # -- corrections -----------------------------------------------------------
    def corrections(self, doc: DocMeta) -> dict[int, HardwareSet]:
        path = self._corrections_path(doc.doc_id)
        if not path.is_file():
            return {}
        data: dict[str, Any] = json.loads(path.read_text("utf-8"))
        return {int(k): HardwareSet.model_validate(v) for k, v in data.items()}

    def _write_corrections(self, doc: DocMeta, corr: dict[int, HardwareSet]) -> None:
        payload = {str(k): corr[k].model_dump(mode="json") for k in sorted(corr)}
        atomic_write_text(self._corrections_path(doc.doc_id), json.dumps(payload, indent=1))

    def result(self, doc: DocMeta) -> DocumentResult:
        """The extractor's result with saved corrections applied (they replace whole sets)."""
        res = self.raw_result(doc)
        for idx, hs in self.corrections(doc).items():
            if 0 <= idx < len(res.sets):
                res.sets[idx] = hs
        return res

    def save_correction(self, doc: DocMeta, set_idx: int, edited: HardwareSet) -> HardwareSet:
        original = self._original_set(doc, set_idx)
        for region in edited.location.regions:
            if not 1 <= region.page <= doc.n_pages:
                raise InvalidCorrectionError(f"region page {region.page} is out of range")
        marked = mark_human_edits(edited, original)
        with self._lock:
            corr = self.corrections(doc)
            corr[set_idx] = marked
            self._write_corrections(doc, corr)
        return marked

    def delete_correction(self, doc: DocMeta, set_idx: int) -> HardwareSet:
        original = self._original_set(doc, set_idx)
        with self._lock:
            corr = self.corrections(doc)
            if corr.pop(set_idx, None) is not None:
                self._write_corrections(doc, corr)
        return original

    def _original_set(self, doc: DocMeta, set_idx: int) -> HardwareSet:
        sets = self.raw_result(doc).sets
        if not 0 <= set_idx < len(sets):
            raise NotFoundError(f"set index {set_idx} out of range (0..{len(sets) - 1})")
        return sets[set_idx]

    def export_gold(self, doc: DocMeta) -> FlatDocument:
        res = self.result(doc)
        flat = to_flat(res)
        pages = sorted({p for s in flat.sets for p in s.location.pages})
        if pages:
            flat.gold_pages = f"{pages[0]}-{pages[-1]}"
        atomic_write_text(
            self.gold_path(doc.doc_id), flat.model_dump_json(indent=1, exclude_none=False)
        )
        return flat

    # -- pages and tokens --------------------------------------------------------
    def _check_page(self, doc: DocMeta, page: int) -> None:
        if not 1 <= page <= doc.n_pages:
            raise NotFoundError(f"page {page} out of range (1..{doc.n_pages})")

    def page_infos(self, doc: DocMeta) -> list[PageInfo]:
        try:
            return self.tokens.pages(doc.sha256)
        except FileNotFoundError as exc:
            raise NotFoundError("token cache missing for document") from exc

    def page_tokens(self, doc: DocMeta, page: int) -> list[Token]:
        self._check_page(doc, page)
        try:
            return self.tokens.page_tokens(doc.sha256, page)
        except FileNotFoundError as exc:
            raise NotFoundError(f"no tokens cached for page {page}") from exc

    def page_png(self, doc: DocMeta, page: int) -> Path:
        """Cached PNG for ``page``; rendered on demand from the raw PDF if missing."""
        self._check_page(doc, page)
        cached = render.png_path(self.pages_dir, doc.sha256, page)
        if cached.is_file():
            return cached
        pdf = (self.raw_dir / doc.source_pdf).resolve()
        if not pdf.is_relative_to(self.raw_dir.resolve()) or not pdf.is_file():
            raise NotFoundError("page image not rendered and source PDF unavailable")
        with self._lock:
            return render.render_pages(pdf, self.pages_dir, doc.sha256, [page])[0]
