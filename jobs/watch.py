"""Hourly watcher: price moves, injury and status news, deadline countdown.

Diffs the live bootstrap against the last snapshot in state/ and only speaks when
something actually changed for a player you own or are watching.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fplbot import api, notify, pipeline  # noqa: E402
from fplbot.notify import esc  # noqa: E402

# transfer momentum at which a price change becomes likely
RISE_ALERT = 0.85
FALL_ALERT = -0.85


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
        label = f"{esc(e['web_name'])} ({teams.get(e['team'],'')}, £{e['now_cost']/10:.1f}m)"
        mine = " ★" if eid in owned else ""

        if e["now_cost"] != old["cost"]:
            arrow = "▲" if e["now_cost"] > old["cost"] else "▼"
            price_lines.append(
                f"{arrow} {label}{mine} — was £{old['cost']/10:.1f}m")
        if e["status"] != old["status"] or (e["news"] or "") != (old.get("news") or ""):
            if eid in interesting:
                news_lines.append(
                    f"• {label}{mine} — {status_word(e)}"
                    + (f": {esc(e['news'])}" if e["news"] else "")
                    + (f" ({e['chance_of_playing_next_round']}% chance)"
                       if e.get("chance_of_playing_next_round") is not None else ""))

    # price-change pressure among owned players, before the 00:30 UK update
    pressure = []
    for eid in sorted(owned):
        e = els.get(eid)
        if not e:
            continue
        tin, tout = e.get("transfers_in_event", 0), e.get("transfers_out_event", 0)
        net = tin - tout
        denom = max(tin + tout, 1)
        score = net / denom
        if abs(score) >= RISE_ALERT and denom > 20000:
            pressure.append(
                f"{'▲ likely rise' if score > 0 else '▼ likely fall'}: "
                f"{esc(e['web_name'])} ({teams.get(e['team'],'')}) — net {net:+,}")

    msg = []
    if price_lines:
        msg.append("<b>Price changes</b>\n" + "\n".join(price_lines[:25]))
    if news_lines:
        msg.append("<b>Team news</b>\n" + "\n".join(news_lines[:25]))
    if pressure:
        msg.append("<b>Price pressure on your players</b>\n" + "\n".join(pressure[:15]))

    nxt = api.next_event(boot)
    if nxt.get("deadline_time"):
        dl = dt.datetime.fromisoformat(nxt["deadline_time"].replace("Z", "+00:00"))
        hrs = (dl - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
        if 1.5 < hrs <= 2.5:
            msg.append(f"⏰ <b>Gameweek {nxt['id']} deadline in {hrs:.1f} hours</b> — "
                       f"last check on lineups and captain.")

    if msg:
        notify.send("\n\n".join(msg))
    else:
        print("[watch] nothing to report")
    pipeline.write_state("players", snapshot)


if __name__ == "__main__":
    main()
