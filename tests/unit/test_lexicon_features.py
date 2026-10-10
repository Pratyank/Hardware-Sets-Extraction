"""columns.lexicon and columns.features: evidence, never decisions."""

from __future__ import annotations

import pytest

from hwsets.columns.features import (
    column_features,
    is_catalog_token,
    is_catalog_value,
    is_mfr_value,
    is_wordy,
)
from hwsets.columns.lexicon import (
    COLLISIONS,
    finish_canonical,
    is_finish_code,
    is_finish_value,
    is_mfr_code,
    mfr_name,
    norm_code,
    unit_code,
)


@pytest.mark.parametrize("code", ["PE", "NO", "AL", "SP", "BL"])
def test_collision_codes_are_evidence_for_neither_role(code: str) -> None:
    assert code in COLLISIONS
    assert not is_mfr_code(code)
    assert not is_finish_code(code)


def test_lexicon_lookups_normalize_case_and_punctuation() -> None:
    assert is_mfr_code("ive") and is_mfr_code("SCH.") and is_mfr_code("Von Duprin")
    assert mfr_name("PE") == "Pemko"  # the name lookup still knows collisions
    assert mfr_name("lcn,") == "LCN"
    assert is_finish_code("us26d") and is_finish_code("626")
    assert norm_code("us26d,") == "US26D"
    assert finish_canonical("US26D") == "626"
    assert finish_canonical("630") == "630"


@pytest.mark.parametrize(
    ("text", "unit"),
    [("EA", "EA"), ("Ea.", "EA"), ("each", "EA"), ("Pair", "PR"), ("PRS", "PR"), ("SET", "SET")],
)
def test_unit_code(text: str, unit: str) -> None:
    assert unit_code(text) == unit


def test_unit_code_rejects_non_units() -> None:
    assert unit_code("HINGE") is None
    assert unit_code("3") is None


@pytest.mark.parametrize("text", ["626", "630-316", "626/622", "US26D", "613 (OIL RUBBED BRONZE)"])
def test_finish_values(text: str) -> None:
    assert is_finish_value(text)


@pytest.mark.parametrize("text", ["IVE", "4040XP", "", "316", "PE"])
def test_non_finish_values(text: str) -> None:
    assert not is_finish_value(text)


def test_catalog_tokens() -> None:
    assert is_catalog_token("5BB1") and is_catalog_token("4040XP") and is_catalog_token("4.5")
    assert not is_catalog_token("2")  # a bare small number is a count
    assert not is_catalog_token("HINGE")
    assert is_catalog_value("2 CB1 HW")  # a leading count shares the cell
    assert not is_catalog_value("3 HINGES")


def test_four_digit_model_number_is_catalog_not_a_count() -> None:
    assert is_catalog_value("8400 10 X 34")


def test_wordiness() -> None:
    assert is_wordy("CONTINUOUS HINGE")
    assert not is_wordy("5BB1 4.5 X 4.5")


def test_mfr_value_uses_legend_for_unknown_codes() -> None:
    assert not is_mfr_value("ZZX")
    assert is_mfr_value("ZZX", legend=frozenset({"ZZX"}))
    assert not is_mfr_value("a long run of words")


def test_column_features_ignore_collisions_for_role_shares() -> None:
    f = column_features(["SCH", "LCN", "IVE", "PE", "PE"], n_rows=5)
    assert f.mfr == 1.0  # 3 of the 3 decisive values
    assert f.finish == 0.0
    assert f.collisions == pytest.approx(0.4)
    assert f.fill == 1.0


def test_column_features_count_legend_codes_as_decisive() -> None:
    f = column_features(["PE", "PE", "IVE"], n_rows=3, legend=frozenset({"PE"}))
    assert f.collisions == 0.0
    assert f.mfr == 1.0


def test_large_numbers_are_weak_quantity_evidence() -> None:
    counts = column_features(["3", "1", "1", "2"], n_rows=4)
    finishes = column_features(["313", "313", "626", "313"], n_rows=4)
    assert counts.qty == 1.0
    assert finishes.qty < 0.5
    assert finishes.finish == 1.0


def test_empty_column() -> None:
    f = column_features(["", "  "], n_rows=4)
    assert f.fill == 0.0 and f.mfr == 0.0 and f.qty == 0.0
