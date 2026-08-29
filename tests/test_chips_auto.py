"""Engine 7: chips the bot plays itself, gated on modelled value.

Two layers are pinned here. The planner layer: a chip branch keeps the
persona (elite_weight) and the wildcard branch really does unlock more moves
than the base plan. The payload layer: when the plan arms a wildcard, the
submitter's entry carries the chip code and the wildcard week's moves, not
the base plan's.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fplbot import model, planner  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jobs"))

import deadline_plan  # noqa: E402


def mini_pool():
    df, _, _, gws = model.build(horizon=3, start_gw=3)
    return df.sort_values("xp_total", ascending=False).head(80).copy(), gws


def squad_of(pool):
    p = pool.sort_values(["price", "xp_total"])
    return list(map(int,
                    list(p[p.pos == "GKP"].id[:2])
                    + list(p[p.pos == "DEF"].sort_values("xp_total", ascending=False).id[:5])
                    + list(p[p.pos == "MID"].sort_values("xp_total", ascending=False).id[:5])
                    + list(p[p.pos == "FWD"].sort_values("xp_total", ascending=False).id[:3])))


def test_wildcard_branch_moves_more_than_base():
    pool, gws = mini_pool()
    squad = squad_of(pool)
    base = planner.plan(pool, gws, squad, bank=0.0, free_transfers=1)
    wc = planner.wildcard_plan(pool, gws, squad, bank=0.0)
    base_moves = sum(len(wk["in"]) for wk in base["weeks"])
    wc_moves = sum(len(wk["in"]) for wk in wc["weeks"])
    assert wc_moves > base_moves, "wildcard should rebuild, not act like 1 FT"


def test_branch_keeps_elite_weight_and_returns_gain():
    pool, gws = mini_pool()
    pool = pool.assign(elite_by=pool.price * 3.0)
    squad = squad_of(pool)
    base = planner.plan(pool, gws, squad, bank=0.0, free_transfers=1,
                        elite_weight=0.5)
    [br] = planner.chip_branches(pool, gws, squad, base,
                                 [{"chip": "wildcard", "gw": gws[0]}],
                                 bank=0.0, elite_weight=0.5)
    assert br["gain"] is not None and br["squad"]


def test_entry_carries_chip_and_wildcard_week():
    pool, gws = mini_pool()
    squad = squad_of(pool)
    base = planner.plan(pool, gws, squad, bank=0.0, free_transfers=1)
    wc = planner.wildcard_plan(pool, gws, squad, bank=0.0)
    wk = wc["weeks"][0]
    res = {"squad": squad, "squad_source": "api", "entry_id": 4896428,
           "plan": {"weeks": base["weeks"]},
           "chip_play": {"chip": "wildcard", "gw": gws[0], "gain": 3.2,
                         "week": wk}}
    ent = deadline_plan.last_plan_entry(pool, res)
    assert ent["chip"] == "wildcard" and ent["chip_gain"] == 3.2
    # the moves submitted are the wildcard week's, not the base plan's
    assert sorted(ent["in"]) == sorted(wk["in"])
    assert sorted(ent["out"]) == sorted(wk["out"])
    assert ent["captain"] == wk["captain"]
    # and the payload is exactly the rebuilt squad's 15, XI first
    assert len(ent["picks_payload"]) == 15
    assert {p["element"] for p in ent["picks_payload"]} == set(wk["squad"])


def test_entry_without_chip_plan_is_unchanged():
    pool, gws = mini_pool()
    squad = squad_of(pool)
    base = planner.plan(pool, gws, squad, bank=0.0, free_transfers=1)
    wk = base["weeks"][0]
    res = {"squad": squad, "squad_source": "api", "entry_id": 1,
           "plan": {"weeks": base["weeks"]}}
    ent = deadline_plan.last_plan_entry(pool, res)
    assert ent["chip"] is None and ent["chip_gain"] is None
    assert sorted(ent["in"]) == sorted(wk["in"])