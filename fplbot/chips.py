"""
Season-long chip calendar.

Chips are the only decisions in Fantasy that you make once and cannot take back,
so a five-gameweek window is the wrong lens for them. This projects every player
across all 38 gameweeks and scores each week for each chip.

What it can and cannot know: double and blank gameweeks are not in the fixture
list until the cup rounds are drawn, so bench boost and free hit are scored on
fixture quality here and will re-score themselves the moment the real doubles
appear. Triple captain and wildcard do not depend on doubles and are sound now.
"""
from __future__ import annotations

import json
from pathlib import Path

# Defaults only - the real windows come from the API's own chips array, which
# for 2026/27 reads: wildcard and free hit GW2-19 then GW20-38, bench boost and
# triple captain GW1-19 then GW20-38. Eight chips in two sets of four, and the
# first set runs THROUGH gameweek 19, not up to it.
CHIP_SPLIT = 20          # first gameweek of the second chip set
DEFAULT_WINDOWS = {
    "wildcard": [{"start": 2, "stop": 19}, {"start": 20, "stop": 38}],
    "freehit": [{"start": 2, "stop": 19}, {"start": 20, "stop": 38}],
    "bboost": [{"start": 1, "stop": 19}, {"start": 20, "stop": 38}],
    "3xc": [{"start": 1, "stop": 19}, {"start": 20, "stop": 38}],
}
CHIP_KEY = {"triple_captain": "3xc", "bench_boost": "bboost",
            "wildcard": "wildcard", "free_hit": "freehit"}
PATTERNS = Path(__file__).resolve().parent.parent / "data" / "history" / "gw_patterns.json"


def load_patterns():
    """How often each gameweek number has been a double or a blank, historically.

    Built from the official fixture lists of 2022-23 to 2025-26. The two
    Covid-disrupted seasons are excluded because their postponement chaos tells
    you nothing about a normal calendar. This is a prior, not a schedule: the
    real doubles depend on cup draws that have not happened yet, and it should be
    read as "this is when they usually land", not "this is when they will".
    """
    try:
        return json.loads(PATTERNS.read_text())
    except (OSError, ValueError):
        return {"basis": [], "gameweeks": {}}


def _xp(p, gw):
    return float(p.get(f"xp{gw}", 0.0) or 0.0)


def calendar(df, gws, squads, caps=None, windows=None, split=None):
    """Score every gameweek for every chip.

    df    : projections covering all of `gws`
    gws   : the full list of gameweeks projected (ideally 1..38)
    squads: {team_name: [player ids]}
    caps  : {team_name: max ownership for a captain} - the risk team refuses to
            triple-captain a player the whole field already owns, so its chip
            calendar has to refuse him too
    """
    caps = caps or {}
    windows = windows or DEFAULT_WINDOWS
    if split is None:
        wc = windows.get("wildcard") or DEFAULT_WINDOWS["wildcard"]
        split = wc[1]["start"] if len(wc) > 1 else CHIP_SPLIT
    pat = load_patterns()
    hist = pat.get("gameweeks", {})
    rows = df.to_dict("records")
    by_id = {int(r["id"]): r for r in rows}
    out = {}

    # the pool a wildcard could reach: best available regardless of price, as a
    # ceiling to measure your own squad against
    for name, ids in squads.items():
        ids = [i for i in ids if i in by_id]
        mine = [by_id[i] for i in ids]
        weeks = []
        for gw in gws:
            xps = sorted(((_xp(p, gw), p) for p in mine), key=lambda t: -t[0])
            xi = xps[:11]
            bench = xps[11:]
            att = [p for v, p in xps if p["pos"] in ("MID", "FWD")]
            cap_limit = caps.get(name)
            if cap_limit is not None:
                capped = [p for p in att if p.get("selected_by", 0) <= cap_limit]
                att = capped or att
            best_cap = max((_xp(p, gw) for p in att), default=0.0)
            cap_name = next((p["name"] for p in att if _xp(p, gw) == best_cap), None)
            blanks = sum(1 for p in mine if not (p.get(f"fx{gw}") or "").strip()
                         or p.get(f"fx{gw}") == "BLANK")
            h = hist.get(str(gw), {})
            p_dbl = float(h.get("p_double", 0.0))
            p_bln = float(h.get("p_blank", 0.0))
            share_dbl = float(h.get("mean_teams_double", 0.0)) / 20.0
            share_bln = float(h.get("mean_teams_blank", 0.0)) / 20.0
            bb = sum(v for v, _ in bench)
            weeks.append({
                "gw": gw,
                "triple_captain": round(best_cap, 2),
                "tc_player": cap_name,
                "bench_boost": round(bb, 2),
                # A double gameweek is what makes a bench boost worth playing, so
                # the expected value leans on how often this week has been one.
                "bench_boost_expected": round(bb * (1 + p_dbl * share_dbl * 11), 2),
                "tc_expected": round(best_cap * (1 + p_dbl * share_dbl * 6), 2),
                "squad_xp": round(sum(v for v, _ in xps), 2),
                "blanks": blanks,
                # Free hit rescues a blank. Until the cup draws land, the only
                # signal available is how often this week has blanked before.
                "blank_risk": round(max(blanks / 15.0, p_bln * share_bln * 6), 3),
                "p_double": p_dbl, "p_blank": p_bln,
                "hist_teams_double": h.get("mean_teams_double", 0),
                "hist_teams_blank": h.get("mean_teams_blank", 0),
            })
        # Wildcard timing. The raw gap between your squad and the best fifteen
        # available over the next five gameweeks is always large - your squad has
        # a budget and a three-per-club limit and the comparison does not. What
        # matters is when that gap is unusually wide, so it is reported as a
        # deviation from your own season median: positive means this is a better
        # week than most to tear the squad up.
        top = _rolling_best(rows, gws, 5)
        gaps = []
        for i, w in enumerate(weeks):
            window = gws[i:i + 5]
            if len(window) < 3:
                w["wildcard"] = None
                gaps.append(None)
                continue
            mine_sum = sum(_xp(p, g) for p in mine for g in window)
            gaps.append(top[w["gw"]] - mine_sum)
        real = sorted(g for g in gaps if g is not None)
        med = real[len(real) // 2] if real else 0.0
        for w, g in zip(weeks, gaps):
            w["wildcard"] = None if g is None else round(g - med, 1)
        out[name] = weeks

    return {
        "split": split,
        "basis": pat.get("basis", []),
        "teams": out,
        "windows": windows,
        "picks": {name: _recommend(w, split, windows) for name, w in out.items()},
    }


def _rolling_best(rows, gws, span):
    """Total projection of the best 15 players over each five-gameweek window."""
    best = {}
    for i, g in enumerate(gws):
        window = gws[i:i + span]
        if len(window) < 3:
            best[g] = 0.0
            continue
        tot = sorted((sum(_xp(p, w) for w in window) for p in rows), reverse=True)[:15]
        best[g] = sum(tot)
    return best


def _allowed(windows, chip, half_index):
    """The gameweek range this chip may be played in, for this half."""
    w = windows.get(CHIP_KEY.get(chip, chip)) or []
    if half_index < len(w):
        return w[half_index].get("start") or 1, w[half_index].get("stop") or 38
    return None


def _best(weeks, key, lo, hi, n=3, reverse=True):
    sub = [w for w in weeks if lo <= w["gw"] <= hi and w.get(key) is not None]
    sub.sort(key=lambda w: w[key], reverse=reverse)
    return sub[:n]


def _recommend(weeks, split, windows=None):
    """Best windows for each chip, split either side of the first-set deadline.

    Each chip is only offered inside the gameweeks it can legally be played -
    a wildcard cannot be played in gameweek 1, for instance, because transfers
    are already unlimited then.
    """
    windows = windows or DEFAULT_WINDOWS
    last = weeks[-1]["gw"] if weeks else 38
    halves = [("first", 0, 1, split - 1), ("second", 1, split, last)]
    picks = {}
    for half, idx, lo0, hi0 in halves:  # noqa: B023 - bounds closes over idx deliberately
        def bounds(chip):
            allowed = _allowed(windows, chip, idx)
            if not allowed:
                return None
            return max(lo0, allowed[0]), min(hi0, allowed[1])
        picks[half] = {
            "triple_captain": [
                {"gw": w["gw"], "value": w["tc_expected"], "player": w["tc_player"],
                 "p_double": w["p_double"]}
                for w in _best(weeks, "tc_expected", *(bounds("triple_captain") or (0, -1)))],
            "bench_boost": [
                {"gw": w["gw"], "value": w["bench_boost_expected"],
                 "p_double": w["p_double"]}
                for w in _best(weeks, "bench_boost_expected", *(bounds("bench_boost") or (0, -1)))],
            "wildcard": [
                {"gw": w["gw"], "value": w["wildcard"]}
                for w in _best(weeks, "wildcard", *(bounds("wildcard") or (0, -1)))],
            "free_hit": [
                {"gw": w["gw"], "value": w["blank_risk"], "p_blank": w["p_blank"]}
                for w in _best(weeks, "blank_risk", *(bounds("free_hit") or (0, -1)))
                if w["blank_risk"] > 0],
        }
    return picks
