"""
Replay a finished season through the engine and see what it would have scored.

This is the only honest test of whether the model is worth anything. It walks
the season gameweek by gameweek and at every deadline may use ONLY what was
knowable at that moment: the previous season in full, this season's results up
to the previous gameweek, each player's price as it was that week, and each
player's ownership as it stood at the previous deadline.

All the mechanics live in fplbot/replay.py; this file is the command line.
The managed arm runs the real policy (planner.plan_with_hit_policy), a frozen
arm keeps its opening squad all season, and a template arm holds the most-owned
squad each week for rank context.

Usage:  python tools/backtest.py --season 2025-26 --until 10
        python tools/backtest.py --horizon 5 --time-limit 60 --out data/backtest/2025-26.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fplbot.replay import Replay, ReplayParams          # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", default="2025-26")
    ap.add_argument("--prior", default="2024-25")
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--until", type=int, default=38)
    ap.add_argument("--from-gw", type=int, default=1)
    ap.add_argument("--hit-threshold", type=float, default=6.0)
    ap.add_argument("--time-limit", type=int, default=20)
    ap.add_argument("--risk-lambda", type=float, default=0.0)
    ap.add_argument("--n-scenarios", type=int, default=0)
    ap.add_argument("--cvar-beta", type=float, default=0.75)
    ap.add_argument("--rank-alpha", type=float, default=0.0)
    ap.add_argument("--template-tilt", type=float, default=0.0)
    ap.add_argument("--cap-tilt", type=float, default=0.0)
    ap.add_argument("--chip-policy", default="calendar")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    cache = None if a.no_cache else None   # default cache dir; --no-cache uses temp
    if a.no_cache:
        import tempfile
        cache = Path(tempfile.mkdtemp())
    r = Replay(a.data, a.season, a.prior, cache_dir=cache)
    params = ReplayParams(horizon=a.horizon, hit_threshold=a.hit_threshold,
                          time_limit=a.time_limit, risk_lambda=a.risk_lambda,
                          n_scenarios=a.n_scenarios, cvar_beta=a.cvar_beta,
                          rank_alpha=a.rank_alpha, template_tilt=a.template_tilt,
                          cap_tilt=a.cap_tilt, chip_policy=a.chip_policy)
    t0 = time.time()
    res = r.run_policy(params, gw_from=a.from_gw, gw_to=a.until)
    print(f"\n{res.summary()}")
    print(f"ran in {time.time() - t0:.0f}s")
    out = a.out or str(ROOT / "data" / "backtest" / f"{a.season}.json")
    Path(out).write_text(json.dumps(res.to_json(), indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()