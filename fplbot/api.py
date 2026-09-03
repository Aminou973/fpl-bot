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
        except urllib.error.HTTPError as e:
            last = e
            # a 4xx is an answer, not a hiccup: a 404 (entry_cup before the cup
            # exists, picks not yet published) used to burn 20s of back-off
            # before raising. Only 429 is worth waiting out.
            if 400 <= e.code < 500 and e.code != 429:
                break
            time.sleep(pause * (attempt + 1))
        except (urllib.error.URLError, TimeoutError) as e:
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


def entry_event(entry_id: int, gw: int):
    """An entry's live gameweek history: {points: {total, ...}, active_chip, ...}."""
    return get(f"entry/{entry_id}/event/{gw}/")


def entry_picks(entry_id: int, gw: int):
    return get(f"entry/{entry_id}/event/{gw}/picks/")


def entry_cup(entry_id: int):
    """This entry's classic cup run; 404/None before or after the cup."""
    return get(f"entry/{entry_id}/cup/")


def league_classic(league_id: int, page: int = 1):
    """One page (50 managers) of a classic league's standings."""
    return get(f"leagues-classic/{league_id}/standings/?page={page}")


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
# These endpoints need an authenticated session. FPL retired the old form
# login (users.premierleague.com is gone from DNS) for OAuth2/OIDC at
# account.premierleague.com with Bearer tokens. A one-time interactive browser
# login (jobs/fpl_login.py, Authorization Code + PKCE) yields a refresh token;
# every automated run then exchanges it for a short-lived access token. Tokens
# arrive from the environment (FPL_REFRESH_TOKEN, FPL_REFRESH_TOKEN_2, …),
# never from config.

AUTH = "https://account.premierleague.com/as"
CLIENT_ID = "bfcbaf69-aade-4c1b-8f00-c1cb8a193030"   # the official web app's
SCOPES = "openid profile email offline_access"
# The web app registers its own origin as the only redirect; a local loopback
# is rejected ("Redirect URI mismatch"), so the interactive login reuses it and
# the user pastes the redirected URL (?code=...) back into the login script.
REDIRECT_URI = "https://fantasy.premierleague.com/"


def _auth_post(path, data):
    import time
    import requests
    # one DNS blip used to kill an otherwise-fine login mid-exchange (and a
    # refresh would then cost the whole run); retry the transient failures
    for attempt in range(4):
        try:
            r = requests.post(f"{AUTH}/{path}", data=data,
                              headers={"User-Agent": UA, "Accept": "application/json"},
                              timeout=45)
            break
        except requests.exceptions.RequestException as e:
            if attempt == 3:
                raise RuntimeError(f"{AUTH}/{path} unreachable after 4 tries: {e}")
            print(f"[auth] transient network error, retrying "
                  f"({attempt + 1}/3): {type(e).__name__}")
            time.sleep(3 * (attempt + 1))
    body = {}
    try:
        body = r.json()
    except ValueError:
        pass
    return r.status_code, body


def authorize_url(state: str, code_challenge: str) -> str:
    """PKCE authorization URL: the user opens it, signs in, and lands on
    REDIRECT_URI with ?code=... — that URL is pasted back and the code
    exchanged by exchange_code()."""
    import urllib.parse
    q = urllib.parse.urlencode({
        "response_type": "code", "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI, "scope": SCOPES,
        "code_challenge": code_challenge, "code_challenge_method": "S256",
        "state": state})
    return f"{AUTH}/authorize?{q}"


def exchange_code(code: str, code_verifier: str):
    """Swap an authorization code (plus its PKCE verifier) for tokens."""
    status, body = _auth_post("token", {
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT_URI, "client_id": CLIENT_ID,
        "code_verifier": code_verifier})
    if status != 200 or not body.get("access_token"):
        raise RuntimeError(f"token exchange failed: HTTP {status} "
                           f"{body.get('error', body)}")
    return body


def refresh_tokens(refresh_token: str):
    """Exchange a refresh token for a fresh access token (headless).

    Note: FPL rotates the refresh token on every exchange and invalidates
    the previous one — the caller must persist the new refresh_token
    (jobs/submit_transfers.py writes it back to the repo secret).
    """
    code, body = _auth_post("token", {
        "grant_type": "refresh_token", "refresh_token": refresh_token,
        "client_id": CLIENT_ID})
    if code != 200 or not body.get("access_token"):
        raise RuntimeError(f"refresh failed: HTTP {code} "
                           f"{body.get('error', body)}")
    return body


def api_session(access_token: str):
    """Requests session carrying the Bearer token the fantasy API wants."""
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json",
                      "Authorization": f"Bearer {access_token}",
                      "X-API-Authorization": f"Bearer {access_token}"})
    return s


def me(session):
    """Logged-in profile: maps entry_id -> my-team id.

    The current /api/me/ shape is {"player": {..., "entry": N}, ...} and the
    web app calls my-team/{entry}/ with that same id, so the two are the same
    number. The older teams[] shape is kept as a fallback.
    """
    r = session.get(f"{BASE}/me/", timeout=45)
    if r.status_code != 200:
        raise RuntimeError(f"/me/ read failed: HTTP {r.status_code}")
    data = r.json()
    player = data.get("player") or {}
    if player.get("entry"):
        entry_id = int(player["entry"])
        return {entry_id: entry_id}
    teams = {}
    for t in data.get("teams", []) or []:
        if t.get("entry"):
            teams[int(t["entry"])] = int(t.get("id") or t["entry"])
    if not teams:
        raise RuntimeError("authenticated but no team is attached to this "
                           f"account (me/ keys: {sorted(data)})")
    return teams


def my_team(session, team_id: int):
    """Current picks, bank, chips and transfer state for a logged-in team."""
    r = session.get(f"{BASE}/my-team/{team_id}/", timeout=45)
    if r.status_code != 200:
        raise RuntimeError(f"my-team/{team_id} read failed: HTTP {r.status_code}")
    return r.json()


def make_transfers(session, entry_id: int, gw: int, transfers: list, chip=None):
    """Execute transfers for one entry in one gameweek.

    ``transfers`` is the payload the web app builds: a list of
    ``{element_in, element_out, purchase_price, selling_price}`` with prices in
    tenths of a million — the in-player's current cost and the out-player's
    selling price (from the my-team read). The endpoint also takes the chip
    being played this week (a chip play posts here with an empty list).
    """
    r = session.post(f"{BASE}/transfers/",
                     json={"chip": chip, "entry": entry_id, "event": gw,
                           "transfers": transfers}, timeout=45)
    # 200 is a fresh batch; FPL answers 202 for an accepted no-change replay
    # (an identical transfer batch or a chip re-armed by a retried run) —
    # both mean the game took it, so only real errors raise
    if not 200 <= r.status_code < 300:
        raise RuntimeError(f"transfers/{entry_id} failed: "
                           f"HTTP {r.status_code} {r.text[:300]}")
    # a 200 can come back with an empty body; that still means accepted
    return r.json() if r.text.strip() else {}


def submit_picks(session, team_id: int, picks: list, chip=None):
    """Write a full 15-player lineup (and optionally a chip) for one team.

    ``picks`` is the standard payload: 15 dicts of
    ``{element, position, is_captain, is_vice}``. Position 1-11 must form a
    legal XI with the captain in it, which last_plan.json guarantees. The
    endpoint's schema names the vice flag ``is_vice_captain`` and calls it
    required, so it is mapped here rather than trusted from callers.
    """
    body = [{"element": p["element"], "position": p["position"],
             "is_captain": bool(p.get("is_captain")),
             "is_vice_captain": bool(p.get("is_vice_captain", p.get("is_vice")))}
            for p in picks]
    r = session.post(f"{BASE}/my-team/{team_id}/",
                     json={"chip": chip, "picks": body}, timeout=45)
    # 200 is a fresh write; 202 means the game accepted a re-write of an
    # already-current lineup (e.g. a chip armed again by a retried run) —
    # both are success, only 4xx/5xx is a failure
    if not 200 <= r.status_code < 300:
        raise RuntimeError(f"my-team/{team_id} submit failed: "
                           f"HTTP {r.status_code} {r.text[:300]}")
    # success can be an empty body; only parse when there is one
    return r.json() if r.text.strip() else {}


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
            # what each held player would actually sell for — the game tracks
            # price rises you paid for, and the planner must not assume it
            # recovers a player's full risen price
            out["picks_detail"] = [{"element": p["element"],
                                    "selling_price": p.get("selling_price"),
                                    "purchase_price": p.get("purchase_price")}
                                   for p in picks["picks"]]
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
