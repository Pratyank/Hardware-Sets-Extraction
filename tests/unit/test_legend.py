"""columns.legend: manufacturer / finish legends printed in the book."""

from __future__ import annotations

import pytest

from helpers.synth import make_page
from hwsets.columns.legend import Legend, find_legend


def _legend(*rows: str) -> tuple[Legend, dict[str, str]]:
    sp = make_page(1, list(rows))
    return find_legend(sp.lines(), sp.toks), {t.id: t.text for t in sp.tokens}


@pytest.mark.parametrize(
    ("row", "code", "name"),
    [
        ("PE - Pemko", "PE", "Pemko"),
        ("IVE  H.B. Ives", "IVE", "H.B. Ives"),
        ("2. RO - Rockwood", "RO", "Rockwood"),
        ("SCH = Schlage Lock Company", "SCH", "Schlage Lock Company"),
    ],
)
def test_single_manufacturer_entries(row: str, code: str, name: str) -> None:
    legend, text = _legend(row)
    assert set(legend.mfr) == {code}
    entry = legend.mfr[code]
    assert (entry.name, entry.kind) == (name, "mfr")
    assert code in [text[i] for i in entry.token_ids]  # cites the printed code
    assert legend.finish == {}


def test_legend_promotes_collision_codes() -> None:
    legend, _ = _legend("PE - Pemko", "NO - Norton")
    assert legend.mfr_codes == frozenset({"PE", "NO"})


def test_finish_entry_with_finish_words() -> None:
    legend, _ = _legend("10BE Dark Oxidized Satin Bronze \u2013 Equivalent")
    assert set(legend.finish) == {"10BE"}
    assert legend.finish["10BE"].name.startswith("Dark Oxidized Satin Bronze")
    assert legend.finish["10BE"].kind == "finish"
    assert legend.mfr == {}


def test_inline_name_with_code_in_parentheses() -> None:
    legend, text = _legend(
        "Hinges shall be as manufactured by McKinney (MK) or approved equal as listed herein"
    )
    assert set(legend.mfr) == {"MK"}
    assert legend.mfr["MK"].name == "McKinney"
    assert [text[i] for i in legend.mfr["MK"].token_ids] == ["(MK)"]


def test_block_majority_admits_unknown_names() -> None:
    legend, _ = _legend("IVE - Ives", "SCH - Schlage", "ZZX - Acme Widgets")
    assert set(legend.mfr) == {"IVE", "SCH", "ZZX"}


def test_isolated_unknown_name_is_not_a_legend_entry() -> None:
    legend, _ = _legend("ZZX - Acme Widgets")
    assert legend.mfr == {} and legend.finish == {}


def test_finish_block() -> None:
    legend, _ = _legend("626 Satin Chromium", "630 Satin Stainless Steel", "313 Dark Bronze")
    assert legend.finish_codes == frozenset({"626", "630", "313"})


def test_column_header_rows_and_component_rows_are_not_legends() -> None:
    legend, _ = _legend("QTY DESCRIPTION CATALOG FINISH MFR", "3 EA HINGE 5BB1 652 IVE")
    assert legend.mfr == {} and legend.finish == {}
