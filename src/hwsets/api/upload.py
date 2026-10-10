"""PDF upload: validate, store, ingest and extract one book for the review UI.

The request handler (``server.py``) streams the upload into ``raw/uploads/`` with
:func:`save_upload` and then runs :func:`ingest_and_extract` in a worker thread. The heavy path
is the same one the CLI uses: ``extract_document_with_rules`` -> ``TokenStore.write/register``
-> ``pipeline.extract`` -> ``results/<doc_id>.json``.

Nothing from the client reaches the filesystem unvalidated: the stored file is named by its
content hash and the document id is a slug of the original file *basename*.
"""

from __future__ import annotations

import hashlib
import ntpath
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from hwsets.api.storage import atomic_write_text
from hwsets.ingest import render
from hwsets.ingest.pdf import extract_document_with_rules
from hwsets.ingest.store import TokenStore
from hwsets.layout.pages import score_page
from hwsets.pipeline import extract

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
PDF_MAGIC = b"%PDF-"
UPLOAD_PREFIX = "uploads"
ALLOWED_CONTENT_TYPES = frozenset(
    {"application/pdf", "application/x-pdf", "application/octet-stream", ""}
)
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_MAX_SLUG = 60
_CHUNK = 1 << 20
_MAX_RENDER_PAGES = 60

# Serialises read-modify-write of tokens/index.json and result writes across uploads.
_REGISTRY_LOCK = threading.Lock()


class UploadError(Exception):
    """Rejected upload; ``status_code`` is the HTTP status to return."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class SavedUpload:
    path: Path  # raw/uploads/<sha16>.pdf
    sha256: str
    n_bytes: int


@dataclass(frozen=True)
class UploadResult:
    doc_id: str
    n_sets: int
    n_pages: int
    hardware_pages: list[int]


def slugify_filename(filename: str | None) -> str:
    """Filesystem-safe slug of the file's basename, without directories or extension."""
    name = ntpath.basename((filename or "").replace("/", "\\"))  # strips both separators
    stem = name[:-4] if name.lower().endswith(".pdf") else name
    slug = _SLUG_RE.sub("-", stem.lower()).strip("-")[:_MAX_SLUG].strip("-")
    return slug or "document"


def check_content_type(content_type: str | None) -> None:
    base = (content_type or "").split(";", 1)[0].strip().lower()
    if base not in ALLOWED_CONTENT_TYPES:
        raise UploadError(415, f"expected a PDF upload, got content type {base!r}")


def save_upload(src: BinaryIO, uploads_dir: Path, max_bytes: int = MAX_UPLOAD_BYTES) -> SavedUpload:
    """Copy ``src`` to ``uploads_dir/<sha16>.pdf``, enforcing the size limit and PDF magic."""
    uploads_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=uploads_dir, prefix=".upload-", suffix=".tmp")
    tmp = Path(tmp_name)
    h = hashlib.sha256()
    n = 0
    try:
        with os.fdopen(fd, "wb") as out:
            head = b""
            while chunk := src.read(_CHUNK):
                n += len(chunk)
                if n > max_bytes:
                    raise UploadError(413, f"file exceeds the {max_bytes // (1 << 20)} MB limit")
                if len(head) < len(PDF_MAGIC):
                    head += chunk[: len(PDF_MAGIC)]
                h.update(chunk)
                out.write(chunk)
        if n == 0:
            raise UploadError(422, "empty file")
        if not head.startswith(PDF_MAGIC):
            raise UploadError(415, "file is not a PDF (missing %PDF header)")
        sha = h.hexdigest()
        dst = uploads_dir / f"{sha[:16]}.pdf"
        os.replace(tmp, dst)
        return SavedUpload(path=dst, sha256=sha, n_bytes=n)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _doc_id(store: TokenStore, slug: str, sha256: str) -> str:
    """``uploads--<slug>``; a different PDF under the same name gets a hash suffix."""
    doc_id = f"{UPLOAD_PREFIX}--{slug}"
    existing = store.index().get(doc_id)
    if existing is not None and existing.get("sha256") != sha256:
        doc_id = f"{doc_id}-{sha256[:8]}"
    return doc_id


def ingest_and_extract(data_dir: Path, saved: SavedUpload, filename: str | None) -> UploadResult:
    """Tokenize (cached by sha256), register, extract and write ``results/<doc_id>.json``."""
    raw_dir = data_dir / "raw"
    store = TokenStore(data_dir / "tokens")
    source_pdf = saved.path.relative_to(raw_dir).as_posix()
    if not store.is_cached(saved.sha256):
        try:
            pages, tokens, rules = extract_document_with_rules(saved.path)
        except (RuntimeError, ValueError) as exc:  # pymupdf.FileDataError is a RuntimeError
            raise UploadError(422, f"could not read PDF: {exc}") from exc
        if not pages:
            raise UploadError(422, "PDF has no pages")
        store.write(source_pdf, saved.sha256, pages, tokens, rules)
    pages = store.pages(saved.sha256)
    tokens_by_page = {p.page: store.page_tokens(saved.sha256, p.page) for p in pages}
    rules_by_page = {p.page: store.page_rules(saved.sha256, p.page) for p in pages}
    result = extract(source_pdf, pages, tokens_by_page, rules_by_page)

    candidates = [p.page for p in pages if score_page(p.page, tokens_by_page[p.page]).is_candidate]
    to_render = sorted(set(result.hardware_pages) | set(candidates))[:_MAX_RENDER_PAGES]
    render.render_pages(saved.path, data_dir / "pages", saved.sha256, to_render)

    slug = slugify_filename(filename)
    with _REGISTRY_LOCK:
        doc_id = _doc_id(store, slug, saved.sha256)
        atomic_write_text(data_dir / "results" / f"{doc_id}.json", result.model_dump_json(indent=1))
        store.register(doc_id, source_pdf, saved.sha256, len(pages))
    return UploadResult(
        doc_id=doc_id,
        n_sets=len(result.sets),
        n_pages=len(pages),
        hardware_pages=list(result.hardware_pages),
    )
