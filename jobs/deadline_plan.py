"""The deadline job: rebuild projections, plan both teams, publish, notify.

Runs on a schedule and decides for itself whether the deadline is close enough to
be worth a full run. Use --force to run it any time, --offline to run against the
CSV snapshots with no network.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from fplbot import api, dashboard, notify, optimize, pipeline  # noqa: E402
from fplbot.notify import esc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def fmt_move(df, ids):
    if not ids:
        return "none"
    r = df.set_index("id")
    return ", ".join(f"{r.loc[i, 'name']} (£{r.loc[i, 'price']:.1f})" for i in ids)


def brief(ctx, results, cfg):
    df, gws = ctx["df"], ctx["gws"]
    r = df.set_index("id")
    nxt = ctx.get("next_event") or {}
    dl = nxt.get("deadline_time", "")
    if dl:
        d = dt.datetime.fromisoformat(dl.replace("Z", "+00:00"))
        dl = d.strftime("%a %d %b, %H:%M UTC")
    out = [f"<b>Gameweek {gws[0]} plan</b>" + (f" — deadline {dl}" if dl else "")]

    for name, res in results.items():
        if "error" in res:
            out.append(f"\n<b>{esc(name)}</b>\n⚠️ {esc(res['error'])}")
            continue
        wk = res["plan"]["weeks"][0]
        cap = r.loc[wk["captain"]]
        base = res["current_report"]["xp_total"]
        gain = res["plan"]["total_xp"]
        lines = [f"\n<b>{esc(name)}</b> — {esc(res['settings'])}",
                 f"Free transfers {res['free_transfers']}, bank £{res['bank']:.1f}m"]
        if wk["out"]:
            lines.append(f"OUT {esc(fmt_move(df, wk['out']))}")
            lines.append(f"IN  {esc(fmt_move(df, wk['in']))}")
            if wk["hits"]:
                lines.append(f"Cost: {wk['hits']} hit(s), −{wk['hits'] * 4} pts — "
                             f"plan still gains {res['hit_policy'].get('gain_over_no_hit')} pts")
        else:
            lines.append(f"No transfer — roll it (next week you have "
                         f"{min(5, res['free_transfers'] + 1)})")
            if res["hit_policy"].get("rejected_hits"):
                lines.append(f"A hit was considered and rejected: it gained only "
                             f"{res['hit_policy']['gain_over_no_hit']} pts against a "
                             f"{res['hit_policy']['threshold']} pt threshold")
        lines.append(f"Captain <b>{esc(cap['name'])}</b> "
                     f"({cap['team']}, {cap[f'xp{gws[0]}']:.1f} xP → {cap[f'xp{gws[0]}']*2:.1f})")
        flagged = [f"{r.loc[i,'name']} ({r.loc[i,'news'] or 'flagged'})"
                   for i in res["squad"]
                   if isinstance(r.loc[i, "status"], str) and r.loc[i, "status"] != "a"]
        if flagged:
            lines.append("⚠️ " + esc("; ".join(flagged)))
        lines.append(f"Projected {wk['xp']:.1f} this week, {gain:.0f} over "
                     f"gameweeks {gws[0]}–{gws[-1]} (squad untouched: {base:.0f})")
        if res["hit_policy"].get("advice"):
            lines.append("💡 " + esc(res["hit_policy"]["advice"]))
        best_tc = max(res["chips"], key=lambda c: c["triple_captain"])
        best_bb = max(res["chips"], key=lambda c: c["bench_boost"])
        lines.append(f"Chips: best triple captain in this window is GW{best_tc['gw']} "
                     f"(+{best_tc['triple_captain']:.1f}); best bench boost GW{best_bb['gw']} "
                     f"(+{best_bb['bench_boost']:.1f})")
        out.append("\n".join(lines))

    site = cfg.get("site_url")
    if site:
        out.append(f"\nFull dashboard: {site}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-notify", action="store_true")
    a = ap.parse_args()

    cfg = pipeline.load_config()
    ctx = pipeline.build_projections(offline=a.offline,
                                     horizon=int(cfg.get("horizon", 5)))
    df, gws = ctx["df"], ctx["gws"]

    if not a.offline:
        nxt = api.next_event(ctx["bootstrap"])
        ctx["next_event"] = nxt
        if not a.force and nxt.get("deadline_time"):
            d = dt.datetime.fromisoformat(nxt["deadline_time"].replace("Z", "+00:00"))
            hrs = (d - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
            if hrs > float(cfg.get("plan_window_hours", 40)) or hrs < 0:
                print(f"[plan] deadline {hrs:.1f}h away — skipping")
                return

    results = {}
    for name, t in cfg["teams"].items():
        state = {"picks": [], "free_transfers": t.get("free_transfers", 1),
                 "bank": t.get("bank", 0.0)}
        if not a.offline and t.get("entry_id"):
            try:
                live = api.squad_state(t["entry_id"], ctx["bootstrap"])
                if live.get("picks"):
                    state = live
                state.setdefault("bank", 0.0)
            except Exception as e:                   # noqa: BLE001
                print(f"[plan] live squad for {name} unavailable ({e}); using config")
        results[name] = pipeline.plan_team(ctx, t, state)

    bundle = build_bundle(ctx, results, cfg)
    (ROOT / "site").mkdir(exist_ok=True)
    (ROOT / "site" / "bundle.json").write_text(json.dumps(bundle))
    dashboard.build(ROOT / "site" / "bundle.json", ROOT / "site" / "index.html")
    pipeline.write_state("last_plan", {
        "gw": gws[0], "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "teams": {k: {"in": v.get("plan", {}).get("weeks", [{}])[0].get("in", []),
                      "out": v.get("plan", {}).get("weeks", [{}])[0].get("out", [])}
                  for k, v in results.items() if "error" not in v}})

    text = brief(ctx, results, cfg)
    print(text)
    if not a.no_notify:
        notify.send(text)


def build_bundle(ctx, results, cfg):
    """Shape the data the dashboard expects."""
    df, teams, fx, gws = ctx["df"], ctx["teams"], ctx["fixtures"], ctx["gws"]
    import fplbot.model as model

    def grid_for(rng):
        out = {}
        for tid, t in teams.items():
            row = []
            for g in rng:
                f = fx[(fx.event == g) & ((fx.team_h == tid) | (fx.team_a == tid))]
                if not len(f):
                    row.append(None); continue
                cells = []
                for _, m in f.iterrows():
                    home = m.team_h == tid
                    opp = int(m.team_a if home else m.team_h)
                    xgf, xga = model.fixture_xg(teams, tid, opp, home)
                    cells.append({"opp": teams[opp]["short"], "home": bool(home),
                                  "fdr": int(m.team_h_difficulty if home else m.team_a_difficulty),
                                  "xgf": round(float(xgf), 2), "xga": round(float(xga), 2)})
                row.append(cells)
            out[t["short"]] = row
        return out

    season = grid_for(range(1, 39))
    short = {k: [c[0] if c else None for c in v[gws[0] - 1: gws[-1]]] for k, v in season.items()}

    keep = ["id", "name", "pos", "team", "price", "start_share", "status", "news",
            "hist_starts", "hist_pts", "selected_by", "xp_total", "value",
            "ceiling_total", "explosive", "b_app", "b_goals", "b_assists", "b_cs",
            "b_saves", "b_dc", "b_bonus", "b_cs_prob"] + \
           [f"{p}{g}" for p in ("xp", "cxp", "fx", "fdr") for g in gws]
    keep = [c for c in keep if c in df.columns]

    builds = {}
    for name, res in results.items():
        if "error" in res:
            continue
        builds[name] = {
            "role": cfg["teams"][name].get("role", "main"),
            "blurb": cfg["teams"][name].get("blurb", res["settings"]),
            "current": res["squad"], "current_report": res["current_report"],
            "target": res["target"], "target_report": res["target_report"],
            "plan": res["plan"], "hit_policy": res["hit_policy"],
            "chips": res["chips"],
            "free_transfers": res["free_transfers"], "bank": res["bank"],
            "own_current": round(float(df[df.id.isin(res["squad"])].selected_by.mean()), 1),
            "own_target": round(float(df[df.id.isin(res["target"])].selected_by.mean()), 1)
                          if res["target"] else None,
            "paths": [],
        }
    ref = optimize.solve(optimize.prune(df, gws), gws, allow_infeasible=True)
    return {
        "generated": pd.Timestamp.now("UTC").isoformat(),
        "gws": gws,
        "deadline": (ctx.get("next_event") or {}).get("deadline_time", ""),
        "chip_deadline": cfg.get("chip_deadline", "2027-01-02T13:30:00Z"),
        "players": df[df.avail > 0][keep].round(3).to_dict("records"),
        "teams": {v["short"]: {"name": v["name"], "att": round(v["att"], 3),
                              "def": round(v["def"], 3), "promoted": bool(v["promoted"])}
                  for v in teams.values()},
        "fixture_grid": short, "season_grid": season,
        "reference": {"squad": ref["squad"],
                      "report": optimize.squad_report(df, ref["squad"], gws)} if ref else None,
        "builds": builds,
    }


if __name__ == "__main__":
    main()
