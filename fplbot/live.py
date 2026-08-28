"""Live gameweek state: scores, per-player live vs projected, leagues and cups.

Built by the hourly watch job while a gameweek is in play and written to
site/live.json for the dashboard's Live tab, which refreshes itself every
couple of minutes. This file is a snapshot, not a websocket: its freshness is
stamped on it, and the dashboard says how old it is.

Honest edges, stated here so they stay stated: the live TOTAL per entry comes
straight from FPL (auto-substitutions already applied), but the per-player
rows are computed from the picked XI — a player auto-subbed in can show
points the total does not include. Every "proj" number comes from the same
model the deadline plans use.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import api


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _multiplier(pick, chip):
    """API spells the triple-captain chip "3xc" on current data and "bignum" on older seasons."""
    if pick.get("is_captain"):
        return 3 if chip in ("3xc", "bignum", "tc") else 2
    return 1


def _live_gw(boot):
    """The gameweek being played: deadline passed, provisional results not in."""
    for e in boot["events"]:
        if e.get("is_current"):
            return e
    started = [e for e in boot["events"] if e.get("started") and not e.get("finished")]
    return started[-1] if started else None


def build(boot=None, entry_ids=None, compare=(), bundle=None, max_leagues=6):
    """One live snapshot for all compared entries.

    entry_ids are the bot's own teams (their live picks come from the API),
    compare are extra manager ids (the friend) shown in every mini-league.
    Returns {} when nothing is in play and a pre_deadline snapshot otherwise.
    """
    boot = boot or api.bootstrap()
    ev = _live_gw(boot)
    if not ev:
        return {}
    gw = int(ev["id"])

    fx = [f for f in api.fixtures() if f.get("event") == gw]
    if not fx:
        return {}
    if not any(f.get("started") for f in fx):
        return {"gw": gw, "status": "pre_deadline",
                "generated": _now(), "fixtures": _fx_rows(fx)}

    live_by_id = {e["id"]: (e.get("stats") or {})
                  for e in api.event_live(gw)["elements"]}
    xp_by_id = {p["id"]: p for p in ((bundle or {}).get("players") or [])}

    entries = []
    for eid in list(entry_ids) + list(compare):
        try:
            snap = _entry_live(eid, gw, live_by_id, xp_by_id, ev)
            snap["meta"] = _entry_meta(eid)
            snap["leagues"] = _leagues(eid, max_leagues)
            entries.append(snap)
        except Exception:                                    # noqa: BLE001
            continue
    if not entries:
        return {}

    # mini-league standings, around the entries being compared
    tables = {}
    for lg in (entries[0].get("leagues", {}).get("classic") or [])[:3]:
        t = _league_table(lg["id"], [e["entry_id"] for e in entries])
        if t:
            tables[str(lg["id"])] = t

    return {
        "gw": gw, "generated": _now(), "status": "live",
        "entry_ids": [int(x) for x in (entry_ids or ())],
        "teams": {t["id"]: t["short_name"] for t in boot["teams"]},
        "fixtures": _fx_rows(fx),
        "entries": entries,
        "leagues": tables,
    }


def _fx_rows(fixtures):
    return [{
        "id": f["id"], "home": f["team_h"], "away": f["team_a"],
        "hs": f.get("score_h"), "as": f.get("score_a"),
        "started": bool(f.get("started")), "finished": bool(f.get("finished")),
    } for f in fixtures]


def _entry_live(entry_id, gw, live_by_id, xp_by_id, event):
    """Live + projected rows for one entry; the live total is FPL's own."""
    picks = api.entry_picks(entry_id, gw)
    e = api.entry_event(entry_id, gw)
    chip = e.get("active_chip")
    players = []
    proj_final = 0.0
    for p in picks["picks"]:
        eid = p["element"]
        st = live_by_id.get(eid, {})
        raw = float(st.get("total_points") or 0.0)
        minutes = int(st.get("minutes") or 0)
        mult = _multiplier(p, chip)
        info = xp_by_id.get(eid, {})
        xp = float(info.get(f"xp{gw}") or 0.0)
        # yet to feature: count the model's projection, not zero
        if minutes > 0:
            final = raw
        else:
            final = xp
        players.append({
            "id": eid,
            "name": info.get("name", info.get("full_name", f"#{eid}")),
            "pos": info.get("pos", ""), "team": info.get("team", ""),
            "xi": p["position"] <= 11,
            "minutes": minutes,
            "live": round(raw * mult, 1),
            "proj_final": round(final * mult, 2),
            "captain": bool(p.get("is_captain")),
        })
        # bench players count too - they can still autosub in
        proj_final += final * mult
    return {
        "entry_id": entry_id,
        "name": e.get("entry_name") or picks.get("entryname") or f"entry {entry_id}",
        "gw": gw,
        "live_pts": (e.get("points") or {}).get("total"),
        "proj_final": round(proj_final, 1),
        "chip": chip,
        "players": players,
    }


def _entry_meta(entry_id):
    """Overall rank / points as of the last settled gameweek, plus a delta."""
    try:
        hist = api.entry_history(entry_id)["current"]
    except Exception:                                        # noqa: BLE001
        return {"name": f"entry {entry_id}"}
    if not hist:
        return {"name": f"entry {entry_id}"}
    last = hist[-1]
    prev = hist[-2] if len(hist) > 1 else None
    return {
        "overall_pts": last.get("total_points"),
        "overall_rank": last.get("overall_rank"),
        "prev_rank": prev.get("overall_rank") if prev else None,
        "last_gw": last.get("event_points"),
        "season": last.get("season_name") or "",
    }


def _leagues(entry_id, max_classic):
    """The classic leagues and cup this entry is in, dashboard-shaped."""
    out = {"classic": [], "h2h": [], "cups": []}
    try:
        lg = (api.entry(entry_id).get("leagues") or {})
        for c in (lg.get("classic") or [])[:max_classic]:
            out["classic"].append({
                "id": c["id"], "name": c["name"], "rank": c.get("entry_rank"),
                "move": c.get("entry_movement"),
                "last_rank": c.get("entry_last_rank"),
                "size": c.get("league_size")})
        for c in (lg.get("h2h") or [])[:3]:
            out["h2h"].append({
                "id": c["id"], "name": c["name"], "rank": c.get("entry_rank"),
                "size": c.get("league_size")})
        cup = _cup(entry_id)
        if cup:
            out["cups"].append(cup)
    except Exception:                                        # noqa: BLE001
        pass
    return out


def _cup(entry_id):
    """This entry's classic cup state, or None before/after the cup."""
    try:
        cup = api.entry_cup(entry_id)
    except Exception:                                        # noqa: BLE001
        return None
    if not cup or not cup.get("status") or cup["status"] == "n":
        return None
    return {
        "name": (cup.get("league") or {}).get("name", "Classic cup"),
        "round": cup.get("current_round"),
        "status": cup.get("status"),         # n = not entered, a = active, o = out
        "state": cup.get("state"),
    }


def _league_table(league_id, entry_ids, max_pages=6):
    """One classic league as {name, rows}: the compared entries plus context.

    Pages through until every compared entry's rank is covered (ranks come
    ordered, so one page per entry's position suffices) - capped at max_pages
    keeps the watch job's API budget honest.
    """
    want = set(entry_ids)
    name, rows, seen = None, [], set()
    for page in range(1, max_pages + 1):
        try:
            data = api.league_classic(league_id, page)
        except Exception:                                    # noqa: BLE001
            break
        name = name or ((data.get("league") or {}).get("name"))
        stand = ((data.get("standings") or {}).get("results")) or []
        for r in stand:
            rows.append({"entry": r["entry"], "manager": r["entry_name"],
                         "player": r["player_name"], "rank": r["rank"],
                         "pts": r["total"], "last": r["event_total"],
                         "mine": r["entry"] in want})
            seen.add(r["entry"])
        if want.issubset(seen) or not stand:
            break
    return {"name": name or f"league {league_id}", "rows": rows} if rows else None