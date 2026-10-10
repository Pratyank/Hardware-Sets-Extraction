"""columns.assign: column roles decided over the whole document (PLAN Phase 4 unit tests)."""

from __future__ import annotations

from helpers.synth import make_page, run
from hwsets.columns.assign import UNIQUE_ROLES, assign_roles
from hwsets.columns.features import column_features
from hwsets.models import Component

H = {"bold": True, "gap": 10}


def _components(result_sets: list[list[Component]]) -> list[Component]:
    return [c for comps in result_sets for c in comps]


# ---------------------------------------------------------------------------
# Hungarian assignment on feature vectors
# ---------------------------------------------------------------------------


def test_assign_roles_on_a_clean_table() -> None:
    cols = [
        ["3", "1", "1", "2"],
        ["EA", "EA", "EA", "PR"],
        ["HINGE", "LOCKSET", "DOOR CLOSER", "KICK PLATE"],
        ["5BB1 4.5 X 4.5", "ND50PD RHO", "4040XP", "8400 10 X 34"],
        ["652", "626", "689", "630"],
        ["IVE", "SCH", "LCN", "IVE"],
    ]
    feats = [column_features(c, n_rows=4) for c in cols]
    ra = assign_roles(feats)
    assert ra.roles == ("qty", "unit", "description", "catalog", "finish", "mfr")
    assert all(m > 0 for m in ra.margins)


def test_unique_roles_are_used_at_most_once() -> None:
    mfr_like = ["IVE", "SCH", "LCN", "IVE"]
    feats = [column_features(c, n_rows=4) for c in (mfr_like, mfr_like, ["652", "626", "689"])]
    ra = assign_roles(feats)
    for role in UNIQUE_ROLES:
        assert ra.roles.count(role) <= 1
    assert ra.roles.count("mfr") == 1
    assert ra.roles[2] == "finish"


def test_header_prior_overrides_weak_value_evidence() -> None:
    short = column_features(["HINGE", "CLOSER", "STOP"], n_rows=3)
    long = column_features(["SEE NOTE ON SHEET A5", "FIELD VERIFY HAND", "BY OWNER"], n_rows=3)
    # Without a header row the evidence is too weak to pin roles; the header decides.
    with_header = assign_roles([short, long], header_prior={0: "description", 1: "notes"})
    assert with_header.roles == ("description", "notes")


def test_header_prior_decides_columns_of_collision_codes() -> None:
    # Two columns of collision codes only: no lexicon evidence, the header row decides.
    a = column_features(["PE", "NO", "PE"], n_rows=3)
    b = column_features(["PE", "AL", "PE"], n_rows=3)
    ra = assign_roles([a, b], header_prior={0: "finish", 1: "mfr"})
    assert ra.roles == ("finish", "mfr")


def test_margin_is_assigned_minus_best_alternative() -> None:
    feats = [column_features(["IVE", "SCH", "LCN"], n_rows=3)]
    ra = assign_roles(feats)
    own = ra.scores[0][ra.roles[0]]
    other = max(v for k, v in ra.scores[0].items() if k != ra.roles[0])
    assert ra.margins[0] == round(own - other, 3)


def test_empty_features() -> None:
    assert assign_roles([]).roles == ()


def test_313_10be_column_with_finish_legend_is_finish_not_qty() -> None:
    vals = ["313", "10BE", "313", "10BE", "313"]
    without = column_features(vals, n_rows=5)
    with_legend = column_features(vals, n_rows=5, finish_legend=frozenset({"10BE", "313"}))
    assert with_legend.finish > without.finish
    desc = column_features(["HINGE", "PUSH PLATE", "PULL", "CLOSER", "STOP"], n_rows=5)
    cat = column_features(["5BB1", "8200", "8103 10", "4040XP", "WS406"], n_rows=5)
    mfr = column_features(["IVE", "IVE", "IVE", "LCN", "IVE"], n_rows=5)
    # No quantity column at all: the numeric-looking finish column must not be taken as qty.
    ra = assign_roles([desc, cat, with_legend, mfr])
    assert ra.roles == ("description", "catalog", "finish", "mfr")


# ---------------------------------------------------------------------------
# End to end: the same code resolves by its column
# ---------------------------------------------------------------------------


def test_pe_in_manufacturer_column_is_pemko() -> None:
    page = make_page(
        1,
        [
            ("HARDWARE SET NO. 1", H),
            "3|EA|HINGE|5BB1 4.5 X 4.5|652|IVE",
            "1|EA|LOCKSET|ND50PD RHO|626|SCH",
            "1|EA|CLOSER|4040XP|689|LCN",
            "1|EA|GASKETING|S88BL|BLK|PE",
            ("HARDWARE SET NO. 2", H),
            "3|EA|HINGE|5BB1 4.5 X 4.5|652|IVE",
            "1|EA|THRESHOLD|171A|613|PE",
            "1|EA|EXIT DEVICE|99L-F|626|VON",
        ],
    )
    result = run([page])
    comps = _components([s.components for s in result.sets])
    pe = [c for c in comps if c.mfr.value == "PE"]
    assert len(pe) == 2
    for c in pe:
        assert c.mfr_resolved == "Pemko"
        assert c.finish.value in {"BLK", "613"}
    roles = {v.split()[0] for v in result.column_roles.values()}
    assert {"mfr", "finish", "qty", "description", "catalog"} <= roles


def test_pe_in_finish_column_is_a_finish() -> None:
    page = make_page(
        1,
        [
            ("HARDWARE SET NO. 1", H),
            "3|EA|HINGE|5BB1 4.5 X 4.5|626|IVE",
            "1|EA|LOCKSET|ND50PD RHO|626|SCH",
            "1|EA|CLOSER|4040XP|PE|LCN",
            "1|EA|STOP|WS406|630|IVE",
            ("HARDWARE SET NO. 2", H),
            "3|EA|HINGE|5BB1 4.5 X 4.5|630|IVE",
            "1|EA|CLOSER|4040XP|PE|LCN",
        ],
    )
    result = run([page])
    closers = [c for s in result.sets for c in s.components if c.description.value == "CLOSER"]
    assert len(closers) == 2
    for c in closers:
        assert c.finish.value == "PE"
        assert c.mfr.value == "LCN"
        assert c.mfr_resolved == "LCN"


def test_313_10be_finish_column_end_to_end_with_legend() -> None:
    x5 = (72.0, 110.0, 260.0, 440.0, 500.0)
    legend = make_page(
        1,
        [
            "FINISHES:",
            "313 Dark Bronze Anodized",
            "10BE Dark Oxidized Satin Bronze \u2013 Equivalent",
            "626 Satin Chromium",
        ],
    )
    sched = make_page(
        2,
        [
            ("HARDWARE SET NO. 1", H),
            "3|HINGE|5BB1 4.5 X 4.5|10BE|IVE",
            "1|PUSH PLATE|8200 4 X 16|313|IVE",
            "1|PULL|8103 10|313|IVE",
            "1|CLOSER|4040XP|10BE|LCN",
            ("HARDWARE SET NO. 2", H),
            "1|DOOR PULL|9264 12|10BE|IVE",
            "1|THRESHOLD|171A|313|PE",
        ],
        x5,
    )
    result = run([legend, sched])
    comps = [c for s in result.sets for c in s.components]
    assert [c.finish.value for c in comps] == ["10BE", "313", "313", "10BE", "10BE", "313"]
    assert [c.qty.value for c in comps] == [3, 1, 1, 1, 1, 1]
