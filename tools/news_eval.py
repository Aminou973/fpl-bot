"""Score the news engine's scraped signals against what FPL itself says.

The engine's promotion rule is explicit: until the agreement test shows
>= 90% precision, scraped signals may only sharpen a player FPL already
calls doubtful - never override the API. This tool measures exactly that:
for every current scraped "out"/"doubt" signal, did FPL independently flag
the player (status not "a", or chance_of_playing < 100)?

Precision here is a snapshot, not a longitudinal score - it grows honest as
state/news_signals.json accumulates history. Written into
data/backtest/news_eval.json for the dashboard accuracy panel.

Usage:  python tools/news_eval.py [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fplbot import api, news                                       # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "data" / "backtest" / "news_eval.json"))
    a = ap.parse_args()

    raw = news.load_signals()
    if not raw:
        print("no news signals stored yet - the watch job has not scanned")
        return
    boot = api.bootstrap()
    base = news.base_frame(boot).set_index("id")
    resolved = news.resolve_players(base.reset_index(), raw)

    rows = []
    for _, r in resolved.iterrows():
        if r.method != "scrape" or r.news_risk >= 1.0:
            continue
        eid = int(r.element)
        if eid not in base.index:
            continue
        p = base.loc[eid]
        fpl_risk = None if p.status == "a" else \
            (p.chance_of_playing_next_round / 100.0
             if p.get("chance_of_playing_next_round") is not None else 0.5)
        rows.append({"element": eid, "name": p.web_name,
                     "scrape": r.source, "scrape_risk": r.news_risk,
                     "fpl_status": p.status,
                     "fpl_risk": fpl_risk,
                     "agrees": fpl_risk is not None and fpl_risk <= 0.75})
    if not rows:
        print("no pessimistic scraped signals to score yet")
        return
    agree = sum(1 for r in rows if r["agrees"])
    out = {"signals": len(rows),
           "precision": round(agree / len(rows), 3),
           "threshold": 0.9,
           "pass": agree / len(rows) >= 0.9,
           "rows": rows}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(f"scraped pessimistic signals: {len(rows)}, agree with FPL: {agree} "
          f"-> precision {out['precision']} "
          f"({'PASS - override unlocked at 90%' if out['pass'] else 'below 0.90 - scrape stays advisory'})")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()