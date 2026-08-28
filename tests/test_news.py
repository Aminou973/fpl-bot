"""Engine 6 invariants: the scrape can only hurt a doubtful player, never help anyone."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fplbot import model, news


def boot():
    """A tiny fake bootstrap: one doubtful player, one fit, one injured."""
    return {
        "teams": [{"id": 1, "name": "Arsenal", "short_name": "ARS"}],
        "elements": [
            {"id": 11, "first_name": "Bukayo", "second_name": "Saka",
             "web_name": "Saka", "team": 1, "status": "d"},
            {"id": 12, "first_name": "Martin", "second_name": "Odegaard",
             "web_name": "Odegaard", "team": 1, "status": "a"},
            {"id": 13, "first_name": "Gabriel", "second_name": "Jesus",
             "web_name": "Jesus", "team": 1, "status": "i"},
        ],
    }


def frame():
    return news.base_frame(boot())


def sig(player=None, team=None, text="", kind=None, source="physioroom",
        weight=0.8, age_h=1.0):
    import datetime as dt
    ts = (news._now() - dt.timedelta(hours=age_h)).isoformat()
    return {"source": source, "kind": kind, "team": team, "player": player,
            "text": text, "ts": ts, "weight": weight}


def test_scraped_out_lowers_only_doubtful():
    base = frame()
    res = news.resolve_players(base, [
        sig(player="Bukayo Saka", text="Saka ruled out of the weekend clash")])
    r = dict(zip(res.element, res.news_risk))
    assert r[11] <= 0.1           # doubtful + scraped "out" -> near zero
    assert r[12] == 1.0           # a fully fit player is untouched


def test_fit_signal_never_raises():
    # resolve_players reports the scrape itself; the never-raises rule is
    # enforced where it matters, in blended() and model.build
    base = frame()
    scrape = news.resolve_players(base, [
        sig(player="Gabriel Jesus", text="Jesus is back in full training",
            kind="fit")])
    r = dict(zip(scrape.element, scrape.news_risk))
    assert r[13] == 1.0           # the scrape alone says "fit"
    b = news.blended(scrape, news.degrade(base))
    m = dict(zip(b.element, b.news_risk))
    assert m[13] == 0.0           # but the blend keeps the API's 0.0


def test_api_wins_when_more_pessimistic():
    base = frame()
    scrape = news.resolve_players(base, [
        sig(player="Gabriel Jesus", text="Jesus is fit again", kind="fit")])
    fallback = news.degrade(base)
    b = news.blended(scrape, fallback)
    m = dict(zip(b.element, b.news_risk))
    assert m[13] == 0.0           # min(fpl, scrape): the API's 0 stands
    assert m[11] <= fallback.set_index("element").loc[11, "news_risk"]


def test_degrade_matches_fpl_status():
    base = frame()
    base["chance_of_playing_next_round"] = [75.0, None, None]
    d = news.degrade(base)
    m = dict(zip(d.element, d.news_risk))
    assert abs(m[11] - 0.75) < 1e-9
    assert m[12] == 1.0
    assert m[13] == 0.0


def test_stale_signals_ignored():
    base = frame()
    res = news.resolve_players(base, [
        sig(player="Bukayo Saka", text="Saka ruled out", age_h=48.0)])
    assert (res.news_risk == 1.0).all()


def test_circuit_breaker_skips_failing_source():
    import json, tempfile
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "news_cache.json"
        skip_until = (news._now() + pd.Timedelta(hours=12)).isoformat()
        cache.write_text(json.dumps({
            "sources": {}, "etag": {}, "failures": {},
            "skip_until": {"physioroom": skip_until}}), encoding="utf-8")
        out = news.fetch_all(sources=[s for s in news.SOURCES
                                      if s["name"] == "physioroom"],
                             cache=cache, budget_s=5)
        assert out["sources"]["physioroom"]["skipped"] is True
        assert out["degraded"] is True


def test_model_build_news_lowers_doubtful_avail_only():
    df, _, _, gws = model.build(horizon=2, start_gw=2)
    base = df[["id", "status", "avail"]].copy()
    news_df = pd.DataFrame({"element": df["id"], "news_risk": 1.0})
    # knock every player's risk to zero and confirm only doubtful rows move
    news_df["news_risk"] = 0.1
    with_news, _, _, _ = model.build(horizon=2, start_gw=2, news=news_df)
    m = with_news.set_index("id")
    doubt = base[base.status == "d"]["id"]
    fit = base[base.status == "a"]["id"]
    for i in doubt:
        assert m.loc[i, "avail"] < base.set_index("id").loc[i, "avail"] + 1e-9
    for i in fit:
        assert abs(m.loc[i, "avail"] - base.set_index("id").loc[i, "avail"]) < 1e-9