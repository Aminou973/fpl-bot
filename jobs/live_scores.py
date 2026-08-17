"""Live gameweek tracker: points, provisional bonus and rank, while matches run.

Only speaks when something changed, so it can run every few minutes without
turning into noise. Bonus is computed from BPS the same way FPL does it, because
the official bonus field stays at zero until a match is finalised.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fplbot import api, notify, pipeline  # noqa: E402
from fplbot.notify import esc  # noqa: E402


def provisional_bonus(live, fixtures_in_play):
    """Top three BPS in each unfinished match get 3, 2, 1 — ties share."""
    bonus = {}
    for fid in fixtures_in_play:
        rows = []
        for el in live.get("elements", []):
            for ex in el.get("explain", []) or []:
                if ex.get("fixture") == fid:
                    rows.append((el["id"], el.get("stats", {}).get("bps", 0)))
                    break
        if not rows:
            continue
        rows.sort(key=lambda r: -r[1])
        ranks, seen = [], []
        for eid, bps in rows:
            if bps <= 0:
                continue
            if bps not in seen:
                seen.append(bps)
            ranks.append((eid, seen.index(bps)))
        for eid, tier in ranks:
            pts = {0: 3, 1: 2, 2: 1}.get(tier)
            if pts:
                bonus[eid] = bonus.get(eid, 0) + pts
    return bonus


def main():
    cfg = pipeline.load_config()
    boot = api.bootstrap()
    fx = api.fixtures()
    gw = api.current_event(boot)
    if not gw:
        print("[live] no current gameweek")
        return

    in_play = [m for m in fx if m.get("event") == gw and m.get("started")
               and not m.get("finished_provisional")]
    done_today = [m for m in fx if m.get("event") == gw and m.get("finished_provisional")]
    if not in_play and not done_today:
        print("[live] nothing kicked off yet")
        return

    live = api.event_live(gw)
    stats = {el["id"]: el.get("stats", {}) for el in live.get("elements", [])}
    els = {e["id"]: e for e in boot["elements"]}
    prov = provisional_bonus(live, [m["id"] for m in in_play])

    prev = pipeline.read_state("live")
    msg, snapshot = [], {"gw": gw, "teams": {}}
    for name, t in cfg["teams"].items():
        if not t.get("entry_id"):
            continue
        try:
            picks = api.entry_picks(t["entry_id"], gw)
        except Exception as e:                       # noqa: BLE001
            print(f"[live] picks unavailable for {name}: {e}")
            continue
        total, played, lines = 0, 0, []
        for p in picks["picks"]:
            if p["multiplier"] == 0:
                continue
            s = stats.get(p["element"], {})
            pts = s.get("total_points", 0) + prov.get(p["element"], 0)
            total += pts * p["multiplier"]
            if s.get("minutes", 0) > 0:
                played += 1
            if pts >= 6:
                lines.append(f"  {esc(els[p['element']]['web_name'])} "
                             f"{pts}{'×' + str(p['multiplier']) if p['multiplier'] > 1 else ''}")
        hits = picks.get("entry_history", {}).get("event_transfers_cost", 0)
        total -= hits
        snapshot["teams"][name] = total
        before = (prev.get("teams") or {}).get(name)
        if before is None or before != total:
            block = [f"<b>{esc(name)}</b> — {total} pts, {played}/11 played"
                     + (f" (−{hits} hits)" if hits else "")]
            block += lines[:6]
            msg.append("\n".join(block))

    if msg:
        notify.send(f"<b>Gameweek {gw} live</b>\n\n" + "\n\n".join(msg)
                    + "\n\n<i>Bonus is provisional until matches are finalised.</i>",
                    silent=True)
    else:
        print("[live] no change")
    pipeline.write_state("live", snapshot)


if __name__ == "__main__":
    main()
