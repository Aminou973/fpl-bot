"""
Golden-file checker: hash the offline projections and the first planned week.

A deliberately small set of anchors so a silent model change cannot slip
through: the projections hash covers every player's xp, ceiling and start
probability for the offline horizon; the plan hash covers the first week's
transfers, captain, hits and free transfers for both configured teams.

Usage:  python tools/selfcheck.py                 # verify against golden/
        python tools/selfcheck.py --rebaseline    # rewrite golden/ (deliberate)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fplbot import model, pipeline, planner, optimize   # noqa: E402

GOLDEN = ROOT / "tests" / "golden"


def projection_frame(df, gws):
    cols = (["id", "name", "pos", "team", "price", "start_share", "avail",
             "selected_by", "xp_total", "ceiling_total"]
            + [f"xp{g}" for g in gws] + [f"q85{g}" for g in gws]
            + [f"q95{g}" for g in gws] + [f"p_start{g}" for g in gws])
    return df[cols].round(4)


def first_week_plan(df, gws):
    out = {}
    for team, t in pipeline.load_config()["teams"].items():
        squad, source = pipeline.resolve_squad_traced(
            df, None, by_name=[tuple(x) for x in t["squad"]])
        if len(squad) < 15:
            # offline snapshot may not know every fallback player (moves etc.);
            # top up deterministically so the golden plan still anchors the solver
            have = set(squad)
            pool_all = df.sort_values("xp_total", ascending=False)
            for pid in pool_all["id"]:
                if len(squad) >= 15:
                    break
                if int(pid) not in have:
                    squad.append(int(pid))
                    have.add(int(pid))
        pool = optimize.prune(df, gws, always=squad)
        plan, info = planner.plan_with_hit_policy(
            pool, gws, squad,
            hit_threshold=t.get("hit_threshold", 6.0),
            free_transfers=t.get("free_transfers", 1),
            **pipeline.team_kwargs(df, t))
        if plan is None:
            out[team] = {"infeasible": True}
            continue
        wk = plan["weeks"][0]
        names = df.set_index("id").name.to_dict()
        out[team] = {
            "in": sorted(names[i] for i in wk["in"]),
            "out": sorted(names[i] for i in wk["out"]),
            "captain": names[wk["captain"]],
            "hits": wk["hits"],
            "free_transfers": wk["free_transfers"],
            "xp": wk["xp"],
        }
    return out


def compute():
    df, teams, fx, gws = model.build(horizon=5, start_gw=3)
    proj = projection_frame(df, gws).to_csv(index=False)
    plan = first_week_plan(df, gws)
    return {
        "projections_sha": hashlib.sha256(proj.encode()).hexdigest(),
        "plan": plan,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rebaseline", action="store_true")
    a = ap.parse_args()
    cur = compute()
    gold_path = GOLDEN / "selfcheck.json"
    if a.rebaseline:
        GOLDEN.mkdir(parents=True, exist_ok=True)
        gold_path.write_text(json.dumps(cur, indent=1, sort_keys=True))
        print(f"rebaselined {gold_path}")
        return
    gold = json.loads(gold_path.read_text())
    ok = True
    if cur["projections_sha"] != gold["projections_sha"]:
        ok = False
        print("MISMATCH: offline projections changed "
              "(model math or distribution layer moved)")
    for team in gold["plan"]:
        if cur["plan"].get(team) != gold["plan"][team]:
            ok = False
            print(f"MISMATCH: first-week plan for {team} changed")
            print("  golden:", json.dumps(gold["plan"][team], sort_keys=True))
            print("  now:   ", json.dumps(cur["plan"].get(team)))
    if ok:
        print("selfcheck OK: projections and first-week plans match golden files")
    else:
        print("selfcheck FAILED — if this change is intended, run "
              "tools/selfcheck.py --rebaseline and commit the diff")
        sys.exit(1)


if __name__ == "__main__":
    main()