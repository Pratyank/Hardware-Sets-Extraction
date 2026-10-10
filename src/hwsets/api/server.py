"""FastAPI review server: JSON API under ``/api`` plus the static review UI at ``/``.

Run with ``uvicorn hwsets.api.server:app`` (data directory from ``HWSETS_DATA``, default
``data``) or build an app for any directory with :func:`create_app`.
"""

from __future__ import annotations

import os
from pathlib import Path
from statistics import fmean

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.datastructures import UploadFile

from hwsets.api import upload
from hwsets.api.storage import DataStore, DocMeta, InvalidCorrectionError, NotFoundError
from hwsets.ingest import render
from hwsets.models import DocumentResult, FlatDocument, HardwareSet, PageInfo, Token

STATIC_DIR = Path(__file__).parent / "static"
PNG_CACHE_CONTROL = "public, max-age=86400"


class DocSummary(BaseModel):
    doc_id: str
    source_pdf: str
    n_sets: int
    n_pages: int
    has_corrections: bool
    mean_confidence: float | None


class PagesResponse(BaseModel):
    dpi: int
    scale: float  # rendered PNG pixels per PDF point
    pages: list[PageInfo]


class SaveResponse(BaseModel):
    set_idx: int
    set: HardwareSet


class UploadResponse(BaseModel):
    doc_id: str
    n_sets: int
    n_pages: int
    hardware_pages: list[int]


# Multipart framing around the file part; Content-Length above limit + slack is refused early.
_MULTIPART_SLACK = 64 * 1024


def create_app(data_dir: Path, *, max_upload_bytes: int = upload.MAX_UPLOAD_BYTES) -> FastAPI:
    store = DataStore(data_dir)
    app = FastAPI(title="hwsets review", version="0.1.0")

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InvalidCorrectionError)
    async def _invalid(_: Request, exc: InvalidCorrectionError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(upload.UploadError)
    async def _upload_error(_: Request, exc: upload.UploadError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    def _doc(doc_id: str) -> DocMeta:
        return store.doc(doc_id)

    @app.get("/api/docs/list", response_model=list[DocSummary])
    def list_docs() -> list[DocSummary]:
        out: list[DocSummary] = []
        for doc_id in store.doc_ids():
            try:
                doc = store.doc(doc_id)
                res = store.result(doc)
            except (NotFoundError, ValueError):
                continue  # registered but not extracted (or unreadable): not reviewable
            confs = [s.confidence for s in res.sets]
            out.append(
                DocSummary(
                    doc_id=doc_id,
                    source_pdf=doc.source_pdf,
                    n_sets=len(res.sets),
                    n_pages=doc.n_pages,
                    has_corrections=bool(store.corrections(doc)),
                    mean_confidence=round(fmean(confs), 4) if confs else None,
                )
            )
        return out

    @app.post("/api/docs/upload", response_model=UploadResponse)
    async def upload_doc(request: Request) -> UploadResponse:
        """Multipart field ``file``: a PDF up to the size limit. Ingests and extracts it."""
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > max_upload_bytes + _MULTIPART_SLACK:
            raise upload.UploadError(413, "upload exceeds the size limit")
        ctype = request.headers.get("content-type", "")
        if not ctype.lower().startswith("multipart/form-data"):
            raise upload.UploadError(415, "expected multipart/form-data with a 'file' field")
        form = await request.form(max_files=1, max_fields=4)
        try:
            item = form.get("file")
            if not isinstance(item, UploadFile):
                raise upload.UploadError(422, "missing 'file' field")
            upload.check_content_type(item.content_type)
            saved = await run_in_threadpool(
                upload.save_upload,
                item.file,
                store.raw_dir / upload.UPLOAD_PREFIX,
                max_upload_bytes,
            )
            res = await run_in_threadpool(upload.ingest_and_extract, data_dir, saved, item.filename)
        finally:
            await form.close()
        return UploadResponse(
            doc_id=res.doc_id,
            n_sets=res.n_sets,
            n_pages=res.n_pages,
            hardware_pages=res.hardware_pages,
        )

    @app.get("/api/docs/{doc_id}/result", response_model=DocumentResult)
    def get_result(doc_id: str) -> DocumentResult:
        return store.result(_doc(doc_id))

    @app.get("/api/docs/{doc_id}/pages", response_model=PagesResponse)
    def get_pages(doc_id: str) -> PagesResponse:
        doc = _doc(doc_id)
        return PagesResponse(dpi=render.DPI, scale=render.SCALE, pages=store.page_infos(doc))

    @app.get("/api/docs/{doc_id}/page/{n}.png", response_class=FileResponse)
    def get_page_png(doc_id: str, n: int) -> FileResponse:
        path = store.page_png(_doc(doc_id), n)
        return FileResponse(
            path, media_type="image/png", headers={"Cache-Control": PNG_CACHE_CONTROL}
        )

    @app.get("/api/docs/{doc_id}/tokens", response_model=list[Token])
    def get_tokens(doc_id: str, page: int = Query(..., ge=1)) -> list[Token]:
        return store.page_tokens(_doc(doc_id), page)

    @app.put("/api/docs/{doc_id}/sets/{set_idx}", response_model=SaveResponse)
    def put_set(doc_id: str, set_idx: int, body: HardwareSet) -> SaveResponse:
        saved = store.save_correction(_doc(doc_id), set_idx, body)
        return SaveResponse(set_idx=set_idx, set=saved)

    @app.delete("/api/docs/{doc_id}/sets/{set_idx}", response_model=SaveResponse)
    def revert_set(doc_id: str, set_idx: int) -> SaveResponse:
        original = store.delete_correction(_doc(doc_id), set_idx)
        return SaveResponse(set_idx=set_idx, set=original)

    @app.post("/api/docs/{doc_id}/export-gold", response_model=FlatDocument)
    def export_gold(doc_id: str) -> FlatDocument:
        return store.export_gold(_doc(doc_id))

    @app.api_route("/api/{rest:path}", methods=["GET", "PUT", "POST", "DELETE"])
    def api_fallback(rest: str) -> None:
        raise HTTPException(status_code=404, detail="not found")

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
    return app


app = create_app(Path(os.environ.get("HWSETS_DATA", "data")))
