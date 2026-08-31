"""Score the price engine's weekly predictions against observed moves.

Every run recomputes what the physics model would have predicted one week ago
from the log as it stood then, and compares against the price changes that
actually happened since: Brier score for p_rise/p_fall and a calibration
table. The result lands in data/backtest/price_eval.json and is surfaced in
the brief's accuracy line - the engine's predictions are graded in public.

Usage:  python tools/price_eval.py [--weeks 4] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fplbot import price                                            # noqa: E402


def brier(pred: float, outcome: bool) -> float:
    return (pred - float(outcome)) ** 2


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weeks", type=int, default=4)
    ap.add_argument("--out", default=str(ROOT / "data" / "backtest" / "price_eval.json"))
    a = ap.parse_args()

    df = price.read_log()
    if not len(df):
        print("no price log yet - nothing to score")
        return

    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    weeks = sorted(df["gw"].dropna().unique())
    scored = []
    for gw in weeks[-a.weeks:]:
        snap = df[df.gw == gw]
        if not len(snap):
            continue
        t_cut = snap.ts.min() + pd.Timedelta(hours=1)
        hist = df[df.ts <= t_cut]
        preds = price.predict(hist)
        if not len(preds):
            continue
        # outcome: did the price change within the following week of log time?
        t_end = t_cut + pd.Timedelta(days=7)
        later = df[(df.ts > t_cut) & (df.ts <= t_end)]
        moved = later.groupby("element").cost.nunique() > 1
        p = preds.set_index("element")
        for eid, did_move in moved.items():
            if int(eid) in p.index:
                scored.append({"gw": int(gw), "element": int(eid),
                               "p_move": float(p.loc[int(eid)].p_rise
                                               + p.loc[int(eid)].p_fall),
                               "moved": bool(did_move),
                               "brier": round(brier(
                                   float(p.loc[int(eid)].p_rise
                                         + p.loc[int(eid)].p_fall), did_move), 4)})
    if not scored:
        print("no scoreable predictions yet (log too short)")
        return
    s = pd.DataFrame(scored)
    out = {
        "scored": len(s),
        "brier_mean": round(float(s.brier.mean()), 4),
        "base_rate": round(float(s.moved.mean()), 4),
        "brier_naive": round(float(brier(s.moved.mean(), s.moved)), 4),
        "calibration": [
            {"bucket": f"{lo/10:.0%}-{(lo+10)/10:.0%}",
             "n": int(len(sub)),
             "mean_pred": round(float(sub.p_move.mean()), 3),
             "observed": round(float(sub.moved.mean()), 3)}
            for lo, sub in
            [(lo, s[(s.p_move >= lo / 10) & (s.p_move < (lo + 10) / 10)])
             for lo in range(0, 100, 10)]
            if len(sub)],
        "weeks": scored,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"scored {len(s)} predictions: brier {out['brier_mean']} "
          f"(naive {out['brier_naive']}), base rate {out['base_rate']}")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()