"""Same-page lookup-code resolution (bonus)."""

from __future__ import annotations

from helpers.synth import make_page, run
from hwsets.components.lookup import find_lookup_legend

LEGEND = [
    "A - HINGES 5BB1 4.5 X 4.5 NRP 652 IVE",
    "B - LOCKSET ND50PD RHO 626 SCH",
]


def test_legend_block_needs_two_entries() -> None:
    page = make_page(1, ["A - A SINGLE SENTENCE THAT IS NOT A LEGEND", "3|EA|HINGE|5BB1|652|IVE"])
    assert find_lookup_legend(page.lines(), page.toks) == {}


def test_legend_entries_cite_their_tokens() -> None:
    page = make_page(1, LEGEND)
    legend = find_lookup_legend(page.lines(), page.toks)
    assert set(legend) == {"A", "B"}
    assert legend["B"].text == "LOCKSET ND50PD RHO 626 SCH"
    assert " ".join(page.toks[i].text for i in legend["B"].token_ids) == legend["B"].text


def test_component_key_resolves_from_same_page_legend() -> None:
    rows = [
        ("HARDWARE SET NO. 1", {"bold": True}),
        "3|EA|HINGE|A|652|IVE",
        "1|EA|LOCKSET|B|626|SCH",
        "1|EA|CLOSER|4040XP|689|LCN",
        ("HARDWARE SET NO. 2", {"bold": True}),
        "3|EA|HINGE|5BB1|652|IVE",
        "1|EA|CLOSER|4040XP|689|LCN",
        "1|EA|STOP|WS406|630|IVE",
        *LEGEND,
    ]
    result = run([make_page(1, rows)])
    comps = result.sets[0].components
    assert comps[0].resolved_from_code == "HINGES 5BB1 4.5 X 4.5 NRP 652 IVE"
    assert comps[0].resolved_from_code_tokens
    assert comps[1].resolved_from_code == "LOCKSET ND50PD RHO 626 SCH"
    assert comps[2].resolved_from_code is None  # a real catalog number is not a key
