"""Glue: live data in, projections + per-team transfer plans + dashboard out."""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import api, model, news as news_mod, optimize, planner, scenarios as scenarios_mod

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
SITE = ROOT / "site"


def load_config():
    return yaml.safe_load((ROOT / "config.yml").read_text())


def resolve_squad(df, element_ids=None, by_name=None):
    """Squad as model row ids. Element ids from the API are the model's ids."""
    squad, _ = resolve_squad_traced(df, element_ids, by_name)
    return squad


def resolve_squad_traced(df, element_ids=None, by_name=None):
    """Like resolve_squad but also reports where the squad came from.

    "api" means the live picks resolved; "config" means the API picks were
    unusable (missing/unknown players) and the config fallback won — which is
    exactly the failure that used to be silent, so callers must surface it.
    """
    if element_ids:
        found = [int(i) for i in element_ids if int(i) in set(df.id)]
        if len(found) == 15:
            return found, "api"
        missing = sorted(set(map(int, element_ids)) - set(found))
    else:
        missing = []
    out = []
    for name, club in (by_name or []):
        m = df[(df.name == name) & (df.team == club)]
        if len(m) != 1:
            m = df[df.name == name]
        if len(m) == 1:
            out.append(int(m.iloc[0].id))
    return out, f"config (api picks unusable: {len(element_ids or [])} given, " \
                f"{len(found) if element_ids else 0} known to the model; missing ids {missing})"


def build_projections(offline=False, horizon=5):
    """Projections plus the context needed by every job."""
    fx = None
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
    # engine 6: signals the watch job scraped are resolved here against the
    # live bootstrap, then model.build applies them (lower-only, doubtful-only)
    news = None
    if not offline and boot is not None:
        try:
            raw = news_mod.load_signals()
            if raw:
                news = news_mod.resolve_players(
                    news_mod.base_frame(boot), raw)
        except Exception as e:                       # noqa: BLE001
            print(f"[proj] news engine unavailable: {e}")
    df, teams, fxdf, gws = model.build(horizon=len(gws), start_gw=start,
                                       frames=frames, gw26=gw26, news=news)
    return {"df": df, "teams": teams, "fixtures": fxdf, "gws": gws,
            "bootstrap": boot, "start": start, "frames": frames, "gw26": gw26,
            "fx": fx, "news": news}


def long_projection(ctx, horizon):
    """Re-run the projection over the rest of the season, for chip planning.

    Reuses the frames already fetched, so this costs arithmetic and no API calls.
    Component columns are dropped so the season-wide frame stays small; the
    quantile ceiling columns are kept because chip scoring uses them.
    """
    return model.build(horizon=horizon, start_gw=ctx["gws"][0],
                       frames=ctx.get("frames"), gw26=ctx.get("gw26"),
                       with_components=False)


def team_kwargs(df, cfg_team):
    """Optimiser settings for one team, from config."""
    kw = {}
    engines = load_config().get("engines") or {}
    if cfg_team.get("lock"):
        ids = resolve_squad(df, by_name=[tuple(x) for x in cfg_team["lock"]])
        kw["locked"] = ids
    if cfg_team.get("ban"):
        ids = resolve_squad(df, by_name=[tuple(x) for x in cfg_team["ban"]])
        kw["banned"] = ids
    if (engines.get("rank") or {}).get("enabled"):
        # engine 1: signed tilt (positive template-safe, negative differential)
        # plus the rank-density weight. The legacy ownership_bonus maps onto
        # tilt on the xp-weighted scale: 0.04 pts per 1% ~ a 0.48 tilt.
        rank = cfg_team.get("rank") or {}
        kw["rank_alpha"] = float(rank.get("alpha",
                                          engines["rank"].get("alpha", 0.5)))
        tilt = rank.get("tilt")
        if tilt is None and cfg_team.get("ownership_bonus"):
            tilt = max(-1.0, min(1.0, float(cfg_team["ownership_bonus"]) * 12))
        if tilt:
            kw["template_tilt"] = float(tilt)
        if rank.get("cap_tilt"):
            kw["cap_tilt"] = float(rank["cap_tilt"])
        if rank.get("elite_weight"):
            kw["elite_weight"] = float(rank["elite_weight"])
    elif cfg_team.get("ownership_bonus"):
        kw["own_bonus"] = float(cfg_team["ownership_bonus"])   # deprecated path
    if cfg_team.get("min_differentials"):
        d = cfg_team["min_differentials"]
        kw["min_differentials"] = (int(d["count"]), float(d["max_ownership"]))
    if cfg_team.get("objective") == "ceiling":
        # cxp is now a deprecated alias for the simulated q85 ceiling
        has_q = any(str(c).startswith("q85") for c in df.columns)
        kw["xp_prefix"] = "q85" if has_q else "cxp"
    if cfg_team.get("max_captain_ownership"):
        kw["max_captain_ownership"] = float(cfg_team["max_captain_ownership"])
    return kw


TUNED_KEYS = ("rank_alpha", "template_tilt", "cap_tilt",
              "risk_lambda", "n_scenarios")


def apply_tuning(kw, cfg_team, hit_threshold):
    """Engine 4: overlay the tuner's best params UNDER per-team config.

    Only knobs neither the team nor the engines block has pinned get moved,
    and only while config.yml says tuning.auto_apply: true. Never writes
    config.yml; the override lives for this plan only. Returns (kw, hit_threshold,
    applied_dict) so the brief can say what the tuner changed.
    """
    cfg = load_config()
    tun = cfg.get("tuning") or {}
    if not tun.get("auto_apply"):
        return kw, hit_threshold, {}
    f = ROOT / tun.get("results", "data/backtest/tuning.json")
    try:
        params = (json.loads(f.read_text()).get("best") or {}).get("params") or {}
    except (OSError, ValueError):
        return kw, hit_threshold, {}
    eng = cfg.get("engines") or {}
    applied = {}
    for k in TUNED_KEYS:
        v = params.get(k)
        if v is None or v == 0:
            continue
        if k == "rank_alpha":
            if not (eng.get("rank") or {}).get("enabled") \
                    or (cfg_team.get("rank") or {}).get("alpha") is not None:
                continue
        elif k == "template_tilt":
            if (cfg_team.get("rank") or {}).get("tilt") is not None:
                continue
        elif k == "cap_tilt":
            if (cfg_team.get("rank") or {}).get("cap_tilt") is not None:
                continue
        elif k in ("risk_lambda", "n_scenarios"):
            if not (eng.get("scenarios") or {}).get("enabled") \
                    or "risk" in cfg_team:
                continue
        kw[k] = v
        applied[k] = v
    if "hit_threshold" in (params or {}) and "hit_threshold" not in cfg_team:
        hit_threshold = float(params["hit_threshold"])
        applied["hit_threshold"] = hit_threshold
    return kw, hit_threshold, applied


def plan_team(ctx, cfg_team, state, pool=None):
    """Transfer plan for one team, honouring its free transfers and hit policy."""
    df, gws = ctx["df"], ctx["gws"]
    kw = team_kwargs(df, cfg_team)
    tuned_hit = float(cfg_team.get("hit_threshold", 6))
    squad, squad_source = resolve_squad_traced(
        df, state.get("picks"), [tuple(x) for x in cfg_team.get("squad", [])])
    if len(squad) != 15:
        return {"error": f"squad resolved to {len(squad)} players "
                         f"(source {squad_source})"}
    if squad_source != "api":
        print(f"[plan] WARNING: {squad_source} — the plan is built on the "
              f"config fallback squad, not the live API squad")
    if pool is None:
        pool = optimize.prune(df, gws, always=squad + list(kw.get("locked", [])))
    # engine 1b: the elite template's ownership share, blended into the tilt
    # by the planner when the team config sets rank.elite_weight. The column
    # only appears when a fresh elite sample exists - without one the plan
    # is bit-identical to the plain-ownership run.
    if kw.get("elite_weight"):
        elite = read_state("elite") or {}
        emap = {int(r["id"]): float(r["elite"]) for r in elite.get("template", [])}
        if emap:
            pool = pool.assign(elite_by=pool["id"].map(
                lambda i: emap.get(int(i), 0.0)))
    ft = int(state.get("free_transfers", 1))
    if cfg_team.get("unlimited_transfers") or gws[0] == 1:
        ft = 15          # transfers are unlimited and free before the GW1 deadline
    # engine 2: scenario CVaR, from the global engines block with per-team override
    eng = (load_config().get("engines") or {}).get("scenarios") or {}
    risk = cfg_team.get("risk") or {}
    lam = risk.get("risk_lambda", eng.get("risk_lambda", 0.0))
    if eng.get("enabled") and lam:
        S_n = int(risk.get("n", eng.get("n", 32)))
        samples, weights = scenarios_mod.scenario_set(
            pool, gws, S=S_n, seed=risk.get("seed", eng.get("seed", 0)),
            method=eng.get("method", "kmeans"),
            team_shock=float(eng.get("team_shock", 0.18)))
        kw.update(scenarios=samples, scenario_weights=weights, risk_lambda=lam,
                  cvar_beta=float(risk.get("cvar_beta",
                                           eng.get("cvar_beta", 0.75))))
    # engine 3 Tier A: TC/BB decided inside the ILP for the IMMINENT deadline
    # week only. A five-gameweek horizon cannot see that a chip is once a
    # season - left free across the horizon the solver burns it on the first
    # decent week - so season-level timing stays with chips.calendar and the
    # ILP only answers "is the chip worth it this week, given the plan?".
    # Window legality from the API's own chips array (offline: defaults);
    # already-spent chips are pinned shut.
    chips_cfg = (load_config().get("engines") or {}).get("chips") or {}
    if chips_cfg.get("tier_a"):
        try:
            wins = ctx.get("chip_windows") or api.chip_windows(ctx.get("bootstrap"))
        except Exception:
            wins = None
        if wins is None:
            from .chips import DEFAULT_WINDOWS as wins
        this_gw = gws[0]

        def legal(key):
            return any(w["start"] <= this_gw <= w["stop"]
                       for w in (wins.get(key) or []))

        kw.update(
            chips_tc_bb=True,
            chip_windows={"3xc": [{"start": this_gw, "stop": this_gw}]
                          if legal("3xc") else [],
                          "bboost": [{"start": this_gw, "stop": this_gw}]
                          if legal("bboost") else []},
            chips_used=state.get("chips_used", ()))
    # engine 5: price predictions into the budget row. No usable log means no
    # predictions and no price kwargs at all - the plan stays bit-identical.
    price_cfg = (load_config().get("engines") or {}).get("price") or {}
    if price_cfg.get("enabled"):
        from . import price as price_mod
        log_df = price_mod.read_log()
        preds = price_mod.predict(log_df)
        if len(preds) >= 5:                      # too thin a history is noise
            pool = price_mod.attach_predictions(pool, preds, gws)
            n, G = len(pool), len(gws)
            pm = np.array([[pool[f"price_buy{g}"].values[i] for g in gws]
                           for i in range(n)])
            kw.update(price_matrix=pm, price_gamma=float(price_cfg.get("gamma", 0.05)))
            # sell at what FPL pays back, not at list price
            detail = {p["element"]: p.get("selling_price")
                      for p in (state.get("picks_detail") or [])}
            if detail:
                sell = pool["price"].values.astype(float).copy()
                for i, eid in enumerate(pool["id"].values):
                    if int(eid) in detail and detail[int(eid)]:
                        sell[i] = float(detail[int(eid)]) / 10.0
                kw["sell_price"] = sell
    # engine 4: the tuner's overlay lands last, AFTER all engine blocks have
    # built their kwargs, so a tuned risk_lambda is never clobbered by the
    # config-driven scenario block above
    kw, tuned_hit, tuned_applied = apply_tuning(kw, cfg_team, tuned_hit)
    p, info = planner.plan_with_hit_policy(
        pool, gws, squad,
        hit_threshold=tuned_hit,
        free_transfers=ft, bank=float(state.get("bank", 0.0)), **kw)
    if p is None:
        return {"error": info.get("advice", "planner infeasible") if info
                else "planner infeasible"}
    # engine 5 diagnostics: predictions for the players this week's plan buys
    price_pred = []
    if "pred_rise" in pool.columns:
        pr = pool.set_index("id")
        for i in p["weeks"][0]["in"]:
            if i in pr.index and pr.loc[i, "pred_rise"] > 0.0:
                price_pred.append({"element": int(i),
                                   "p_rise": float(pr.loc[i, "pred_rise"]),
                                   "conf": float(pr.loc[i, "pred_conf"])})
        price_pred.sort(key=lambda d: -d["p_rise"])
    cap_own = kw.get("max_captain_ownership")
    planner.attach_vice(df, p["weeks"], cap_own)
    # engine 7: chips the bot plays ITSELF when config.chips_auto says so (the
    # user delegated this, specifically for Minoux_41). Three gates, all hard:
    # the chip is not yet spent (live entry history), the API's own window is
    # open for the imminent gameweek, and the modelled gain over the horizon
    # clears the config threshold. The winning branch's ILP week becomes the
    # submit payload — the submit job activates the chip, never pays for the
    # moves. TC/BB stay tier-A (inside the plan) and free hit stays advisory.
    chip_play = None
    auto = cfg_team.get("chips_auto") or {}
    used = set(state.get("chips_used") or ())
    try:
        wins = ctx.get("chip_windows") or api.chip_windows(ctx.get("bootstrap"))
    except Exception:
        wins = None
    if wins is None:
        from .chips import DEFAULT_WINDOWS as wins
    wc_gate = float(auto.get("wildcard") or 0)
    if wc_gate and "wildcard" not in used and \
            any(w["start"] <= gws[0] <= w["stop"] for w in (wins.get("wildcard") or [])):
        [wc] = planner.chip_branches(
            pool, gws, squad, p, [{"chip": "wildcard", "gw": gws[0]}],
            bank=float(state.get("bank", 0.0)), **kw)
        gain = wc.get("gain")
        if gain is not None and gain >= wc_gate:
            chip_play = {"chip": "wildcard", "gw": gws[0], "gain": float(gain),
                         "week": None}
            wc_full = planner.wildcard_plan(
                pool, gws, squad, bank=float(state.get("bank", 0.0)), **kw)
            if wc_full is not None:
                chip_play["week"] = wc_full["weeks"][0]
    fh_gate = float(auto.get("free_hit") or 0)
    if fh_gate and chip_play is None and "freehit" not in used and \
            any(w["start"] <= gws[0] <= w["stop"] for w in (wins.get("freehit") or [])):
        [fh] = planner.chip_branches(
            pool, gws, squad, p, [{"chip": "free_hit", "gw": gws[0]}],
            bank=float(state.get("bank", 0.0)), **kw)
        gain = fh.get("gain")
        if gain is not None and gain >= fh_gate:
            chip_play = {"chip": "free_hit", "gw": gws[0], "gain": float(gain),
                         "squad": fh.get("squad"), "week": None}
    if chip_play:
        print(f"[plan] CHIP ARMED: {chip_play['chip']} for GW{chip_play['gw']} "
              f"(+{chip_play['gain']} xp over the horizon)")
    plan_kw = {k: v for k, v in kw.items()
               if k not in ("max_captain_ownership", "scenarios",
                            "scenario_weights", "risk_lambda", "cvar_beta",
                            "rank_alpha", "template_tilt", "cap_tilt",
                            "elite_weight", "chips_tc_bb", "chip_windows",
                            "chips_used", "price_matrix", "sell_price",
                            "price_gamma")}
    target = optimize.solve(pool, gws, allow_infeasible=True, **plan_kw)
    return {
        "squad": squad, "squad_source": squad_source,
        "entry_id": state.get("entry"),
        "picks_error": state.get("picks_error"),
        "picks_source": state.get("picks_source"),
        "current_report": optimize.squad_report(df, squad, gws, cap_own),
        "plan": p, "hit_policy": info,
        "target": target["squad"] if target else None,
        "target_report": optimize.squad_report(df, target["squad"], gws, cap_own)
                         if target else None,
        "chips": planner.evaluate_chips(df, p["weeks"], gws),
        "chip_play": chip_play,
        "price_pred": price_pred,
        "tuned": tuned_applied,
        "free_transfers": ft, "bank": float(state.get("bank", 0.0)),
        "settings": kw_summary(cfg_team)
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
    (STATE / f"{name}.json").write_text(json.dumps(obj, indent=1, sort_keys=True),
                                        encoding="utf-8")
