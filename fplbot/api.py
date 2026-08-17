"""
Official Fantasy Premier League API client.

Everything here talks to https://fantasy.premierleague.com/api/. The endpoints
used are public and unauthenticated. Frames are returned with exactly the column
names the model expects, so the same engine runs on live data or on the offline
CSV snapshots in data/.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

BASE = "https://fantasy.premierleague.com/api"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
POS_NAME = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def get(path: str, retries: int = 4, pause: float = 2.0):
    url = f"{BASE}/{path.lstrip('/')}"
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last = e
            time.sleep(pause * (attempt + 1))
    raise RuntimeError(f"FPL API failed for {url}: {last}")


# ------------------------------------------------------------------ endpoints
def bootstrap():
    return get("bootstrap-static/")


def fixtures():
    return get("fixtures/")


def event_live(gw: int):
    return get(f"event/{gw}/live/")


def entry(entry_id: int):
    return get(f"entry/{entry_id}/")


def entry_picks(entry_id: int, gw: int):
    return get(f"entry/{entry_id}/event/{gw}/picks/")


def entry_history(entry_id: int):
    return get(f"entry/{entry_id}/history/")


def entry_transfers(entry_id: int):
    return get(f"entry/{entry_id}/transfers/")


# --------------------------------------------------------------------- frames
def frames(boot=None, fx=None):
    """(players, teams, fixtures) as DataFrames matching the CSV schema."""
    boot = boot or bootstrap()
    fx = fx or fixtures()
    p = pd.DataFrame(boot["elements"])
    t = pd.DataFrame(boot["teams"])
    f = pd.DataFrame(fx)
    for col in ("team_h_difficulty", "team_a_difficulty"):
        if col not in f:
            f[col] = 3
    return p, t, f


def current_event(boot=None):
    boot = boot or bootstrap()
    for e in boot["events"]:
        if e.get("is_current"):
            return e["id"]
    return 0


def next_event(boot=None):
    boot = boot or bootstrap()
    for e in boot["events"]:
        if e.get("is_next"):
            return e
    pend = [e for e in boot["events"] if not e.get("finished")]
    return pend[0] if pend else boot["events"][-1]


def season_gameweeks(boot=None, fx=None, upto=None):
    """Rebuild a merged_gw-style frame for the current season from event/live.

    One request per completed gameweek rather than one per player, which keeps
    this inside the API's rate limits even late in the season.
    """
    boot = boot or bootstrap()
    fx = fx or fixtures()
    elements = {e["id"]: e for e in boot["elements"]}
    team_name = {t["id"]: t["name"] for t in boot["teams"]}
    fixtures_by_id = {m["id"]: m for m in fx}
    done = [e["id"] for e in boot["events"] if e.get("finished")]
    if upto:
        done = [g for g in done if g <= upto]

    rows = []
    for gw in done:
        live = event_live(gw)
        for el in live.get("elements", []):
            eid = el["id"]
            meta = elements.get(eid)
            if not meta:
                continue
            stats = el.get("stats", {}) or {}
            fixture_ids = [x.get("fixture") for x in (el.get("explain") or [])
                           if x.get("fixture")]
            if not fixture_ids:
                fixture_ids = [None]
            for fid in fixture_ids:
                m = fixtures_by_id.get(fid, {})
                home = m.get("team_h") == meta["team"]
                opp = m.get("team_a") if home else m.get("team_h")
                rows.append({
                    "name": meta["web_name"],
                    "position": POS_NAME.get(meta["element_type"], "MID"),
                    "team": team_name.get(meta["team"], ""),
                    "element": eid,
                    "fixture": fid,
                    "opponent_team": opp,
                    "was_home": bool(home),
                    "team_h_score": m.get("team_h_score"),
                    "team_a_score": m.get("team_a_score"),
                    "GW": gw, "round": gw,
                    "value": meta["now_cost"],
                    **{k: stats.get(k, 0) for k in (
                        "minutes", "goals_scored", "assists", "clean_sheets",
                        "goals_conceded", "own_goals", "penalties_saved",
                        "penalties_missed", "yellow_cards", "red_cards", "saves",
                        "bonus", "bps", "influence", "creativity", "threat",
                        "ict_index", "starts", "expected_goals", "expected_assists",
                        "expected_goal_involvements", "expected_goals_conceded",
                        "clearances_blocks_interceptions", "recoveries", "tackles",
                        "defensive_contribution", "total_points")},
                })
    df = pd.DataFrame(rows)
    if len(df):
        for c in ("expected_goals", "expected_assists", "expected_goals_conceded"):
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df


# ------------------------------------------------------------- manager state
def squad_state(entry_id: int, boot=None):
    """Current picks, bank, squad value and free transfers for one team."""
    boot = boot or bootstrap()
    cur = current_event(boot)
    info = entry(entry_id)
    out = {
        "entry": entry_id,
        "name": info.get("name"),
        "overall_rank": info.get("summary_overall_rank"),
        "total_points": info.get("summary_overall_points"),
        "bank": (info.get("last_deadline_bank") or 0) / 10.0,
        "value": (info.get("last_deadline_value") or 0) / 10.0,
        "picks": [], "free_transfers": 1, "chips_used": [],
    }
    if cur:
        try:
            picks = entry_picks(entry_id, cur)
            out["picks"] = [p["element"] for p in picks["picks"]]
            out["captain"] = next((p["element"] for p in picks["picks"] if p["is_captain"]), None)
        except RuntimeError:
            pass
    try:
        hist = entry_history(entry_id)
        out["chips_used"] = [c["name"] for c in hist.get("chips", [])]
        made = {h["event"]: h.get("event_transfers", 0) for h in hist.get("current", [])}
        ft = 1
        for gw in sorted(made):
            ft = min(5, ft - min(made[gw], ft) + 1)
        out["free_transfers"] = max(1, min(5, ft))
    except RuntimeError:
        pass
    return out


# ------------------------------------------------------------------- offline
def offline_frames(data_dir="data"):
    d = Path(data_dir)
    return (pd.read_csv(d / "2026-27/players_raw.csv"),
            pd.read_csv(d / "2026-27/teams.csv"),
            pd.read_csv(d / "2026-27/fixtures.csv"))
