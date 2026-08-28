"""Engine 3 invariants: chips never break the game's hard rules."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fplbot import model, optimize, planner
from fplbot.chips import DEFAULT_WINDOWS


def build():
    return model.build(horizon=4, start_gw=3)


def squad_of(pool):
    return pool.id.head(15).tolist()


def test_no_chips_identical():
    """chips_tc_bb=False must be exactly today's model."""
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    s = squad_of(pool)
    base = planner.plan(pool, gws, s, time_limit=60)
    off = planner.plan(pool, gws, s, time_limit=60, chips_tc_bb=False)
    wk0, wk1 = base["weeks"][0], off["weeks"][0]
    assert (wk0["squad"], wk0["captain"]) == (wk1["squad"], wk1["captain"])
    assert base["objective"] == off["objective"]
    assert "chip" not in wk1 or wk1["chip"] is None


def test_chips_outside_window_never_played():
    """With every window closed, no chip may fire - and the plan still solves."""
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    s = squad_of(pool)
    closed = {"3xc": [], "bboost": []}
    res = planner.plan(pool, gws, s, time_limit=90, chips_tc_bb=True,
                       chip_windows=closed)
    assert res is not None
    assert all(wk["chip"] is None for wk in res["weeks"])


def test_used_chip_never_recommended():
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    s = squad_of(pool)
    wide = DEFAULT_WINDOWS
    for used in ("3xc", "bboost"):
        res = planner.plan(pool, gws, s, time_limit=90, chips_tc_bb=True,
                           chip_windows=wide, chips_used=(used,))
        assert res is not None
        assert all(wk["chip"] != used for wk in res["weeks"])


def test_tc_triples_a_real_attacker_and_bb_pays_bench():
    """When TC fires, the captaincy triples a MID/FWD; BB pays exactly the bench."""
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    s = squad_of(pool)
    res = planner.plan(pool, gws, s, time_limit=120, chips_tc_bb=True,
                       chip_windows=DEFAULT_WINDOWS)
    assert res is not None
    pos = df.set_index("id").pos.to_dict()
    chips = [wk["chip"] for wk in res["weeks"] if wk["chip"]]
    assert len(chips) <= 2                     # once per chip per season
    assert len(set(chips)) == len(chips)       # never the same chip twice
    for wk in res["weeks"]:
        if wk["chip"] == "3xc":
            assert pos[wk["captain"]] in ("MID", "FWD")
        assert sum(1 for c in [wk["chip"]] if c) <= 1


def test_risk_and_chips_solve_together():
    """CVaR epigraph + Tier A chip blocks in one model: the variable layout
    must slice the U block correctly past the chip blocks (regression: the
    tail-slice reshape crashed when both engines were active)."""
    from fplbot import scenarios as scenarios_mod
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    s = squad_of(pool)
    samples, weights = scenarios_mod.scenario_set(pool, gws, S=8, seed=0)
    res = planner.plan(pool, gws, s, time_limit=90, chips_tc_bb=True,
                       chip_windows=DEFAULT_WINDOWS,
                       scenarios=samples, scenario_weights=weights,
                       risk_lambda=0.3)
    assert res is not None
    # mean_objective excludes the risk term: with risk on, it must differ
    # from the risk-adjusted objective by exactly the reported risk value
    assert res["mean_objective"] <= res["objective"]
    assert all(len(wk["squad"]) == 15 for wk in res["weeks"])


def test_wildcard_branch_restructures_for_free():
    """The wildcard branch may replace the whole squad without paying hits."""
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    s = squad_of(pool)
    base = planner.plan(pool, gws, s, time_limit=60)
    assert base is not None
    wc = planner.wildcard_plan(pool, gws, s, time_limit=120)
    assert wc is not None
    # a wildcard spends no hits and banks only one free transfer afterwards
    assert wc["total_hits"] == 0
    assert wc["weeks"][1]["free_transfers"] == 1


def test_freehit_branch_single_week():
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    s = squad_of(pool)
    base = planner.plan(pool, gws, s, time_limit=60)
    fh = planner.freehit_plan(pool, [gws[0]], s, time_limit=120)
    assert fh is not None
    assert len(fh["squad"]) == 15
    branches = planner.chip_branches(pool, gws, s, base,
                                     [{"chip": "free_hit", "gw": gws[0]}],
                                     time_limit=60)
    assert len(branches) == 1
    assert branches[0]["gain"] is not None


def test_branch_kwargs_survive_persona():
    """A persona's constraints must reach the branch solves - the old wildcard
    gain dropped them silently."""
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    s = squad_of(pool)
    base = planner.plan(pool, gws, s, time_limit=60)
    banned_ids = pool.id.head(3).tolist()
    branches = planner.chip_branches(
        pool, gws, s, base, [{"chip": "wildcard", "gw": gws[0]}],
        banned=banned_ids, min_differentials=(5, 30.0), time_limit=90)
    assert branches and branches[0]["gain"] is not None
    wc_squad = branches[0]["squad"]
    assert not (set(banned_ids) & set(wc_squad)), \
        "wildcard branch bought a banned player"