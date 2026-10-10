"""Positional template fallback for free-flowing list formats (columns/template.py)."""

from __future__ import annotations

from helpers.synth import make_page, run
from hwsets.columns.template import apply_template, infer_template

ROWS = [
    ("HARDWARE SET NO. 1", {"bold": True}),
    "3 EA HINGE 5BB1 4.5 X 4.5 652 IVE",
    "1 EA LOCKSET ND50PD RHO 626 SCH",
    "1 EA CLOSER 4040XP 689 LCN",
    "1 EA THRESHOLD 171A AL PE",  # collision codes: resolved by the template's slots
    ("HARDWARE SET NO. 2", {"bold": True}),
    "3 EA HINGE 5BB1 4.5 X 4.5 652 IVE",
    "1 EA PASSAGE SET ND10S RHO 626 SCH",
    "1 EA WALL STOP WS406 630 IVE",
]


def test_infers_finish_then_manufacturer_order() -> None:
    page = make_page(1, ROWS)
    template = infer_template(page.lines(), page.toks)
    assert template is not None
    assert template.trailing == ("finish", "mfr")
    assert template.support >= 3


def test_reversed_order_is_inferred_from_the_document() -> None:
    rows = [r if isinstance(r, tuple) else _swap_last_two(r) for r in ROWS]
    page = make_page(1, rows)
    template = infer_template(page.lines(), page.toks)
    assert template is not None and template.trailing == ("mfr", "finish")


def _swap_last_two(row: str) -> str:
    words = row.split()
    return " ".join([*words[:-2], words[-1], words[-2]])


def test_apply_assigns_every_token_a_role() -> None:
    page = make_page(1, ROWS)
    template = infer_template(page.lines(), page.toks)
    assert template is not None
    line = next(ln for ln in page.lines() if ln.text.startswith("1 EA LOCKSET"))
    roles, fit = apply_template(template, line, page.toks)
    by_text = {page.toks[i].text: r for i, r in roles.items()}
    assert fit
    assert by_text["1"] == "qty" and by_text["EA"] == "unit"
    assert by_text["LOCKSET"] == "description"
    assert by_text["ND50PD"] == "catalog" and by_text["RHO"] == "catalog"
    assert by_text["626"] == "finish" and by_text["SCH"] == "mfr"


def test_too_little_support_gives_no_template() -> None:
    page = make_page(1, [("HARDWARE SET NO. 1", {"bold": True}), "1 EA CLOSER 4040XP 689 LCN"])
    assert infer_template(page.lines(), page.toks) is None


def test_pipeline_uses_the_template_for_unaligned_lists() -> None:
    result = run([make_page(1, ROWS)])
    assert [s.set_number.value for s in result.sets] == ["1", "2"]
    first = result.sets[0].components
    assert [(c.mfr.value, c.finish.value) for c in first] == [
        ("IVE", "652"),
        ("SCH", "626"),
        ("LCN", "689"),
        ("PE", "AL"),  # the collision code PE sits in the manufacturer slot -> Pemko
    ]
    assert first[3].mfr_resolved == "Pemko"
    assert first[0].qty.value == 3 and first[0].qty_unit == "EA"
    assert any("template" in k for k in result.column_roles)
