"""Hourly watcher: price moves, injury and status news, deadline countdown.

Diffs the live bootstrap against the last snapshot in state/ and only speaks when
something actually changed for a player you own or are watching.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fplbot import api, notify, pipeline  # noqa: E402
from fplbot.notify import esc  # noqa: E402


def status_word(p):
    return {"a": "available", "d": "doubtful", "i": "injured",
            "s": "suspended", "u": "unavailable", "n": "on loan"}.get(p["status"], p["status"])


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
    if price_lines:
        msg.append("💰 <b>Your players — price moves</b>\n" + "\n".join(price_lines[:12]))
    if news_lines:
        msg.append("🚑 <b>Team news</b>\n" + "\n".join(news_lines[:12]))

    nxt = api.next_event(boot)
    if nxt.get("deadline_time"):
        dl = dt.datetime.fromisoformat(nxt["deadline_time"].replace("Z", "+00:00"))
        hrs = (dl - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
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
    pipeline.write_state("players", snapshot)


if __name__ == "__main__":
    main()
