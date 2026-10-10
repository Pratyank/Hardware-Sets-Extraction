"""Command line: ``hwsets ingest | pages | extract | eval | serve``."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer

from hwsets.calibration import FIELDS as CAL_FIELDS
from hwsets.calibration import Calibration
from hwsets.calibration import fit as fit_calibration
from hwsets.eval import aggregate, evaluate_document, write_report
from hwsets.export import to_flat
from hwsets.ingest import render
from hwsets.ingest.pdf import extract_document_with_rules
from hwsets.ingest.store import TokenStore, doc_id_for, sha256_file
from hwsets.layout.pages import PageScore, score_page
from hwsets.models import DocumentResult, FlatDocument, Token
from hwsets.pipeline import extract

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
        pages, tokens, rules = extract_document_with_rules(pdf)
        store.write(str(pdf.relative_to(raw_root)), sha, pages, tokens, rules)
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


SPLITS = DATA / "splits.json"
RESULTS = DATA / "results"
GOLD = DATA / "gold"


class Split(StrEnum):
    dev = "dev"
    gold = "gold"
    holdout = "holdout"
    all = "all"


def _splits() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(SPLITS.read_text("utf-8"))
    return data


def _docs_for(split: Split) -> list[str]:
    sp = _splits()
    groups = {
        Split.dev: list(sp["dev"]) + list(sp["negatives"]),
        Split.gold: list(sp["gold"]),
        Split.holdout: list(sp["holdout"]),
    }
    if split is Split.all:
        return [d for g in (Split.dev, Split.gold, Split.holdout) for d in groups[g]]
    return groups[split]


def _guard(doc_id: str, allow_holdout: bool) -> None:
    """Hold-out discipline and gold independence, enforced rather than remembered."""
    sp = _splits()
    if doc_id in sp["holdout"] and not allow_holdout:
        raise typer.BadParameter(f"{doc_id} is a held-out book; pass --allow-holdout (final eval)")
    if doc_id in sp["gold"] and not _gold_final(doc_id):
        raise typer.BadParameter(
            f'{doc_id} is a gold book whose gold file is not final yet (needs "_final": true)'
        )


def _gold_final(doc_id: str) -> bool:
    """Gold labels are drafted independently of the extractor; a book may only be extracted
    once its gold file has been reviewed and marked final."""
    path = GOLD / f"{doc_id}.gold.json"
    if not path.exists():
        return False
    return bool(json.loads(path.read_text("utf-8")).get("_final"))


CALIBRATION = DATA / "calibration.json"


def _load_calibration() -> Calibration | None:
    if not CALIBRATION.exists():
        return None
    return Calibration.model_validate_json(CALIBRATION.read_text("utf-8"))


def _extract_one(doc_id: str, *, calibrated: bool = True) -> DocumentResult:
    store = TokenStore(TOKENS)
    source_pdf, pages_info, tokens = store.load_all(doc_id)
    cal = _load_calibration() if calibrated else None
    return extract(source_pdf, pages_info, tokens, store.load_rules(doc_id), cal)


@app.command()
def calibrate(out: Annotated[Path, typer.Option()] = CALIBRATION) -> None:
    """Fit per-field confidence calibration on the (final) gold books."""
    obs: dict[str, list[tuple[float, bool]]] = {}
    docs = [d for d in _docs_for(Split.gold) if _gold_final(d)]
    for d in docs:
        result = _extract_one(d, calibrated=False)
        gold = FlatDocument.model_validate_json((GOLD / f"{d}.gold.json").read_text("utf-8"))
        de = evaluate_document(result, gold, doc_id=d)
        for se in de.sets:
            if se.pred_idx is None:
                continue
            comps = result.sets[se.pred_idx].components
            for ce in se.components:
                if ce.pred_idx is None:
                    continue
                c = comps[ce.pred_idx]
                for name, ok in ce.field_correct.items():
                    if name in CAL_FIELDS:
                        obs.setdefault(name, []).append((getattr(c, name).confidence, bool(ok)))
    cal = fit_calibration(obs, source=f"gold books: {', '.join(docs)}")
    out.write_text(cal.model_dump_json(indent=1), encoding="utf-8")
    for name, fmap in cal.fields.items():
        pairs = ", ".join(f"{x:.2f}->{y:.2f}" for x, y in zip(fmap.xs, fmap.ys, strict=True))
        typer.echo(f"{name:15} n={fmap.n:5} {pairs}")
    typer.echo(f"wrote {out}")


def _write_result(doc_id: str, result: DocumentResult, flat: bool) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{doc_id}.json"
    path.write_text(result.model_dump_json(indent=1), encoding="utf-8")
    if flat:
        (RESULTS / f"{doc_id}.flat.json").write_text(
            to_flat(result).model_dump_json(indent=1), encoding="utf-8"
        )
    return path


@app.command("extract")
def extract_cmd(
    doc_id: Annotated[str | None, typer.Argument(help="Document id (omit with --split)")] = None,
    split: Annotated[Split | None, typer.Option(help="Extract every book of a split")] = None,
    flat: Annotated[bool, typer.Option(help="Also write the brief's plain JSON shape")] = False,
    allow_holdout: bool = False,
    stdout: Annotated[bool, typer.Option(help="Print the JSON instead of writing it")] = False,
) -> None:
    """Extract hardware sets into ``data/results/<doc_id>.json``."""
    if (doc_id is None) == (split is None):
        raise typer.BadParameter("give exactly one of DOC_ID or --split")
    docs = [doc_id] if doc_id is not None else _docs_for(split or Split.dev)
    for d in docs:
        try:
            _guard(d, allow_holdout)
        except typer.BadParameter as exc:
            typer.echo(f"skip {d}: {exc.message}", err=True)
            continue
        result = _extract_one(d)
        if stdout:
            payload = to_flat(result) if flat else result
            typer.echo(payload.model_dump_json(indent=1))
            continue
        path = _write_result(d, result, flat)
        n_comp = sum(len(s.components) for s in result.sets)
        typer.echo(f"{d}: sets={len(result.sets)} components={n_comp} -> {path}")


@app.command("eval")
def eval_cmd(
    split: Annotated[
        Split, typer.Option(help="Books to evaluate (must have gold files)")
    ] = Split.gold,
    out: Annotated[Path, typer.Option(help="Report directory")] = Path("eval"),
    allow_holdout: bool = False,
    ui_base: str = "http://localhost:8000",
) -> None:
    """Extract and score every book that has a gold file; writes report.md / report.json."""
    docs = [d for d in _docs_for(split) if _gold_final(d)]
    if not docs:
        raise typer.BadParameter(f"no gold files for split {split.value}")
    evals = []
    for d in docs:
        _guard(d, allow_holdout)
        result = _extract_one(d)
        _write_result(d, result, flat=False)
        gold = FlatDocument.model_validate_json((GOLD / f"{d}.gold.json").read_text("utf-8"))
        de = evaluate_document(result, gold, doc_id=d)
        evals.append(de)
        m = de.metrics
        typer.echo(
            f"{d[:48]:48} set_R={m.set_recall:.3f} set_P={m.set_precision:.3f} "
            f"fully={m.set_fully_correct:.3f}"
        )
    summary = aggregate(evals)
    write_report(summary, evals, out, ui_base=ui_base)
    typer.echo(f"report: {out / 'report.md'}")


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


@app.command("tokens")
def tokens_cmd(
    doc_id: str,
    page: int,
    grep: Annotated[str | None, typer.Option(help="Only lines containing this text")] = None,
) -> None:
    """Print a page's raw ingest tokens grouped by PyMuPDF line, with bboxes (PDF points).

    Raw ingest output only (no extraction), so it is safe to use while drafting gold labels.
    Struck-through tokens are marked with ``~``.
    """
    store = TokenStore(TOKENS)
    sha = store.resolve(doc_id)["sha256"]
    rows: dict[tuple[int, int], list[Token]] = {}
    for t in store.page_tokens(sha, page):
        rows.setdefault((t.block, t.line), []).append(t)
    for toks in sorted(rows.values(), key=lambda ts: (round(ts[0].bbox[1]), ts[0].bbox[0])):
        text = " ".join(("~" if t.strike else "") + t.text for t in toks)
        if grep and grep.lower() not in text.lower():
            continue
        x0 = min(t.bbox[0] for t in toks)
        y0 = min(t.bbox[1] for t in toks)
        x1 = max(t.bbox[2] for t in toks)
        y1 = max(t.bbox[3] for t in toks)
        typer.echo(f"{toks[0].id:>10} [{x0:6.1f},{y0:6.1f},{x1:6.1f},{y1:6.1f}] {text}")


@app.command("gold-check")
def gold_check(path: Path) -> None:
    """Validate a gold file against the flat schema and print a summary."""
    doc = FlatDocument.model_validate_json(path.read_text("utf-8"))
    n_comp = sum(len(s.components) for s in doc.sets)
    not_used = sum(1 for s in doc.sets if s.status == "not_used")
    nums = [s.set_number for s in doc.sets]
    dups = sorted({n for n in nums if nums.count(n) > 1})
    typer.echo(f"OK {path}: sets={len(doc.sets)} components={n_comp} not_used={not_used}")
    if dups:
        typer.echo(f"  duplicate set numbers: {dups}")


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
