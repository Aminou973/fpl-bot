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

from fplbot import api, chips, dashboard, elite as elite_mod, history, notify, optimize, pipeline  # noqa: E402
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
            for pp in (res.get("price_pred") or [])[:2]:
                if pp["conf"] >= 0.3:
                    lines.append(f"⏫ {esc(r.loc[pp['element'], 'name'])} may "
                                 f"rise before the deadline (conf {pp['conf']:.0%})")
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
        cp = res.get("chip_play")
        if cp:
            how = ("the bot plays it at the deadline"
                   if cp["chip"] == "wildcard"
                   else "play it manually — it is alert-only for now")
            lines.append(
                f"🃏 <b>{esc(cp['chip'].upper())} suggested</b> for GW{cp['gw']} "
                f"(+{cp['gain']:.1f} xp over the horizon) — {how}")
        out.append("\n".join(lines))

    site = cfg.get("site_url")
    if site:
        out.append(f"\n{site}")
    return "\n".join(out)


def chip_alerts(ctx, results, cfg):
    """Chip recommendations that have come due, as alert-tier messages.

    The bot never plays a chip itself — they are irreversible — so the best
    it can do is ring when the plan says this (or next) week is the window.
    Each team+chip+gameweek combination is announced exactly once, tracked
    in state so the three-times-a-day plan runs cannot repeat it.
    """
    cal = ctx.get("chip_calendar") or {}
    picks = (cal.get("picks") or {})
    if not picks:
        return []
    gws = ctx["gws"]
    half = "first" if cal.get("split", 20) > gws[0] else "second"
    label = {"triple_captain": "Triple Captain", "bench_boost": "Bench Boost",
             "wildcard": "Wildcard", "free_hit": "Free Hit"}
    told = pipeline.read_state("chip_alerts", {"sent": []})
    sent = set(told.get("sent", []))

    lines = []
    now_gw, next_gw = gws[0], (gws[1] if len(gws) > 1 else None)
    for name, per_half in picks.items():
        if name not in results or "error" in results.get(name):
            continue
        for chip, options in (per_half.get(half) or {}).items():
            best = options[0] if options else None
            if not best:
                continue
            bgw = best.get("gw")
            when = ("this week" if bgw == now_gw
                    else f"next week (GW{bgw})" if bgw == next_gw else None)
            if not when:
                continue
            key = f"{name}|{chip}|{bgw}|{'now' if bgw == now_gw else 'next'}"
            if key in sent:
                continue
            sent.add(key)
            why = {"triple_captain": f"best captain window — {best.get('player')} "
                                     f"(+{best.get('value', 0):.1f} expected)",
                   "bench_boost": f"best bench window — bench worth "
                                  f"+{best.get('value', 0):.1f} expected"
                                  + (", historically a double week"
                                     if best.get("p_double") else ""),
                   "wildcard": f"best rebuild window — squad gap "
                               f"+{best.get('value', 0):.1f} above your median"
                               + (f", plus likely doubles to capture "
                                  f"(+{best.get('capture', 0):.1f})"
                                  if best.get("capture") else ""),
                   "free_hit": "best blank insurance — flagged blank-week risk"
                   }.get(chip, f"value {best.get('value')}")
            lines.append(f"🎯 <b>{esc(name)}</b> — {label.get(chip, chip)} "
                         f"is best {when}: {esc(why)}")

    alerts = []
    if lines:
        alerts.append("🎯 <b>Chip window"
                      + ("s" if len(lines) > 1 else "") + "</b>\n\n"
                      + "\n".join(lines)
                      + "\n\n<i>Only chips listed under a team's "
                        "chips_auto are played by the bot; the rest are "
                        "yours to play before the deadline.</i>")
    pipeline.write_state("chip_alerts", {"sent": sorted(sent)})
    return alerts


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
    # engine 7: if the planner armed a chip for this week, its ILP week is the
    # plan — the wildcard's rebuild replaces the transfer plan wholesale
    cp = res.get("chip_play")
    wk_chip = wk.get("chip")
    if cp and cp["chip"] == "wildcard" and cp.get("week"):
        wk = cp["week"]
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
        "chip": (cp or {}).get("chip") if cp and cp.get("week") else wk_chip,
        # a Tier A chip (TC/BB) is decided inside the ILP, so its value lives
        # in res["tier_a_gain"] rather than on a chip_play branch - report
        # whichever applies, so the bot never plays a chip without saying what
        # it thought the chip was worth
        "chip_gain": ((cp or {}).get("gain") if cp and cp.get("week")
                      else res.get("tier_a_gain")),
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

    # engine 1b: sample the world's top managers before planning, so
    # rank.elite_weight squads chase the elite template as it stands right now
    elite = None
    if not a.offline:
        try:
            elite = elite_mod.build(boot=ctx["bootstrap"], plan_gw=gws[0])
            print(f"[plan] elite template sampled: "
                  f"{(elite or {}).get('sampled', 0)} of the top "
                  f"{(elite or {}).get('league', '')}") if elite else \
                print("[plan] elite sample too thin - planner uses field ownership")
            if elite:
                pipeline.write_state("elite", elite)
        except Exception as e:                              # noqa: BLE001
            print(f"[plan] elite template unavailable: {e}")

    # Live squad state for every team FIRST. The season chip calendar is built
    # from these squads before any planning happens, so the chip gates inside
    # plan_team can see all 36 remaining gameweeks instead of just the
    # 5-gameweek planning horizon. (It used to be computed after the loop,
    # which is why the gates could only ever compare the next five weeks.)
    states = {}
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
        states[name] = state

    # the full-season chip pass, now BEFORE planning so the gates can use it
    try:
        long_h = 39 - gws[0]
        ldf, _, _, lgws = pipeline.long_projection(ctx, long_h)
        live_squads = {}
        for name, t in cfg["teams"].items():
            sq = pipeline.resolve_squad(
                df, states[name].get("picks"),
                [tuple(x) for x in t.get("squad", [])])
            if len(sq) == 15:
                live_squads[name] = sq
        caps = {n: cfg["teams"][n].get("max_captain_ownership") for n in live_squads}
        win = api.chip_windows(ctx["bootstrap"]) if not a.offline else None
        ctx["chip_calendar"] = chips.calendar(ldf, lgws, live_squads, caps,
                                              windows=win)
        print(f"[plan] chip calendar built over {len(lgws)} gameweeks "
              f"(GW{lgws[0]}-{lgws[-1]}) - chip gates can see the whole season")
    except Exception as e:                              # noqa: BLE001
        print(f"[plan] chip calendar unavailable: {e}")
        ctx["chip_calendar"] = None

    results = {}
    for name, t in cfg["teams"].items():
        results[name] = pipeline.plan_team(ctx, t, states[name], name=name)
        results[name].setdefault("entry_id", t.get("entry_id"))

    prev = {}
    prev_path = ROOT / "site" / "bundle.json"
    if prev_path.exists():
        try:
            prev = json.loads(prev_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            prev = {}

    bundle = build_bundle(ctx, results, cfg)
    bundle["changes"] = diff_since(prev, bundle, results)
    bundle["elite"] = elite

    # the submitter's audit log, so the dashboard can show its own state
    automation = {"apply_window": 36, "ft_pin": any(
        t.get("free_transfers") is not None for t in cfg["teams"].values())}
    sub = pipeline.read_state("auto_submit", {"gws": {}})
    last_gw = max(sub.get("gws", {}), key=int, default=None)
    if last_gw is not None:
        automation["submit"] = sub["gws"][last_gw]
    bundle["automation"] = automation
    bundle["price_pred"] = price_predictions(ctx)
    # engine grading files, inlined so the single-file dashboard can show them
    for key, fname in (("price_eval", "price_eval.json"),
                       ("news_eval", "news_eval.json")):
        f = ROOT / "data" / "backtest" / fname
        bundle[key] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    # the calendar was already built above (on the live squads) so the chip
    # gates could consult it; the dashboard shows that same one rather than
    # paying for a second full-season pass
    bundle["chip_calendar"] = ctx.get("chip_calendar")
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

    # chips are irreversible, so the bot never plays one — it rings instead,
    # once per team+chip+gameweek, when the calendar says the window is now
    for alert in chip_alerts(ctx, results, cfg):
        print(alert)
        if not quiet and not a.no_notify:
            notify.send(alert, kind="alert")


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
    owned = _owned(results)          # hoisted: was rebuilt once per player
    prices, news = [], []
    for p in cur["players"]:
        o = old.get(p["id"])
        if not o:
            continue
        if abs(p["price"] - o["price"]) > 1e-6:
            prices.append({"name": p["name"], "team": p["team"], "pos": p["pos"],
                           "from": o["price"], "to": p["price"],
                           "owned": p["id"] in owned})
        if (p.get("status") != o.get("status")) or ((p.get("news") or "") != (o.get("news") or "")):
            news.append({"name": p["name"], "team": p["team"], "pos": p["pos"],
                         "status": p.get("status"), "note": p.get("news") or "",
                         "owned": p["id"] in owned})
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


def price_predictions(ctx, limit=10):
    """Top price-move predictions for the dashboard; empty when the engine is dark.

    "Dark" includes engines.price.enabled: false - the panel used to predict
    regardless of the switch, so a disabled engine still published its numbers
    to the dashboard.
    """
    from fplbot import price as price_mod
    if not ((pipeline.load_config().get("engines") or {})
            .get("price") or {}).get("enabled"):
        return []
    try:
        preds = price_mod.predict(price_mod.read_log())
    except Exception:
        return []
    if not len(preds):
        return []
    r = ctx["df"].set_index("id")
    out = []
    for _, p in preds.sort_values("p_rise", ascending=False).head(limit).iterrows():
        eid = int(p.element)
        if eid in r.index:
            out.append({"id": eid, "name": r.loc[eid, "name"],
                        "team": r.loc[eid, "team"], "pos": r.loc[eid, "pos"],
                        "price": float(p.price),
                        "own": float(r.loc[eid, "selected_by"])
                        if "selected_by" in ctx["df"].columns else None,
                        "p_rise": round(float(p.p_rise), 3),
                        "p_fall": round(float(p.p_fall), 3),
                        "conf": round(float(p.conf), 3)})
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
            # which deadline's confirmed picks the squad view shows ("gw12"):
            # before the deadline FPL has not published this week's squad yet,
            # so the page can flag the bot's applied changes as pending
            "picks_source": res.get("picks_source"),
            "current_report": res["current_report"],
            "target": res["target"], "target_report": res["target_report"],
            "plan": res["plan"], "hit_policy": res["hit_policy"],
            "chips": res["chips"],
            "chip_play": res.get("chip_play"),
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
