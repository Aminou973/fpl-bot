"""Glue: live data in, projections + per-team transfer plans + dashboard out."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import yaml

from . import api, model, optimize, planner

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
SITE = ROOT / "site"


def load_config():
    return yaml.safe_load((ROOT / "config.yml").read_text())


def resolve_squad(df, element_ids=None, by_name=None):
    """Squad as model row ids. Element ids from the API are the model's ids."""
    if element_ids:
        found = [int(i) for i in element_ids if int(i) in set(df.id)]
        if len(found) == 15:
            return found
    out = []
    for name, club in (by_name or []):
        m = df[(df.name == name) & (df.team == club)]
        if len(m) != 1:
            m = df[df.name == name]
        if len(m) == 1:
            out.append(int(m.iloc[0].id))
    return out


def build_projections(offline=False, horizon=5):
    """Projections plus the context needed by every job."""
    if offline:
        frames = api.offline_frames(ROOT / "data")
        boot = None
        gw26 = None
        start = model.next_gw(frames[2])
    else:
        boot = api.bootstrap()
        fx = api.fixtures()
        frames = api.frames(boot, fx)
        gw26 = api.season_gameweeks(boot, fx)
        start = api.next_event(boot)["id"]
    gws = list(range(start, min(start + horizon, 39)))
    df, teams, fxdf, gws = model.build(horizon=len(gws), start_gw=start,
                                       frames=frames, gw26=gw26)
    return {"df": df, "teams": teams, "fixtures": fxdf, "gws": gws,
            "bootstrap": boot, "start": start}


def team_kwargs(df, cfg_team):
    """Optimiser settings for one team, from config."""
    kw = {}
    if cfg_team.get("lock"):
        ids = resolve_squad(df, by_name=[tuple(x) for x in cfg_team["lock"]])
        kw["locked"] = ids
    if cfg_team.get("ban"):
        ids = resolve_squad(df, by_name=[tuple(x) for x in cfg_team["ban"]])
        kw["banned"] = ids
    if cfg_team.get("ownership_bonus"):
        kw["own_bonus"] = float(cfg_team["ownership_bonus"])
    if cfg_team.get("min_differentials"):
        d = cfg_team["min_differentials"]
        kw["min_differentials"] = (int(d["count"]), float(d["max_ownership"]))
    if cfg_team.get("objective") == "ceiling":
        kw["xp_prefix"] = "cxp"
    if cfg_team.get("max_captain_ownership"):
        kw["max_captain_ownership"] = float(cfg_team["max_captain_ownership"])
    return kw


def plan_team(ctx, cfg_team, state, pool=None):
    """Transfer plan for one team, honouring its free transfers and hit policy."""
    df, gws = ctx["df"], ctx["gws"]
    kw = team_kwargs(df, cfg_team)
    squad = resolve_squad(df, state.get("picks"),
                          [tuple(x) for x in cfg_team.get("squad", [])])
    if len(squad) != 15:
        return {"error": f"squad resolved to {len(squad)} players"}
    if pool is None:
        pool = optimize.prune(df, gws, always=squad + list(kw.get("locked", [])))
    ft = int(state.get("free_transfers", 1))
    if cfg_team.get("unlimited_transfers") or gws[0] == 1:
        ft = 15          # transfers are unlimited and free before the GW1 deadline
    p, info = planner.plan_with_hit_policy(
        pool, gws, squad,
        hit_threshold=float(cfg_team.get("hit_threshold", 6)),
        free_transfers=ft, bank=float(state.get("bank", 0.0)), **kw)
    if p is None:
        return {"error": info.get("advice", "planner infeasible") if info
                else "planner infeasible"}
    plan_kw = {k: v for k, v in kw.items() if k != "max_captain_ownership"}
    target = optimize.solve(pool, gws, allow_infeasible=True, **plan_kw)
    return {
        "squad": squad,
        "current_report": optimize.squad_report(df, squad, gws),
        "plan": p, "hit_policy": info,
        "target": target["squad"] if target else None,
        "target_report": optimize.squad_report(df, target["squad"], gws) if target else None,
        "chips": planner.evaluate_chips(df, p["weeks"], gws),
        "free_transfers": ft, "bank": float(state.get("bank", 0.0)),
        "settings": kw_summary(cfg_team),
    }


def kw_summary(cfg_team):
    bits = []
    if cfg_team.get("lock"):
        bits.append("locked: " + ", ".join(x[0] for x in cfg_team["lock"]))
    if cfg_team.get("ban"):
        bits.append("barred: " + ", ".join(x[0] for x in cfg_team["ban"]))
    if cfg_team.get("min_differentials"):
        d = cfg_team["min_differentials"]
        bits.append(f"at least {d['count']} players under {d['max_ownership']}% owned")
    if cfg_team.get("objective") == "ceiling":
        bits.append("optimised for ceiling")
    if cfg_team.get("max_captain_ownership"):
        bits.append(f"captain under {cfg_team['max_captain_ownership']}% owned")
    bits.append(f"hit threshold {cfg_team.get('hit_threshold', 6)} pts")
    return "; ".join(bits)


def read_state(name, default=None):
    f = STATE / f"{name}.json"
    return json.loads(f.read_text()) if f.exists() else (default or {})


def write_state(name, obj):
    STATE.mkdir(exist_ok=True)
    (STATE / f"{name}.json").write_text(json.dumps(obj, indent=1, sort_keys=True))
