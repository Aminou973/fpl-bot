"""Backtest-driven tuning (engine 4). The sweep every other engine's knob waits for.

Two-stage random search over the policy space, scored by the 2025-26 replay
harness the same way every engine was validated: primary objective
mean(field_pct), secondary total points. Stage 1 runs 24 coarse configs with a
short horizon and solver time limit; stage 2 re-runs the top 5 with the real
horizon and time limit. A walk-forward pass then checks the winner generalises
beyond the weeks it was picked on: best config by early weeks, scored on the
late weeks it never saw.

Usage:  python tools/tune.py --n-iter 24 --until 6 --shard 0 --nshards 4
        python tools/tune.py --collect          # merge shards, refine, report
        python tools/tune.py --report           # render tuning.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fplbot.replay import Replay, ReplayParams          # noqa: E402

OUT = ROOT / "data" / "backtest" / "tuning.json"

# the sweepable space. risk_lambda only means anything with scenarios on, so
# the sampler zeroes the lambda whenever n_scenarios is 0. price_gamma is
# deliberately absent: the price engine has no 2025-26 log to replay, so it is
# graded forward by tools/price_eval.py's Brier score instead - sweeping it
# here would pick a value that looks good by pure chance.
SPACES = {
    "hit_threshold": [3, 4, 5, 6, 8],
    "horizon": [3, 5, 8],
    "rank_alpha": [0, 0.25, 0.5, 0.75, 1],
    "template_tilt": [-0.5, -0.25, 0, 0.25, 0.5],
    "risk_lambda": [0, 0.3, 0.6, 1.0, 1.5],
    "n_scenarios": [0, 8, 32],
    "chip_policy": ["calendar", "ilp_tc_bb"],
}
COARSE_TIME_LIMIT = 12
COARSE_HORIZON = 3
REFINE_TOP = 5


def sample_params(rng: random.Random, space=None, **overrides) -> ReplayParams:
    space = space or SPACES
    kw = {k: rng.choice(v) for k, v in space.items()}
    if not kw["n_scenarios"]:
        kw["risk_lambda"] = 0            # CVaR needs a scenario set
    kw.update(overrides)
    return ReplayParams(**kw)


def score(replay: Replay, params: ReplayParams, gw_from, gw_to,
          field_sims=600, verbose=False) -> dict:
    t0 = time.time()
    res = replay.run_policy(params, gw_from=gw_from, gw_to=gw_to,
                            field_sims=field_sims, verbose=verbose)
    t = res.totals
    return {"params": {k: v for k, v in vars(params).items()},
            "points": t.get("managed", 0),
            "field_pct": t.get("mean_field_pct", 0.0),
            "worst5": t.get("worst5_managed", 0),
            "hits": t.get("hits", 0),
            "secs": round(time.time() - t0, 1)}


def coarse_stage(replay, n_iter, gw_from, gw_to, shard, nshards, seed,
                 verbose=False):
    rng = random.Random(seed)
    rows = []
    for i in range(n_iter):
        if i % nshards != shard:
            continue
        p = sample_params(rng, horizon=COARSE_HORIZON,
                          time_limit=COARSE_TIME_LIMIT, seed=seed + i)
        row = score(replay, p, gw_from, gw_to, verbose=verbose)
        row["stage"] = "coarse"
        print(f"[coarse {i + 1}/{n_iter}] pts {row['points']} "
              f"field {row['field_pct']:.1f} ({row['secs']}s) "
              f"{ {k: v for k, v in vars(p).items() if k in SPACES} }")
        rows.append(row)
    return rows


def shard_file(shard):
    return ROOT / "data" / "backtest" / f"tuning_shard{shard}.json"


def refine_stage(replay, top, gw_from, gw_to, verbose=False):
    rows = []
    for cfg in top:
        p = ReplayParams(**cfg)
        p.horizon = 5                       # the real horizon
        p.time_limit = 60                   # the real solver budget
        row = score(replay, p, gw_from, gw_to, verbose=verbose)
        row["stage"] = "refined"
        print(f"[refine] pts {row['points']} field {row['field_pct']:.1f} "
              f"({row['secs']}s) { {k: v for k, v in vars(p).items() if k in SPACES} }")
        rows.append(row)
    return rows


def pareto(rows):
    """Configs not beaten on BOTH objectives by another config."""
    out = []
    for r in rows:
        if not any(o["points"] >= r["points"] and o["field_pct"] >= r["field_pct"]
                   and (o["points"] > r["points"] or o["field_pct"] > r["field_pct"])
                   for o in rows):
            out.append(r)
    return sorted(out, key=lambda r: -r["field_pct"])


def walk_forward(replay, coarse_rows, gw_from, gw_to, split_frac=0.5):
    """Pick the best config on the training weeks, score it on the eval weeks.

    The honest check that the sweep found something and didn't just overfit
    the six weeks it searched.
    """
    if not coarse_rows or gw_to - gw_from < 3:
        return None
    split = gw_from + max(2, int((gw_to - gw_from + 1) * split_frac))
    best = max(coarse_rows, key=lambda r: (r["field_pct"], r["points"]))
    p = ReplayParams(**best["params"])
    p.horizon = COARSE_HORIZON
    p.time_limit = COARSE_TIME_LIMIT
    train = score(replay, p, gw_from, split)
    ev = score(replay, p, split + 1, gw_to)
    return {"split_gw": split, "train": train, "eval": ev,
            "params": best["params"]}


def collect(gw_from, gw_to):
    shards = sorted(ROOT.glob("data/backtest/tuning_shard*.json"))
    rows = []
    for f in shards:
        rows.extend(json.loads(f.read_text(encoding="utf-8")))
    if not rows:
        print("no shard results found - run the sweep first")
        return
    coarse = [r for r in rows if r["stage"] == "coarse"]
    top = sorted(coarse, key=lambda r: (r["field_pct"], r["points"]),
                 reverse=True)[:REFINE_TOP]
    replay = Replay()
    refined = refine_stage(replay, [r["params"] for r in top], gw_from, gw_to)
    wf = walk_forward(replay, coarse, gw_from, gw_to)
    pool = coarse + refined
    par = pareto(pool)
    best = max(par, key=lambda r: r["field_pct"])
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "gw_window": [gw_from, gw_to],
           "n_coarse": len(coarse), "n_refined": len(refined),
           "pareto": par, "best": best, "walk_forward": wf,
           "all": sorted(pool, key=lambda r: -r["field_pct"])}
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for f in shards:
        f.unlink()
    print(f"\nwrote {OUT} - {len(pool)} configs, best field_pct "
          f"{best['field_pct']} at {best['points']} pts")


def report():
    if not OUT.exists():
        print("no tuning.json yet")
        return
    d = json.loads(OUT.read_text(encoding="utf-8"))
    print(f"tuning run {d.get('generated')} over GW"
          f"{d['gw_window'][0]}-{d['gw_window'][1]} "
          f"({d.get('n_coarse')} coarse, {d.get('n_refined')} refined)\n")
    print(f"{'field_pct':>9} {'points':>7} {'worst5':>7} {'hits':>5}  params")
    for r in d.get("pareto", []):
        p = {k: v for k, v in r["params"].items() if k in SPACES}
        print(f"{r['field_pct']:>9.1f} {r['points']:>7} {r['worst5']:>7} "
              f"{r['hits']:>5}  {p}")
    wf = d.get("walk_forward")
    if wf:
        print(f"\nwalk-forward split at GW{wf['split_gw']}: train "
              f"{wf['train']['field_pct']:.1f} pct / {wf['train']['points']} pts "
              f"-> eval {wf['eval']['field_pct']:.1f} pct / {wf['eval']['points']} pts")
    print(f"\nbest: { {k: v for k, v in d['best']['params'].items() if k in SPACES} }")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-iter", type=int, default=24)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--from-gw", type=int, default=1)
    ap.add_argument("--until", type=int, default=6)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--collect", action="store_true",
                    help="merge shard results, refine the top 5, walk-forward")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    if a.report:
        report()
        return
    if a.collect:
        collect(a.from_gw, a.until)
        return

    replay = Replay()
    rows = coarse_stage(replay, a.n_iter, a.from_gw, a.until,
                        a.shard, a.nshards, a.seed)
    if rows:
        shard_file(a.shard).write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print(f"\nwrote {shard_file(a.shard)} ({len(rows)} configs); "
              f"finish with --collect")


if __name__ == "__main__":
    main()