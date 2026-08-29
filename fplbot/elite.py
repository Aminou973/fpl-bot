"""The elite template: what the world's top-ranked managers actually hold.

The global Overall league (id 314) publishes its standings pages, and any
manager's squad is public once their entry id is known — so each plan run
samples the top of the world ranking, reads the squads they intend for the
next deadline, and turns that into an elite ownership share. Planned around
the upcoming deadline rather than last weekend: the template that matters is
the one the elite are walking into.

Why a second ownership number: the field's `selected_by` is a crowd average
dragged by casual managers; the top managers move earlier and more
deliberately, so a player held by 30% of the elite can be the real template
a week before the field catches up. Teams point at it with `rank.elite_weight`
in config, which blends the two shares (0 = field only, 1 = elite only).
Blended into `fplbot.planner`'s template tilt for both teams.

Honest edges, stated here so they stay stated: the sample is one page (50
entries) of one league; squads are read for the most recent gameweek the API
will expose for other managers — intended squads for a future deadline stay
private until its picks open, so the snapshot can trail the moves top
managers make at the last hour; entry data can fail per manager and those
are skipped, not faked; and if too few elite squads are readable the module
returns None and the planner silently runs on the field's ownership alone.
"""
from __future__ import annotations

import datetime as dt

from . import api

OVERALL_LEAGUE = 314        # the global "Overall" league - live world ranking
MIN_SAMPLE = 10             # below this the signal is noise, return None


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def build(boot=None, plan_gw=None, size=50, league_id=OVERALL_LEAGUE,
          moves=True):
    """One elite-template snapshot for the squad going into `plan_gw`.

    plan_gw: the gameweek the horizon opens on (intended squads, not stale
    ones). Defaults to the next unfinished event. Returns {} when the
    gameweek cannot be identified, None when the sample is too thin.
    """
    boot = boot or api.bootstrap()
    if plan_gw is None:
        nxt = api.next_event(boot)
        cur = api.current_event(boot)
        ev = nxt or cur
        plan_gw = int(ev["id"]) if ev else None
    if plan_gw is None:
        return {}

    rows = []
    try:
        data = api.league_classic(league_id, 1)
    except Exception:                                        # noqa: BLE001
        return None
    rows = ((data.get("standings") or {}).get("results") or [])[:size]
    league_name = (data.get("league") or {}).get("name") or f"league {league_id}"

    # other managers' intended squads for a future deadline are not public -
    # the picks endpoint 404s ahead of the deadline. Probe once, and fall
    # back to the most recent gameweek that IS readable for everyone.
    gw_read = int(plan_gw)
    if rows:
        try:
            api.entry_picks(int(rows[0]["entry"]), int(plan_gw))
        except Exception:                                    # noqa: BLE001
            cur = api.current_event(boot)      # returns the event id, or None
            if cur and int(cur) != int(plan_gw):
                gw_read = int(cur)
    gw_note = ("" if gw_read == int(plan_gw) else
               f"squads as read for GW{gw_read} — intended GW{plan_gw} squads "
               "are not public yet")

    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    pos_by_type = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    info = {e["id"]: {"name": e.get("web_name"), "team": teams[e["team"]],
                      "pos": pos_by_type[e["element_type"]],
                      "price": e["now_cost"] / 10.0,
                      "field": float(e.get("selected_by_percent") or 0)}
            for e in boot["elements"]}

    squads, seen_cap, moves_in, moves_out = {}, {}, {}, {}
    ok = 0
    for r in rows:
        eid = int(r["entry"])
        try:
            picks = api.entry_picks(eid, gw_read)["picks"]
        except Exception:                                    # noqa: BLE001
            continue
        ok += 1
        for p in picks:
            i = p["element"]
            squads[i] = squads.get(i, 0) + 1
            if p["position"] <= 11 and p.get("is_captain"):
                seen_cap[i] = seen_cap.get(i, 0) + 1
        if moves:
            try:
                for tr in api.entry_transfers(eid):
                    if int(tr.get("event") or 0) != plan_gw:
                        continue
                    moves_in[tr["element_in"]] = moves_in.get(tr["element_in"], 0) + 1
                    moves_out[tr["element_out"]] = moves_out.get(tr["element_out"], 0) + 1
            except Exception:                                # noqa: BLE001
                pass
    if ok < MIN_SAMPLE:
        return None
    n = float(ok)

    def row(i, share):
        p = info.get(i, {})
        return {"id": int(i), "name": p.get("name", f"#{i}"),
                "team": p.get("team", ""), "pos": p.get("pos", ""),
                "price": p.get("price"), "elite": round(share / n * 100, 1),
                "field": p.get("field")}

    template = sorted((row(i, c) for i, c in squads.items()),
                      key=lambda r: -r["elite"])[:25]
    captions = sorted((row(i, c) for i, c in seen_cap.items()),
                      key=lambda r: -r["elite"])[:8]
    top = lambda d: [row(i, c) for i, c in                      # noqa: E731
                     sorted(d.items(), key=lambda kv: -kv[1])[:10]]
    return {
        "gw": int(plan_gw), "gw_read": gw_read, "note": gw_note,
        "generated": _now(),
        "league": f"{league_name} (top {size})",
        "sampled": ok,
        "template": template,
        "captains": captions,
        "moves_in": top(moves_in), "moves_out": top(moves_out),
    }


def own_map(snap):
    """Elite share per element id, for the planner's blend."""
    return {r["id"]: r["elite"] for r in (snap or {}).get("template", [])}