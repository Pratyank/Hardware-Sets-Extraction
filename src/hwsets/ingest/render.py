"""Page -> PNG rendering for the review UI and gold drafting.

PNGs are rendered at ``DPI`` from the page *as displayed*, matching token bboxes. A point
``(x, y)`` in PDF points maps to pixel ``(x * scale, y * scale)`` with ``scale = DPI / 72``.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

import pymupdf

DPI = 150
SCALE = DPI / 72.0


def png_path(pages_root: Path, sha256: str, page: int) -> Path:
    return pages_root / sha256[:16] / f"p{page:04d}.png"


def points_to_pixels(bbox: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    return (round(x0 * SCALE), round(y0 * SCALE), round(x1 * SCALE), round(y1 * SCALE))


def pixels_to_points(px: tuple[int, int, int, int]) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = px
    return (x0 / SCALE, y0 / SCALE, x1 / SCALE, y1 / SCALE)


def render_pages(
    pdf: Path, pages_root: Path, sha256: str, pages: Iterable[int], *, force: bool = False
) -> list[Path]:
    """Render 1-based ``pages`` to PNG (skipping ones already cached). Returns their paths."""
    out: list[Path] = []
    with pymupdf.open(pdf) as doc:
        for n in pages:
            dst = png_path(pages_root, sha256, n)
            if dst.exists() and not force:
                out.append(dst)
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            pix = doc[n - 1].get_pixmap(dpi=DPI, alpha=False)
            tmp = dst.with_suffix(".tmp.png")
            pix.save(tmp)
            os.replace(tmp, dst)
            out.append(dst)
    return out
