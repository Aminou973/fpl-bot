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

from fplbot import api, chips, dashboard, history, notify, optimize, pipeline  # noqa: E402
from fplbot.notify import esc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# Windows consoles default to cp1252 and crash on the arrows/accents in the
# briefs; Linux (Actions) is already UTF-8, so this only patches what needs it.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def fmt_move(df, ids):
    if not ids:
        return "none"
    r = df.set_index("id")
    return ", ".join(f"{r.loc[i, 'name']} (£{r.loc[i, 'price']:.1f})" for i in ids)


def brief(ctx, results, cfg):
    """Compact per-team plan message: what to do this week, nothing more."""
    df, gws = ctx["df"], ctx["gws"]
    r = df.set_index("id")
    nxt = ctx.get("next_event") or {}
    dl = nxt.get("deadline_time", "")
    if dl:
        d = dt.datetime.fromisoformat(dl.replace("Z", "+00:00"))
        dl = d.strftime("%a %d %b, %H:%M UTC")
    out = [f"📋 <b>GW{gws[0]} plan</b>" + (f" · deadline {dl}" if dl else "")]

    for name, res in results.items():
        if "error" in res:
            out.append(f"\n<b>{esc(name)}</b> — ⚠️ {esc(res['error'])}")
            continue
        wk = res["plan"]["weeks"][0]
        lines = [f"\n<b>{esc(name)}</b> · {res['free_transfers']} FT · "
                 f"£{res['bank']:.1f}m bank"]
        if wk["out"]:
            for i in wk["out"]:
                lines.append(f"▼ OUT {esc(r.loc[i, 'name'])} ({r.loc[i, 'team']})")
            for i in wk["in"]:
                lines.append(f"▲ IN  {esc(r.loc[i, 'name'])} "
                             f"({r.loc[i, 'team']}, £{r.loc[i, 'price']:.1f}m)")
            if wk["hits"]:
                lines.append(f"Cost −{wk['hits'] * 4} pts ({wk['hits']} hit) "
                             f"— gains {res['hit_policy'].get('gain_over_no_hit')} pts")
        else:
            roll = min(5, res["free_transfers"] + 1)
            lines.append(f"↻ No transfer — FT rolls ({roll} next week)")
        cap_line = (f"⚽ Captain <b>{esc(r.loc[wk['captain'], 'name'])}</b> "
                    f"({r.loc[wk['captain'], 'team']})")
        if wk.get("vice") in r.index:
            cap_line += f" · Vice {esc(r.loc[wk['vice'], 'name'])}"
        lines.append(cap_line)
        flagged = [f"{r.loc[i, 'name']} ({r.loc[i, 'news'] or 'flagged'})"
                   for i in res["squad"]
                   if isinstance(r.loc[i, "status"], str) and r.loc[i, "status"] != "a"]
        if flagged:
            lines.append("⚠️ " + esc("; ".join(flagged)))
        lines.append(f"Projected <b>{wk['xp']:.1f}</b> this week")
        out.append("\n".join(lines))

    site = cfg.get("site_url")
    if site:
        out.append(f"\n{site}")
    return "\n".join(out)


def brief_signature(results):
    """Whether the plan actually changed — out/in/captain/hits per team."""
    sig = []
    for name, res in results.items():
        if "error" in res:
            sig.append([name, "error", str(res["error"])])
            continue
        wk = res["plan"]["weeks"][0]
        sig.append([name, sorted(wk["out"]), sorted(wk["in"]),
                    wk["captain"], wk.get("vice"), wk["hits"]])
    return json.dumps(sig, sort_keys=True)


def last_plan_entry(df, res):
    """Everything an auto-submit job needs to act on the plan unsupervised.

    ``picks_payload`` is the exact 15-entry list the FPL my-team endpoint
    expects: the XI first in slot order, then the bench, with the plan's
    captain and vice applied. Kept here so the submit job and the planner
    can never disagree about ordering rules.
    """
    r = df.set_index("id")
    wk = res["plan"]["weeks"][0]
    pos_rank = {"GKP": 0, "DEF": 1, "MID": 2, "FWD": 3}
    rank = lambda i: (pos_rank.get(r.loc[i, "pos"], 9), -r.loc[i, "price"])  # noqa: E731
    xi = sorted(wk.get("xi", []), key=rank)
    # the squad that matters here is the one after this week's transfers land
    after = [i for i in wk.get("squad", []) if i not in set(wk.get("out", []))]
    bench = sorted([i for i in after if i not in set(xi)], key=rank)
    captain = wk.get("captain")
    vice = wk.get("vice")
    payload = []
    for i in xi + bench:
        payload.append({"element": int(i), "position": len(payload) + 1,
                        "is_captain": i == captain, "is_vice": i == vice})
    return {
        "entry": res.get("entry_id"),
        "in": wk.get("in", []), "out": wk.get("out", []),
        "squad": res["squad"], "squad_after": after,
        "xi": xi, "bench": bench,
        "captain": captain, "vice": vice,
        "hits": wk.get("hits", 0),
        "squad_source": res.get("squad_source"),
        "picks_payload": payload,
    }


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

    # Far from a deadline there is no transfer advice worth pushing to a phone,
    # but the results of the gameweek that just ended very much are worth
    # publishing. So the run continues either way and only the Telegram brief is
    # held back: the dashboard refreshes three times a day all week.
    quiet = False
    if not a.offline:
        nxt = api.next_event(ctx["bootstrap"])
        ctx["next_event"] = nxt
        if not a.force and nxt.get("deadline_time"):
            d = dt.datetime.fromisoformat(nxt["deadline_time"].replace("Z", "+00:00"))
            hrs = (d - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
            if hrs > float(cfg.get("plan_window_hours", 40)) or hrs < 0:
                quiet = True
                print(f"[plan] deadline {hrs:.1f}h away — publishing results only")

    results = {}
    for name, t in cfg["teams"].items():
        state = {"picks": [], "picks_source": None,
                 "free_transfers": t.get("free_transfers", 1),
                 "bank": t.get("bank", 0.0)}
        if not a.offline and t.get("entry_id"):
            try:
                live = api.squad_state(t["entry_id"], ctx["bootstrap"])
                if live.get("picks"):
                    state = live
                    print(f"[plan] live squad for {name}: "
                          f"{len(live['picks'])} picks "
                          f"(source {live.get('picks_source')})")
                else:
                    print(f"[plan] live squad for {name} returned no picks "
                          f"({live.get('picks_error')}); using config fallback")
                state.setdefault("bank", 0.0)
                if t.get("free_transfers") is not None:
                    # config pin wins over the recomputed count: the game's own
                    # screen is the authority on how many FTs are available
                    # (e.g. a season where unused FTs do not bank)
                    state["free_transfers"] = int(t["free_transfers"])
                    print(f"[plan] free transfers pinned to "
                          f"{state['free_transfers']} by config")
            except Exception as e:                   # noqa: BLE001
                print(f"[plan] live squad for {name} unavailable ({e}); using config")
        results[name] = pipeline.plan_team(ctx, t, state)
        results[name].setdefault("entry_id", t.get("entry_id"))

    prev = {}
    prev_path = ROOT / "site" / "bundle.json"
    if prev_path.exists():
        try:
            prev = json.loads(prev_path.read_text())
        except (ValueError, OSError):
            prev = {}

    bundle = build_bundle(ctx, results, cfg)
    bundle["changes"] = diff_since(prev, bundle, results)

    # the submitter's audit log, so the dashboard can show its own state
    automation = {"apply_window": 36, "ft_pin": any(
        t.get("free_transfers") is not None for t in cfg["teams"].values())}
    sub = pipeline.read_state("auto_submit", {"gws": {}})
    last_gw = max(sub.get("gws", {}), key=int, default=None)
    if last_gw is not None:
        automation["submit"] = sub["gws"][last_gw]
    bundle["automation"] = automation

    # chips are once-a-season decisions, so they get their own full-season pass
    try:
        long_h = 39 - gws[0]
        ldf, _, _, lgws = pipeline.long_projection(ctx, long_h)
        squads = {n: r["squad"] for n, r in results.items() if "error" not in r}
        caps = {n: cfg["teams"][n].get("max_captain_ownership") for n in squads}
        win = api.chip_windows(ctx["bootstrap"]) if not a.offline else None
        bundle["chip_calendar"] = chips.calendar(ldf, lgws, squads, caps, windows=win)
        ctx["chip_calendar"] = bundle["chip_calendar"]
    except Exception as e:                              # noqa: BLE001
        print(f"[plan] chip calendar unavailable: {e}")
        bundle["chip_calendar"] = None
    if not a.offline:
        entries = {n: t.get("entry_id") for n, t in cfg["teams"].items()}
        bundle["history"] = history.build(ROOT, ctx["bootstrap"], entries,
                                          df=df, gw=gws[0], fx=ctx.get("fx"))
    else:
        bundle["history"] = {"teams": {}, "accuracy": [], "settled": [],
                             "provisional": []}
    (ROOT / "site").mkdir(exist_ok=True)
    (ROOT / "site" / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    dashboard.build(ROOT / "site" / "bundle.json", ROOT / "site" / "index.html")
    pipeline.write_state("last_plan", {
        "gw": gws[0], "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "deadline": (ctx.get("next_event") or {}).get("deadline_time", ""),
        "teams": {name: last_plan_entry(df, res)
                  for name, res in results.items() if "error" not in res}})

    # A week first reported while provisional is reported once more when the
    # game confirms it, in case bonus moved anything.
    told = pipeline.read_state("reported", {"gws": [], "final": []})
    prov = set(bundle["history"].get("provisional") or [])
    seen, final = set(told.get("gws", [])), set(told.get("final", []))
    done = [g for g in (bundle["history"].get("settled") or [])
            if g not in seen or (g not in prov and g not in final)]
    if done and not a.offline:
        rtext = results_brief(bundle["history"], max(done), cfg)
        print(rtext)
        if not a.no_notify and rtext:
            notify.send(rtext, kind="alert")
        pipeline.write_state("reported", {
            "gws": sorted(seen | set(done)),
            "final": sorted(final | {g for g in done if g not in prov})})

    text = brief(ctx, results, cfg)
    print(text)
    # send only when the plan itself changed, and only inside the deadline
    # window: three runs a day of identical text is noise, not information
    sig = brief_signature(results)
    told = pipeline.read_state("plan_brief", {"gw": None, "sig": None})
    unchanged = told.get("gw") == gws[0] and told.get("sig") == sig
    if quiet:
        print("[plan] outside the deadline window — brief printed, not sent")
    elif not a.no_notify:
        if unchanged:
            print("[plan] plan unchanged since the last send — not sent")
        else:
            notify.send(text, kind="alert")
    if not unchanged:
        pipeline.write_state("plan_brief", {"gw": gws[0], "sig": sig})


def results_brief(hist, gw, cfg):
    """What actually happened last gameweek, for both teams, plus model accuracy."""
    prov = gw in (hist.get("provisional") or [])
    lines = [f"📊 <b>GW{gw} results</b>"
             + (" · provisional" if prov else "")]
    for name, series in (hist.get("teams") or {}).items():
        wk = next((w for w in series.get("weeks", []) if w["gw"] == gw), None)
        if not wk:
            continue
        avg = wk.get("average")
        vs = f" · field {avg} ({wk['net'] - avg:+d})" if avg else ""
        rank = f"{wk['overall_rank']:,}" if wk.get("overall_rank") else "—"
        delta = wk.get("rank_delta")
        move = f", {'▲' if delta > 0 else '▼'}{abs(delta):,}" if delta else ""
        lines.append(f"\n<b>{esc(name)}</b> — <b>{wk['net']}</b> pts{esc(vs)}"
                     f"\nRank {esc(rank)}{esc(move)}")
    acc = next((g for g in (hist.get("accuracy") or []) if g["gw"] == gw), None)
    if acc:
        lines.append(f"\nModel error {acc['mae']} pts ({acc['n']} players)")
    site = cfg.get("site_url")
    if site:
        lines.append(f"\n{site}")
    return "\n".join(lines) if len(lines) > 1 else ""


def diff_since(prev, cur, results):
    """What moved since the last run: prices, availability, and plan reversals."""
    if not prev.get("players"):
        return {"first_run": True, "prices": [], "news": [], "plan": []}
    old = {p["id"]: p for p in prev["players"]}
    prices, news = [], []
    for p in cur["players"]:
        o = old.get(p["id"])
        if not o:
            continue
        if abs(p["price"] - o["price"]) > 1e-6:
            prices.append({"name": p["name"], "team": p["team"], "pos": p["pos"],
                           "from": o["price"], "to": p["price"],
                           "owned": p["id"] in _owned(results)})
        if (p.get("status") != o.get("status")) or ((p.get("news") or "") != (o.get("news") or "")):
            news.append({"name": p["name"], "team": p["team"], "pos": p["pos"],
                         "status": p.get("status"), "note": p.get("news") or "",
                         "owned": p["id"] in _owned(results)})
    plan = []
    for name, res in results.items():
        if "error" in res:
            continue
        now_in = set(res["plan"]["weeks"][0]["in"])
        was = prev.get("builds", {}).get(name, {}).get("plan", {})
        was_in = set((was.get("weeks") or [{}])[0].get("in", []))
        if was_in and now_in != was_in:
            plan.append({"team": name,
                         "added": sorted(now_in - was_in),
                         "dropped": sorted(was_in - now_in)})
    return {"first_run": False, "prices": prices[:40], "news": news[:40], "plan": plan}


def _owned(results):
    out = set()
    for res in results.values():
        out |= set(res.get("squad") or [])
    return out


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

    # every player is published, not only the available ones: an owned player
    # who is injured must still render on the pitch (flagged), never vanish
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
            "current": res["squad"], "squad_source": res.get("squad_source"),
            "current_report": res["current_report"],
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
        "players": df[keep].round(3).to_dict("records"),
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
