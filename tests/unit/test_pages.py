"""Hardware-page scoring is a pure function of tokens."""

from __future__ import annotations

from hwsets.columns import lexicon
from hwsets.layout.pages import score_page
from hwsets.models import Token


def _toks(text: str, page: int = 1) -> list[Token]:
    return [
        Token(
            id=f"p{page}_w{i}",
            page=page,
            text=w,
            bbox=(i * 10.0, 0, i * 10.0 + 8, 10),
            font_size=10,
            bold=False,
            block=0,
            line=0,
        )
        for i, w in enumerate(text.split())
    ]


HW = """HARDWARE SET NO. 01 ENTRANCE 3 EA HINGE 5BB1 4.5 X 4.5 652 IVE
1 EA LOCKSET ND50PD RHO 626 SCH 1 EA CLOSER 4040XP 689 LCN 1 EA STOP WS406 630 IVE
HARDWARE SET NO. 02 3 EA HINGE 5BB1 652 IVE 1 EA PASSAGE ND10S 626 SCH"""
PROSE = """PART 1 GENERAL 1.01 SECTION INCLUDES A. Hollow metal doors and frames. B. Submittals
shall comply with Division 01 requirements for product data and shop drawings."""


def test_hardware_page_is_candidate() -> None:
    s = score_page(1, _toks(HW))
    assert s.is_candidate
    assert s.keyword_hits >= 2 and s.mfr_hits >= 4 and s.finish_hits >= 4


def test_prose_page_is_not_candidate() -> None:
    assert not score_page(1, _toks(PROSE)).is_candidate


def test_empty_page() -> None:
    assert score_page(3, []).score == 0.0


def test_collisions_carry_no_evidence() -> None:
    for code in ("PE", "NO", "AL", "SP"):
        assert code in lexicon.COLLISIONS
        assert not lexicon.is_mfr_code(code)
        assert not lexicon.is_finish_code(code)
    assert lexicon.mfr_name("PE") == "Pemko"
    assert lexicon.is_mfr_code("ive,") and lexicon.is_finish_code("US26D")
    assert lexicon.finish_canonical("us26d") == "626"
