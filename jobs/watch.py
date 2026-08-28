"""Hourly watcher: price moves, injury and status news, deadline countdown.

Diffs the live bootstrap against the last snapshot in state/ and only speaks when
something actually changed for a player you own or are watching.

Every run also appends a line to state/price_log.jsonl — a delta-only record of
each element's cost, event net transfers, ownership and availability. That log is
the training data for the price-move prediction engine; the day it starts is the
day calibration becomes possible, so it runs unconditionally, even when nothing
is worth alerting on.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fplbot import api, news as news_mod, notify, pipeline  # noqa: E402
from fplbot.notify import esc  # noqa: E402

PRICE_LOG = Path(__file__).resolve().parent.parent / "state" / "price_log.jsonl"
NEWS_CACHE = Path(__file__).resolve().parent.parent / "state" / "news_cache.json"


def append_price_log(els, prev, gw, h_deadline):
    """Append this run's deltas to state/price_log.jsonl.

    One line per run, holding only the elements whose (cost, tin, tout, own,
    status, chance) tuple moved since the previous run — plus a full snapshot on
    the first line of each UTC day, so a day can always be reconstructed without
    replaying every hourly line. The first line ever is necessarily full.
    """
    now = dt.datetime.now(dt.timezone.utc)
    full = False
    if PRICE_LOG.exists():
        try:
            last_ts = PRICE_LOG.read_text(encoding="utf-8").strip().rsplit("\n", 1)[-1]
            last_day = dt.datetime.fromisoformat(json.loads(last_ts)["ts"][:19]).date()
            full = last_day != now.date()
        except Exception:                            # noqa: BLE001
            full = True
    else:
        full = True

    changed = {}
    for eid, e in els.items():
        rec = {
            "cost": e["now_cost"],
            "tin": e.get("transfers_in_event", 0),
            "tout": e.get("transfers_out_event", 0),
            "own": float(e["selected_by_percent"]),
            "status": e["status"],
            "chance": e.get("chance_of_playing_next_round"),
        }
        old = prev.get(str(eid))
        if full or not old or any(rec[k] != old.get(k) for k in rec):
            changed[str(eid)] = rec
    if not changed and not full:
        return 0

    line = {"ts": now.isoformat(timespec="seconds"), "gw": gw,
            "h_deadline": round(h_deadline, 2) if h_deadline is not None else None,
            "full": full, "elements": changed}
    PRICE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PRICE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")
    return len(changed)


def ensure_news_cache():
    """Scaffold for the news engine: an empty-but-valid cache file."""
    if not NEWS_CACHE.exists():
        NEWS_CACHE.write_text(json.dumps(
            {"sources": {}, "signals": [], "updated": None}), encoding="utf-8")


def status_word(p):
    return {"a": "available", "d": "doubtful", "i": "injured",
            "s": "suspended", "u": "unavailable", "n": "on loan"}.get(p["status"], p["status"])


def news_scan(boot, owned, els):
    """Engine 6: external sources, resolved into per-player alerts.

    Runs here, in the hourly watch job, never in the deadline-critical plan
    job. Returns (alert_lines, n_signals); state/news_signals.json is written
    for the plan job's model.build(news=) to resolve on its own schedule.
    """
    try:
        fetched = news_mod.fetch_all()
    except Exception as e:                       # noqa: BLE001
        print(f"[watch] news scan failed outright: {e}")
        return [], 0
    raw = fetched.get("signals") or []
    news_mod.store_signals(raw)
    if not raw:
        return [], 0

    lines, seen = [], set()
    try:
        resolved = news_mod.resolve_players(news_mod.base_frame(boot), raw)
        risk = dict(zip(resolved.element.astype(int), resolved.news_risk))
        p_start = dict(zip(resolved.element.astype(int), resolved.p_start))
    except Exception as e:                       # noqa: BLE001
        print(f"[watch] news resolution failed: {e}")
        return [], len(raw)

    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    for eid in sorted(owned):
        e = els.get(eid)
        if not e or eid in seen:
            continue
        label = f"{esc(e['web_name'])} ({teams.get(e['team'], '')})"
        ps = p_start.get(eid, 1.0)
        if ps < 0.6:
            row = resolved[resolved.element == eid]
            src = (row["source"].iloc[0] if len(row) and
                   isinstance(row["source"].iloc[0], str) else "scrape")
            lines.append(f"• {label} — scraped news says start unlikely "
                         f"(p_start {ps:.0%}, {src})")
            seen.add(eid)
        elif risk.get(eid, 1.0) < 1.0 and e["status"] == "a":
            # scrape contradicts FPL: flagged doubtful by a source while the
            # API still says available - early warning, clearly labelled
            lines.append(f"• {label} — scrape flags a doubt, FPL still says "
                         f"available (unverified)")
            seen.add(eid)
    return lines[:8], len(raw)


def main():
    cfg = pipeline.load_config()
    boot = api.bootstrap()
    els = {e["id"]: e for e in boot["elements"]}
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}

    owned, watch = set(), set()
    for name, t in cfg["teams"].items():
        try:
            st = api.squad_state(t["entry_id"], boot)
            owned |= set(st.get("picks", []))
        except Exception as e:                       # noqa: BLE001
            print(f"[watch] could not read {name}: {e}")
    prev = pipeline.read_state("players")
    interesting = owned | {int(k) for k, v in prev.items()
                           if float(v.get("selected_by", 0)) >= 5}

    price_lines, news_lines = [], []
    snapshot = {}
    for eid, e in els.items():
        snapshot[str(eid)] = {
            "cost": e["now_cost"], "status": e["status"],
            "news": e["news"], "selected_by": float(e["selected_by_percent"]),
            "chance": e.get("chance_of_playing_next_round"),
            "tin": e.get("transfers_in_event", 0),
            "tout": e.get("transfers_out_event", 0),
        }
        old = prev.get(str(eid))
        if not old:
            continue
        label = f"{esc(e['web_name'])} ({teams.get(e['team'],'')})"

        # prices only matter for players actually held — the game has 600+
        # players and reporting every move in the game is noise
        if e["now_cost"] != old["cost"] and eid in owned:
            arrow = "▲" if e["now_cost"] > old["cost"] else "▼"
            price_lines.append(
                f"{arrow} {label} £{old['cost']/10:.1f}m → £{e['now_cost']/10:.1f}m")
        if e["status"] != old["status"] or (e["news"] or "") != (old.get("news") or ""):
            if eid in interesting:
                news_lines.append(
                    f"• {label} — {status_word(e)}"
                    + (f": {esc(e['news'])}" if e["news"] else "")
                    + (f" ({e['chance_of_playing_next_round']}%)"
                       if e.get("chance_of_playing_next_round") is not None else ""))

    msg = []
    n_signals = 0
    if cfg.get("engines", {}).get("news", {}).get("enabled", True):
        try:
            news_alerts, n_signals = news_scan(boot, owned, els)
            if news_alerts:
                msg.append("📰 <b>News scan</b> (unverified external sources)\n"
                           + "\n".join(news_alerts))
        except Exception as e:                       # noqa: BLE001
            print(f"[watch] news scan unavailable: {e}")
    if price_lines:
        msg.append("💰 <b>Your players — price moves</b>\n" + "\n".join(price_lines[:12]))
    if news_lines:
        msg.append("🚑 <b>Team news</b>\n" + "\n".join(news_lines[:12]))

    nxt = api.next_event(boot)
    h_deadline = None
    if nxt.get("deadline_time"):
        dl = dt.datetime.fromisoformat(nxt["deadline_time"].replace("Z", "+00:00"))
        h_deadline = (dl - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
        hrs = h_deadline
        meta = pipeline.read_state("watch_meta", {"warned_gw": None})
        warned = meta.get("warned_gw") == nxt["id"]
        if 2.0 <= hrs <= 26 and not warned:
            msg.append(f"⏰ <b>Gameweek {nxt['id']} deadline in {hrs:.0f} hours</b> "
                       f"— lineups and captain are set automatically.")
            pipeline.write_state("watch_meta", {"warned_gw": nxt["id"]})

    if msg:
        notify.send("\n\n".join(msg), kind="watch")
    else:
        print("[watch] nothing to report")
    n_logged = append_price_log(els, prev, nxt.get("id"), h_deadline)
    ensure_news_cache()
    print(f"[watch] price log: {n_logged} elements changed, "
          f"{'full snapshot' if n_logged else 'delta-only'}")
    print(f"[watch] news scan: {n_signals} signals")
    pipeline.write_state("players", snapshot)


if __name__ == "__main__":
    main()
