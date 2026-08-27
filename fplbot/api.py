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


def chip_windows(boot=None):
    """When each chip may actually be played, straight from the game itself.

    The API is the authority here: it publishes one entry per chip per half of
    the season with the exact gameweek range. Reading it rather than hardcoding
    means a rule change fixes itself.
    """
    boot = boot or bootstrap()
    out = {}
    for c in boot.get("chips", []) or []:
        out.setdefault(c["name"], []).append(
            {"start": c.get("start_event"), "stop": c.get("stop_event"),
             "type": c.get("chip_type")})
    for v in out.values():
        v.sort(key=lambda w: (w["start"] or 0))
    return out


def settled_events(boot=None, fx=None, with_provisional=False):
    """Gameweeks whose results can be trusted, which is not the same as "finished".

    The game only sets ``finished``/``data_checked`` on an event once it has
    audited the week, and that audit can lag the last whistle by more than a
    day. The fixtures themselves flip ``finished_provisional`` as soon as bonus
    is applied, and the points behind them stop moving at that point. Waiting on
    the event flag leaves the dashboard blank on a gameweek that is, to anyone
    looking at it, plainly over - so an event counts as settled when the game
    says so, or when every one of its fixtures has provisionally finished.

    The provisional ones carry a caveat: their bonus points are the live
    calculation and the game has not written them down yet, so a player can
    still move by a point or two. With ``with_provisional`` this returns
    ``(settled, provisional)`` so the dashboard can say which weeks those are.
    """
    boot = boot or bootstrap()
    by_event = {}
    for m in (fx if fx is not None else fixtures()):
        by_event.setdefault(m.get("event"), []).append(m)
    ids, prov = [], []
    for e in boot["events"]:
        if e.get("finished") or e.get("data_checked"):
            ids.append(e["id"])
            continue
        ms = by_event.get(e["id"]) or []
        if ms and all(m.get("finished") or m.get("finished_provisional") for m in ms):
            ids.append(e["id"])
            prov.append(e["id"])
    return (sorted(ids), sorted(prov)) if with_provisional else sorted(ids)


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
    done = settled_events(boot, fx)
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


# ----------------------------------------------------------------- logged in
# These endpoints need a real login session. Nothing here is public-API: the
# session cookie comes from the account login and every write goes through
# my-team/{team_id}/. Credentials are expected to arrive from the environment
# (FPL_EMAIL / FPL_PASSWORD), never from config or code.

LOGIN_URL = "https://users.premierleague.com/api/user/login"


def login(email: str, password: str):
    """Authenticated session plus the my-team id for the caller's entries.

    Returns (session, teams) where teams maps entry_id -> my-team id (the
    internal id the my-team endpoints want, not the public entry id).
    """
    try:
        import requests
    except ImportError as e:                     # pragma: no cover
        raise RuntimeError("auto-submit needs the requests package") from e
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    r = s.post(LOGIN_URL, data={
        "login_username": email, "login_password": password,
        "redirect_uri": "https://fantasy.premierleague.com/",
        "app": "plfpl-web"}, timeout=45)
    if r.status_code != 200:
        raise RuntimeError(f"FPL login failed: HTTP {r.status_code}")
    body = {}
    try:
        body = r.json()
    except ValueError:
        pass
    if body.get("state") not in (None, "success") or not s.cookies:
        raise RuntimeError(f"FPL login refused: {body or 'no session cookie'}")
    me = s.get(f"{BASE}/me/", timeout=45)
    if me.status_code != 200:
        raise RuntimeError(f"FPL login did not stick: /me/ HTTP {me.status_code}")
    teams = {}
    for t in me.json().get("teams", []):
        if t.get("entry"):
            teams[int(t["entry"])] = int(t["id"])
    if not teams:
        raise RuntimeError("login succeeded but no teams are attached to this account")
    return s, teams


def my_team(session, team_id: int):
    """Current picks, bank, chips and transfer state for a logged-in team."""
    r = session.get(f"{BASE}/my-team/{team_id}/", timeout=45)
    if r.status_code != 200:
        raise RuntimeError(f"my-team/{team_id} read failed: HTTP {r.status_code}")
    return r.json()


def submit_picks(session, team_id: int, picks: list, chip=None):
    """Write a full 15-player lineup (and optionally a chip) for one team.

    ``picks`` is the standard payload: 15 dicts of
    ``{element, position, is_captain, is_vice}``. Position 1-11 must form a
    legal XI with the captain in it, which last_plan.json guarantees.
    """
    r = session.post(f"{BASE}/my-team/{team_id}/",
                     json={"chip": chip, "picks": picks}, timeout=45)
    if r.status_code != 200:
        raise RuntimeError(f"my-team/{team_id} submit failed: "
                           f"HTTP {r.status_code} {r.text[:300]}")
    return r.json()


# ------------------------------------------------------------- manager state
def squad_state(entry_id: int, boot=None):
    """Current picks, bank, squad value and free transfers for one team.

    The squad is the last published picks: the current gameweek's if the game
    has opened it, otherwise the previous one (no transfers happen between a
    deadline and the next one being scored, so that is the live squad). Which
    source won is recorded in ``picks_source`` — "gw12" for published picks,
    "none" when no picks could be read, so callers can degrade loudly instead
    of quietly planning on stale data.
    """
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
        "picks_source": None, "picks_error": None,
    }
    attempts = [cur] if not cur else [cur, cur - 1]
    errors = []
    for gw in attempts:
        if not gw or gw < 1:
            continue
        try:
            picks = entry_picks(entry_id, gw)
            out["picks"] = [p["element"] for p in picks["picks"]]
            out["captain"] = next((p["element"] for p in picks["picks"] if p["is_captain"]), None)
            out["picks_source"] = f"gw{gw}"
            break
        except RuntimeError as e:
            errors.append(f"gw{gw}: {e}")
    if not out["picks"] and errors:
        out["picks_error"] = "; ".join(errors)
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
