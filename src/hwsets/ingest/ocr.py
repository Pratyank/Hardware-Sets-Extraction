"""OCR fallback for pages without a text layer.

Runs ``ocrmypdf`` (Tesseract) on a single page and returns the OCR'd one-page PDF, from which
``pdf.py`` re-extracts words. OCR is optional at runtime: if ``ocrmypdf`` is not installed
the page is skipped with a (one-time) warning and the caller keeps the native tokens.
"""

from __future__ import annotations

import functools
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf

log = logging.getLogger(__name__)
_OCR_TIMEOUT_S = 180


def available() -> bool:
    return shutil.which("ocrmypdf") is not None


@functools.cache
def _warn_missing() -> None:
    log.warning("ocrmypdf not installed; image-only pages will have no tokens")


def ocr_page_pdf(pdf_path: Path, page_index: int) -> bytes | None:
    """OCR page ``page_index`` (0-based). Returns a one-page PDF with a text layer, or None."""
    if not available():
        _warn_missing()
        return None
    with tempfile.TemporaryDirectory(prefix="hwsets-ocr-") as tmp:
        src = Path(tmp) / "page.pdf"
        dst = Path(tmp) / "page.ocr.pdf"
        with pymupdf.open(pdf_path) as doc, pymupdf.open() as one:
            one.insert_pdf(doc, from_page=page_index, to_page=page_index)
            one.save(src)
        try:
            subprocess.run(
                ["ocrmypdf", "--force-ocr", "--quiet", str(src), str(dst)],
                check=True,
                timeout=_OCR_TIMEOUT_S,
                capture_output=True,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            log.warning("OCR failed for %s page %d: %s", pdf_path.name, page_index + 1, exc)
            return None
        return dst.read_bytes()
