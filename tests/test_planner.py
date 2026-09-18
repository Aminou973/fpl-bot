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


def test_team_constraints_honoured_at_horizon_end():
    """Whatever the config still demands of Minoux_41's squad must hold.

    The elite-chase flip of 2026-08-29 deliberately removed the team's
    min_differentials block, so the old pinned quota of nine differentials
    went with it - this now honours whatever the config says, and stipulates
    nothing when it stipulates nothing.
    """
    df, _, _, gws = build()
    cfg = pipeline.load_config()["teams"].get("Minoux_41", {})
    plan, _, _ = team_plan(df, gws, "Minoux_41")
    own = df.set_index("id").selected_by.to_dict()
    final = plan["weeks"][-1]["squad"]
    d = cfg.get("min_differentials")
    if d:
        n_diff = sum(1 for i in final if own.get(i, 0) < float(d["max_ownership"]))
        assert n_diff >= int(d["count"]), \
            f"only {n_diff} differentials in final squad"


def test_planner_deterministic():
    df, _, _, gws = build()
    a, _, _ = team_plan(df, gws, "Minoux_69")
    b, _, _ = team_plan(df, gws, "Minoux_69")
    assert a["weeks"][0]["squad"] == b["weeks"][0]["squad"]
    assert a["weeks"][0]["in"] == b["weeks"][0]["in"]

def _swap_legs(df, pool, squad, gws):
    """A same-position upgrade leg: the best affordable buy for the weakest own.

    apply_lock's "held" state is exactly such a re-plan, so the forced-legs
    tests need legs that differ from whatever the free solve picked and that
    are feasible for real (same position keeps the squad-shape counts intact,
    cheaper price keeps the budget row intact).
    """
    r = pool.set_index("id")
    xp = f"xp{gws[0]}"
    out_pid = min(squad, key=lambda p: float(r.loc[p, xp]))
    cands = pool[(~pool.id.isin(squad))
                 & (pool.pos == r.loc[out_pid, "pos"])
                 & (pool.price <= float(r.loc[out_pid, "price"]))]
    in_pid = int(cands.sort_values(xp, ascending=False).id.values[0])
    return [in_pid], [out_pid]


def test_forced_legs_solve_around_a_committed_move():
    """apply_lock "held" re-plans with the committed legs FORCED (2026-09-18).

    The old implementation pasted the committed in/out onto the fresh solve's
    week, leaving last_plan.json with transfers from one decision and a
    squad_after/payload from another - Minoux_41's payload named O'Reilly and
    Mbeumo, players its legs (in 356, out 499) never bought. Forcing the legs
    must make the whole week agree with them."""
    df, _, _, gws = build()
    team = "Minoux_69"
    cfg = pipeline.load_config()["teams"][team]
    squad = resolve_cfg_squad(df, cfg)
    pool = optimize.prune(df, gws, always=squad)
    natural, _, _ = team_plan(df, gws, team)
    legs = (natural["weeks"][0]["in"], natural["weeks"][0]["out"])
    if not legs[0]:
        legs = _swap_legs(df, pool, squad, gws)
    forced, info = planner.plan_with_hit_policy(
        pool, gws, squad, hit_threshold=6.0, free_transfers=1,
        force_legs=legs, **pipeline.team_kwargs(df, cfg))
    assert forced is not None, info
    w0 = forced["weeks"][0]
    assert sorted(w0["in"]) == sorted(legs[0])
    assert sorted(w0["out"]) == sorted(legs[1])
    assert set(w0["squad"]) == set(squad) - set(legs[1]) | set(legs[0])
    # the rest of the horizon stays internally consistent with week 0
    prev = w0["squad"]
    for wk in forced["weeks"][1:]:
        assert set(wk["squad"]) - set(prev) == set(wk["in"])
        assert set(prev) - set(wk["squad"]) == set(wk["out"])
        prev = wk["squad"]


def test_plan_team_force_legs_survive_the_prune():
    """The committed arrival is often a player optimize.prune would drop - the
    pool must keep it, or the pin silently vanishes and the solve picks
    different moves (the other half of the GW5 mixing)."""
    df, _, _, gws = build()
    team = "Minoux_69"
    cfg = pipeline.load_config()["teams"][team]
    squad = resolve_cfg_squad(df, cfg)
    pool = optimize.prune(df, gws, always=squad)
    legs = _swap_legs(df, pool, squad, gws)
    res = pipeline.plan_team({"df": df, "gws": gws, "offline": True}, cfg,
                             {"free_transfers": 1, "bank": 0.0},
                             name=team, force_legs=legs)
    assert "error" not in res, res.get("error")
    w0 = res["plan"]["weeks"][0]
    assert sorted(w0["in"]) == sorted(legs[0])
    assert sorted(w0["out"]) == sorted(legs[1])
    assert set(w0["squad"]) == set(squad) - set(legs[1]) | set(legs[0])


def test_forced_legs_on_a_player_not_owned_are_infeasible():
    """Selling a player the squad does not hold cannot be pinned - the re-plan
    must report infeasible (deadline_plan then falls back to the fresh solve)
    rather than quietly solving something else."""
    df, _, _, gws = build()
    team = "Minoux_69"
    cfg = pipeline.load_config()["teams"][team]
    squad = resolve_cfg_squad(df, cfg)
    pool = optimize.prune(df, gws, always=squad)
    r = pool.set_index("id")
    stranger = int(r.drop(squad).sort_values(f"xp{gws[0]}",
                                       ascending=False).index[0])
    plan, info = planner.plan_with_hit_policy(
        pool, gws, squad, hit_threshold=6.0, free_transfers=1,
        force_legs=([], [stranger]), **pipeline.team_kwargs(df, cfg))
    assert plan is None and info.get("infeasible"), (plan, info)
