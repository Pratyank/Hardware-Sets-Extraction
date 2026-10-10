"""Command line: ``hwsets ingest | pages | extract | eval | serve``."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from hwsets.ingest import render
from hwsets.ingest.pdf import extract_document
from hwsets.ingest.store import TokenStore, doc_id_for, sha256_file
from hwsets.layout.pages import PageScore, score_page

app = typer.Typer(add_completion=False, no_args_is_help=True)
log = logging.getLogger("hwsets")

DATA = Path("data")
RAW = DATA / "raw"
TOKENS = DATA / "tokens"
PAGES = DATA / "pages"


class RenderMode(StrEnum):
    candidates = "candidates"
    all = "all"
    none = "none"


def _score_doc(store: TokenStore, sha: str) -> list[PageScore]:
    return [score_page(p.page, store.page_tokens(sha, p.page)) for p in store.pages(sha)]


def _ingest_one(
    pdf: Path,
    *,
    raw_root: Path,
    tokens_root: Path,
    pages_root: Path,
    mode: RenderMode,
    force: bool,
) -> tuple[str, int, list[int], bool]:
    """Worker: tokenize (cached by sha256), score pages, render. Runs in a subprocess."""
    store = TokenStore(tokens_root)
    sha = sha256_file(pdf)
    doc_id = doc_id_for(pdf, raw_root)
    cached = store.is_cached(sha) and not force
    if not cached:
        pages, tokens = extract_document(pdf)
        store.write(str(pdf.relative_to(raw_root)), sha, pages, tokens)
    infos = store.pages(sha)
    candidates = [s.page for s in _score_doc(store, sha) if s.is_candidate]
    to_render = {
        RenderMode.candidates: candidates,
        RenderMode.all: [p.page for p in infos],
        RenderMode.none: [],
    }[mode]
    render.render_pages(pdf, pages_root, sha, to_render)
    return doc_id, len(infos), candidates, cached


@app.command()
def ingest(
    path: Annotated[
        Path, typer.Argument(help="PDF file or directory (searched recursively)")
    ] = RAW,
    raw_root: Annotated[Path, typer.Option(help="Root used to derive document ids")] = RAW,
    render_mode: Annotated[RenderMode, typer.Option("--render")] = RenderMode.candidates,
    workers: Annotated[int, typer.Option(min=1)] = 4,
    force: bool = False,
) -> None:
    """Tokenize PDFs into ``data/tokens`` and render hardware-candidate pages to PNG."""
    pdfs = sorted(path.rglob("*.pdf")) if path.is_dir() else [path]
    if not pdfs:
        raise typer.BadParameter(f"no PDFs under {path}")
    store = TokenStore(TOKENS)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _ingest_one,
                pdf,
                raw_root=raw_root,
                tokens_root=TOKENS,
                pages_root=PAGES,
                mode=render_mode,
                force=force,
            ): pdf
            for pdf in pdfs
        }
        for fut in as_completed(futures):
            pdf = futures[fut]
            try:
                doc_id, n_pages, cands, cached = fut.result()
            except Exception as exc:  # report and continue with the other books
                typer.echo(f"FAIL {pdf}: {exc!r}", err=True)
                continue
            sha = sha256_file(pdf)
            store.register(doc_id, str(pdf.relative_to(raw_root)), sha, n_pages)
            tag = "cached" if cached else "ingested"
            typer.echo(f"{tag:8} {doc_id}  pages={n_pages}  hw_candidates={_ranges(cands)}")


@app.command()
def pages(
    doc_id: str,
    top: Annotated[int, typer.Option(help="Show the N best-scoring pages")] = 15,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show hardware-page scores for one ingested document."""
    store = TokenStore(TOKENS)
    sha = store.resolve(doc_id)["sha256"]
    scores = _score_doc(store, sha)
    if as_json:
        typer.echo(json.dumps([_asdict(s) for s in scores]))
        return
    for s in sorted(scores, key=lambda s: -s.score)[:top]:
        flag = "*" if s.is_candidate else " "
        typer.echo(
            f"{flag} p{s.page:<5} score={s.score:<6} kw={s.keyword_hits:<3} "
            f"mfr={s.mfr_hits:<3} fin={s.finish_hits:<3} tokens={s.n_tokens}"
        )


@app.command("render")
def render_cmd(
    doc_id: str,
    page_spec: Annotated[str, typer.Argument(help="Pages, e.g. '7-12,15'")],
    raw_root: Annotated[Path, typer.Option(help="Root the document id is relative to")] = RAW,
    text: Annotated[bool, typer.Option(help="Also print each page's token text")] = False,
) -> None:
    """Render pages of an ingested document to PNG and print their paths."""
    store = TokenStore(TOKENS)
    meta = store.resolve(doc_id)
    n_pages = int(meta["n_pages"])
    wanted = _parse_pages(page_spec, n_pages)
    for path, n in zip(
        render.render_pages(raw_root / meta["source_pdf"], PAGES, meta["sha256"], wanted),
        wanted,
        strict=True,
    ):
        typer.echo(f"p{n}: {path}")
        if text:
            typer.echo(" ".join(t.text for t in store.page_tokens(meta["sha256"], n)))


def _parse_pages(spec: str, n_pages: int) -> list[int]:
    out: set[int] = set()
    for part in spec.split(","):
        lo, _, hi = part.strip().partition("-")
        a, b = int(lo), int(hi or lo)
        if not 1 <= a <= b <= n_pages:
            raise typer.BadParameter(f"page range {part!r} outside 1..{n_pages}")
        out.update(range(a, b + 1))
    return sorted(out)


def _asdict(s: PageScore) -> dict[str, object]:
    return {f: getattr(s, f) for f in s.__slots__}


def _ranges(pages: list[int]) -> str:
    if not pages:
        return "-"
    out: list[str] = []
    start = prev = pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
            continue
        out.append(f"{start}" if start == prev else f"{start}-{prev}")
        start = prev = p
    out.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ",".join(out)


@app.callback()
def _main(verbose: Annotated[bool, typer.Option("-v")] = False) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.WARNING)


if __name__ == "__main__":
    app()
