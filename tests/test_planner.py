"""Invariant tests for the planner: the rules the live bot must never break."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fplbot import model, optimize, planner, pipeline


def build():
    return model.build(horizon=3, start_gw=3)


def resolve_cfg_squad(df, cfg):
    """Config fallback squad, topped up when the offline snapshot misses players."""
    squad, _ = pipeline.resolve_squad_traced(
        df, None, by_name=[tuple(x) for x in cfg["squad"]])
    if len(squad) < 15:
        have = set(squad)
        for pid in df.sort_values("xp_total", ascending=False)["id"]:
            if len(squad) >= 15:
                break
            if int(pid) not in have:
                squad.append(int(pid))
                have.add(int(pid))
    return squad


def team_plan(df, gws, team):
    cfg = pipeline.load_config()["teams"][team]
    squad = resolve_cfg_squad(df, cfg)
    pool = optimize.prune(df, gws, always=squad)
    plan, info = planner.plan_with_hit_policy(
        pool, gws, squad, hit_threshold=cfg.get("hit_threshold", 6.0),
        free_transfers=cfg.get("free_transfers", 1),
        **pipeline.team_kwargs(df, cfg))
    return plan, info, squad


def test_plan_structure_and_ft_accounting():
    df, _, _, gws = build()
    for team in pipeline.load_config()["teams"]:
        plan, _, _ = team_plan(df, gws, team)
        assert plan is not None, f"{team}: no feasible plan"
        prev_squad = None
        for wk in plan["weeks"]:
            assert len(wk["squad"]) == 15
            assert 0 <= wk["free_transfers"] <= 5
            assert 0 <= wk["hits"] <= 15
            assert len(wk["xi"]) == 11
            assert len(set(wk["squad"])) == 15
            if prev_squad is not None:
                ins, outs = set(wk["in"]), set(wk["out"])
                assert set(wk["squad"]) - set(prev_squad) == ins
                assert set(prev_squad) - set(wk["squad"]) == outs
            prev_squad = wk["squad"]


def test_captain_rules():
    df, _, _, gws = build()
    pos = df.set_index("id").pos.to_dict()
    for team in pipeline.load_config()["teams"]:
        plan, _, _ = team_plan(df, gws, team)
        for wk in plan["weeks"]:
            cap = wk["captain"]
            assert cap in wk["xi"]
            assert pos[cap] not in ("GKP", "DEF")


def test_hit_threshold_respected():
    df, _, _, gws = build()
    plan, info, _ = team_plan(df, gws, "Minoux_69")
    if info.get("took_hits"):
        assert info["gain_over_no_hit"] is None or \
            info["gain_over_no_hit"] >= info["threshold"], info
    else:
        assert plan["total_hits"] == 0


def test_min_differentials_honoured_at_horizon_end():
    df, _, _, gws = build()
    plan, _, _ = team_plan(df, gws, "Minoux_41")
    own = df.set_index("id").selected_by.to_dict()
    final = plan["weeks"][-1]["squad"]
    # config asks for 9 players owned by under 8% at the end of the horizon
    n_diff = sum(1 for i in final if own.get(i, 0) < 8.0)
    assert n_diff >= 9, f"only {n_diff} differentials in final squad"


def test_planner_deterministic():
    df, _, _, gws = build()
    a, _, _ = team_plan(df, gws, "Minoux_69")
    b, _, _ = team_plan(df, gws, "Minoux_69")
    assert a["weeks"][0]["squad"] == b["weeks"][0]["squad"]
    assert a["weeks"][0]["in"] == b["weeks"][0]["in"]