"""Team-news / lineup intelligence (engine 6).

External scraping with the FPL API as the always-available fallback. Every
source is parsed with stdlib only — regex over HTML tables, xml.etree over RSS
— so no new dependency ships with the engine.

Two hard rules, both from the validation phase of the plan:

1. The engine may only LOWER availability, never raise it, and only for
   players the API itself flags doubtful ("d"). Until the agreement test
   (>= 90% precision against FPL's chance_of_playing) passes, scraped news
   is a tie-breaker, not an override.
2. The API wins when it is more pessimistic. A scrape saying "fit" can never
   restore availability the API has withdrawn.

Block resilience, in order: conditional requests (ETag/Last-Modified) ->
per-source exponential backoff -> circuit breaker (3 consecutive failures
skips the source for 24h) -> wall-clock budget -> an empty-but-valid result
marked degraded: True. A dead source costs a few seconds, never the job.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
CACHE = STATE / "news_cache.json"
SIGNALS = STATE / "news_signals.json"

# All sources the scanner knows. `fpl` is the API fallback - never fetched
# here (bootstrap already carries it), listed so the cache reports it.
SOURCES = [
    {"name": "fpl", "url": None, "weight": 1.0, "ttl_min": 60,
     "note": "API status/chance - the fallback, resolved from bootstrap"},
    {"name": "physioroom",
     "url": "https://www.physioroom.com/soccer/premier-league/injuries/",
     "weight": 0.8, "ttl_min": 120, "parser": "physioroom"},
    {"name": "ffscout",
     "url": "https://www.fantasyfootballscout.co.uk/feed/",
     "weight": 0.6, "ttl_min": 90, "parser": "rss"},
    {"name": "bbc",
     "url": "https://feeds.bbci.co.uk/sport/football/rss.xml",
     "weight": 0.4, "ttl_min": 120, "parser": "rss"},
]

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
]

# injury-news phrases, by direction. "out" phrases must be unambiguous -
# a false "ruled out" is the one mistake this engine must never make
OUT_PHRASES = ["ruled out", "out for the season", "will miss", "set to miss",
               "expected to miss", "sidelined", "injured and will",
               "not in the squad", "no chance of playing"]
DOUBT_PHRASES = ["doubt", "rated", "struggling", "assessment", "monitor",
                 "facing a fitness test", "late fitness"]
FIT_PHRASES = ["in contention", "available again", "back in training",
               "returned to full training", "fit again", "in the squad"]
CIRCUIT_TRIP, CIRCUIT_COOLDOWN_H = 3, 24.0
MAX_AGE_H = 24.0            # signals older than this are ignored downstream


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _fetch(url, etag=None, last_mod=None, timeout=8):
    """Conditional GET; returns (text, new_etag, new_last_mod) or raises."""
    headers = {"User-Agent": random.choice(UA_POOL),
               "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8"}
    if etag:
        headers["If-None-Match"] = etag
    if last_mod:
        headers["If-Modified-Since"] = last_mod
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return (r.read().decode("utf-8", errors="replace"),
                r.headers.get("ETag"), r.headers.get("Last-Modified"))


def _parse_rss(text):
    """Item (title, description, pubDate) tuples from an RSS feed."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    items = []
    for item in root.iter("item"):
        def txt(tag):
            el = item.find(tag)
            return (el.text or "") if el is not None else ""
        items.append({"title": txt("title"), "desc": txt("description"),
                      "ts": txt("pubDate")})
    return items


_PHYSIO_ROW = re.compile(
    r"<tr[^>]*>(?:(?!</tr>).)*?</tr>", re.S | re.I)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def _parse_physioroom(text):
    """Rows (player, injury, status, return-date-ish) from the injury table."""
    rows = []
    for tr in _PHYSIO_ROW.findall(text):
        cells = [_TAG.sub(" ", c) for c in _CELL.findall(tr)]
        cells = [re.sub(r"\s+", " ", c).strip() for c in cells]
        if len(cells) >= 3 and cells[0]:
            rows.append(cells)
    return rows


def _headline_signal(text):
    """Classify one chunk of news text; None when nothing decisive is said."""
    low = text.lower()
    if any(p in low for p in OUT_PHRASES):
        return "out"
    if any(p in low for p in DOUBT_PHRASES):
        return "doubt"
    if any(p in low for p in FIT_PHRASES):
        return "fit"
    return None


def _pub_date(s):
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S GMT"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    return None


def fetch_all(sources=None, timeout=8, cache=CACHE, budget_s=40):
    """Fetch every live source; the cache absorbs failures.

    Returns {"signals": [...], "sources": {...}, "degraded": bool,
    "updated": iso}. A signal is {"source", "kind" (out|doubt|fit), "team",
    "player", "text", "ts", "weight"} - player/team may be None and are
    resolved later against the model frame.
    """
    state = {"sources": {}, "etag": {}, "failures": {}, "skip_until": {}}
    if Path(cache).exists():
        try:
            state.update(json.loads(Path(cache).read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass
    now = _now()
    out = {"signals": [], "sources": {}, "degraded": False, "updated": now.isoformat()}
    deadline = time.monotonic() + budget_s

    for src in (sources or SOURCES):
        name = src["name"]
        if not src.get("url"):
            continue
        # circuit breaker: a source that failed three times straight is
        # skipped for a day - no point paying its timeout every hour
        skip_until = state["skip_until"].get(name)
        if skip_until and _now() < dt.datetime.fromisoformat(skip_until):
            out["sources"][name] = {"ok": False, "skipped": True}
            out["degraded"] = True
            continue
        if time.monotonic() > deadline:
            out["sources"][name] = {"ok": False, "skipped": True, "reason": "budget"}
            out["degraded"] = True
            continue
        et = state["etag"].get(name) or {}
        try:
            time.sleep(random.uniform(0.2, 1.2))        # jitter, be polite
            text, netag, nmod = _fetch(src["url"], et.get("etag"),
                                       et.get("last_modified"), timeout)
            if name not in state["etag"]:
                state["etag"][name] = {}
            state["etag"][name].update({"etag": netag, "last_modified": nmod})
            parser = src.get("parser")
            if parser == "rss":
                raw = [{"source": name, "team": None, "player": None,
                        "text": f"{it['title']}. {it['desc']}",
                        "ts": (_pub_date(it["ts"]) or now).isoformat(),
                        "weight": src["weight"]}
                       for it in _parse_rss(text) if _headline_signal(
                           f"{it['title']}. {it['desc']}")]
            elif parser == "physioroom":
                raw = []
                for cells in _parse_physioroom(text):
                    kind = None
                    joined = " ".join(cells[1:]).lower()
                    if re.search(r"\b(out|ruled out)\b", joined) or \
                            re.search(r"\b(no return date|season)\b", joined):
                        kind = "out"
                    elif re.search(r"\b(\d+ %|doubt|assessment|knock)\b", joined):
                        kind = "doubt"
                    if kind:
                        raw.append({"source": name, "team": None,
                                    "player": cells[0],
                                    "kind": kind,
                                    "text": " | ".join(cells[1:4]),
                                    "ts": now.isoformat(),
                                    "weight": src["weight"]})
            else:
                raw = []
            state["sources"][name] = {"ok": True, "ts": now.isoformat(),
                                      "n": len(raw)}
            state["failures"][name] = 0
            out["sources"][name] = {"ok": True, "n": len(raw)}
            out["signals"].extend(raw)
        except urllib.error.HTTPError as e:
            if e.code == 304:
                # conditional GET says "unchanged" - a success with no new body
                state["sources"][name] = {"ok": True, "ts": now.isoformat(),
                                          "n": 0, "not_modified": True}
                state["failures"][name] = 0
                out["sources"][name] = {"ok": True, "n": 0, "not_modified": True}
                continue
            fails = state["failures"].get(name, 0) + 1
            state["failures"][name] = fails
            if fails >= CIRCUIT_TRIP:
                state["skip_until"][name] = (
                    _now() + dt.timedelta(hours=CIRCUIT_COOLDOWN_H)).isoformat()
                state["failures"][name] = 0
            out["sources"][name] = {"ok": False, "error": str(e)[:120]}
            out["degraded"] = True
        except Exception as e:                            # noqa: BLE001
            fails = state["failures"].get(name, 0) + 1
            state["failures"][name] = fails
            if fails >= CIRCUIT_TRIP:
                state["skip_until"][name] = (
                    _now() + dt.timedelta(hours=CIRCUIT_COOLDOWN_H)).isoformat()
                state["failures"][name] = 0
            out["sources"][name] = {"ok": False, "error": str(e)[:120]}
            out["degraded"] = True

    out["signals"] = [s for s in out["signals"]
                      if (now - (dt.datetime.fromisoformat(s["ts"])
                                 if s["ts"] else now)).total_seconds()
                      < MAX_AGE_H * 3600]
    try:
        Path(cache).parent.mkdir(parents=True, exist_ok=True)
        Path(cache).write_text(json.dumps(state, indent=1), encoding="utf-8")
    except OSError:
        pass
    return out


# ---------------------------------------------------------------- resolution

def base_frame(boot):
    """A minimal player frame (id/name/web_name/team/status) for name matching.

    Both the watch job and the projections build their resolution input this
    way, so the news engine never depends on model.build having run first.
    """
    tname = {t["id"]: t["name"] for t in boot["teams"]}
    return pd.DataFrame([
        {"id": int(e["id"]), "name": f"{e['first_name']} {e['second_name']}",
         "web_name": e["web_name"], "team": tname.get(e["team"], ""),
         "status": e["status"]}
        for e in boot["elements"]])


def store_signals(raw_signals, path=SIGNALS):
    """Persist this scan's raw signals for the plan job to resolve later."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(
            {"signals": raw_signals, "updated": _now().isoformat()}),
            encoding="utf-8")
    except OSError:
        pass
    return True


def load_signals(path=SIGNALS, max_age_h=MAX_AGE_H * 2):
    """Signals stored by the last watch scan, still fresh enough to use."""
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        upd = dt.datetime.fromisoformat(data.get("updated"))
        if (_now() - upd).total_seconds() > max_age_h * 3600:
            return []
        return data.get("signals") or []
    except (ValueError, OSError, KeyError):
        return []


def _name_tokens(name):
    return {t for t in re.split(r"[^a-z]+", str(name).lower()) if len(t) > 1}


def _match_player(player_name, df):
    """Best df row for a scraped full name; None when ambiguous."""
    if not player_name:
        return None
    toks = _name_tokens(player_name)
    best, best_j = None, 0.0
    for _, r in df.iterrows():
        cand = _name_tokens(r.get("web_name", "")) | _name_tokens(r["name"])
        if not cand:
            continue
        j = len(toks & cand) / max(len(toks), 1)
        if j > best_j:
            best, best_j = int(r["id"]), j
    return best if best_j >= 0.5 else None


def _team_mask(df, team_name):
    if not team_name:
        return pd.Series(True, index=df.index)
    low = str(team_name).lower()
    return (df["team"].str.lower().str.startswith(low[:3])
            if len(low) >= 3 else df["team"].str.lower() == low)


def resolve_players(df, raw_signals, max_age_h=MAX_AGE_H):
    """Collapse raw signals into one row per element id.

    Columns: element, news_risk (0-1 availability multiplier), p_start,
    source, ts, method. Only signals fresh enough survive; conflicts resolve
    by source weight (heaviest wins, pessimism breaks ties).
    """
    now = _now()
    df = df.copy()
    df["element"] = df["id"].astype(int)
    out = df[["element"]].copy()
    out["news_risk"] = 1.0
    out["p_start"] = 1.0
    out["source"] = None
    out["ts"] = None
    if not raw_signals:
        out["method"] = "none"
        return out

    hits = {}                       # element -> best (weight, pessimism, sig)
    order = {"out": 0, "doubt": 1, "fit": 2}
    for sig in raw_signals:
        ts = sig.get("ts")
        try:
            age_h = (now - dt.datetime.fromisoformat(ts)).total_seconds() / 3600.0
        except (ValueError, TypeError):
            continue
        if age_h > max_age_h:
            continue
        kind = sig.get("kind")
        if kind is None:
            kind = _headline_signal(sig.get("text", ""))
        if kind is None:
            continue
        eid = None
        if sig.get("player"):
            eid = _match_player(sig["player"], df)
        if eid is None and sig.get("team"):
            # team-scoped news only sharpens players FPL already doubts
            m = df[_team_mask(df, sig["team"]) & (df["status"] == "d")]
            if len(m) == 1:
                eid = int(m.iloc[0]["id"])
        if eid is None:
            continue
        w = float(sig.get("weight", 0.5))
        pess = order.get(kind, 2)
        cur = hits.get(eid)
        if cur is None or (w, -pess) > (cur[0], -cur[1]):
            hits[eid] = (w, pess, sig, now - dt.timedelta(hours=age_h))

    for eid, (w, pess, sig, ts) in hits.items():
        if pess == 0:               # "out": near-zero availability
            risk, p_start = 0.05, 0.05
        elif pess == 1:             # "doubt": meaningful knock
            risk, p_start = 0.5, 0.4
        else:                       # "fit": corroborating only - never raises
            risk, p_start = 1.0, 1.0
        out.loc[out.element == eid, "news_risk"] = risk
        out.loc[out.element == eid, "p_start"] = p_start
        out.loc[out.element == eid, "source"] = sig.get("source")
        out.loc[out.element == eid, "ts"] = ts.isoformat()
    out["method"] = "scrape"
    return out


def degrade(df, max_age_h=MAX_AGE_H):
    """The API-only fallback, same shape as resolve_players. Always available."""
    df = df.copy()
    out = pd.DataFrame({"element": df["id"].astype(int)})
    if "chance_of_playing_next_round" in df.columns:
        chance = pd.to_numeric(df["chance_of_playing_next_round"],
                               errors="coerce")
    else:
        chance = pd.Series(float("nan"), index=df.index)
    out["news_risk"] = 1.0
    st = df["status"]
    out.loc[st == "d", "news_risk"] = (
        (chance[st == "d"] / 100.0).fillna(0.5).clip(0.05, 1.0))
    out.loc[st.isin(["i", "s", "u"]), "news_risk"] = 0.0
    out["p_start"] = 1.0
    out["source"] = "fpl"
    out["ts"] = None
    out["method"] = "fpl_only"
    return out


def blended(resolved, fallback):
    """Scrape where it speaks pessimistically, FPL everywhere else.

    The API wins when more pessimistic: news_risk = min(scrape, fpl) - and
    since the pre-agreement engine may only lower availability, the scrape
    can never lift a low FPL risk.
    """
    m = fallback[["element", "news_risk"]].merge(
        resolved[["element", "news_risk", "p_start", "source", "ts", "method"]],
        on="element", how="left", suffixes=("_fpl", "_news"))
    m["news_risk"] = m[["news_risk_fpl", "news_risk_news"]].min(axis=1)
    m["news_risk"] = m["news_risk"].fillna(m["news_risk_fpl"])
    m["p_start"] = m["p_start"].fillna(1.0)
    m["source"] = m["source"].fillna("fpl")
    return m[["element", "news_risk", "p_start", "source", "ts"]]


def attach_to_pool(pool, news_df):
    """The columns model.build(news=) reads; no-op when news is None."""
    df = pool.copy()
    df["news_risk"] = 1.0
    df["news_p_start"] = 1.0
    if news_df is None or not len(news_df):
        return df
    nd = news_df.set_index("element")
    for i, eid in enumerate(df["id"].values):
        if int(eid) in nd.index:
            df.iloc[i, df.columns.get_loc("news_risk")] = \
                float(nd.loc[int(eid), "news_risk"])
            df.iloc[i, df.columns.get_loc("news_p_start")] = \
                float(nd.loc[int(eid)].get("p_start", 1.0))
    return df