"""
Replay a finished season through the engine and see what it would have scored.

This is the only honest test of whether the model is worth anything. It walks
2025-26 gameweek by gameweek, and at every deadline it may use ONLY what was
knowable at that moment: the previous season in full, plus this season's results
up to the previous gameweek, plus each player's price as it was that week.

Two arms run side by side so the weekly transfer decision can be judged on its
own: the managed team makes the optimiser's transfer every week, and the frozen
team keeps the gameweek-1 squad all season and only picks its best eleven.

Usage:  python3 tools/backtest.py --season 2025-26 --prior 2024-25 --data /tmp/fplhist/data
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np                                    # noqa: E402
import pandas as pd                                   # noqa: E402

from fplbot import model, optimize                    # noqa: E402

POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def load(data, season, prior):
    d = Path(data)
    cur = {
        "players": pd.read_csv(d / season / "players_raw.csv"),
        "teams": pd.read_csv(d / season / "teams.csv"),
        "fixtures": pd.read_csv(d / season / "fixtures.csv"),
        "gw": pd.read_csv(d / season / "gws" / "merged_gw.csv",
                          encoding="utf-8", on_bad_lines="skip"),
    }
    prev = {
        "players": pd.read_csv(d / prior / "players_raw.csv"),
        "teams": pd.read_csv(d / prior / "teams.csv"),
        "gw": pd.read_csv(d / prior / "gws" / "merged_gw.csv",
                          encoding="utf-8", on_bad_lines="skip"),
    }
    return cur, prev


def prices_at(cur, gw):
    """Each player's price as it was that week - never the end-of-season price."""
    g = cur["gw"]
    upto = g[g.GW <= max(gw - 1, 1)]
    if not len(upto):
        upto = g[g.GW == g.GW.min()]
    last = upto.sort_values("GW").groupby("element")["value"].last()
    return last.to_dict()


def frame_for(cur, gw):
    """The player table as it looked before gameweek `gw` kicked off."""
    p = cur["players"].copy()
    pr = prices_at(cur, gw)
    p["now_cost"] = p["id"].map(pr).fillna(p["now_cost"]).astype(int)
    # end-of-season availability is hindsight, so everyone is treated as fit and
    # the minutes model carries the rotation risk on its own
    p["status"] = "a"
    p["news"] = ""
    p["chance_of_playing_next_round"] = np.nan
    return p


def actual_points(cur):
    g = cur["gw"]
    return {(int(r.element), int(r.GW)): int(r.total_points)
            for r in g.itertuples() if pd.notna(r.total_points)}


def score(df, squad, gw, pts, cap_pool=("MID", "FWD")):
    """Best legal eleven from a squad, captain the top attacker, then score it."""
    s = df[df.id.isin(squad)].copy()
    if not len(s):
        return 0, None, []
    s["proj"] = s[f"xp{gw}"] if f"xp{gw}" in s.columns else 0.0
    xi, _ = optimize.best_xi(df, squad, gw)
    ids = [int(r.id) for r in xi]
    att = [r for r in xi if r.pos in cap_pool] or xi
    cap = max(att, key=lambda r: r[f"xp{gw}"])
    total = sum(pts.get((i, gw), 0) for i in ids) + pts.get((int(cap.id), gw), 0)
    return total, int(cap.id), ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2025-26")
    ap.add_argument("--prior", default="2024-25")
    ap.add_argument("--data", default="/tmp/fplhist/data")
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--until", type=int, default=38)
    ap.add_argument("--out", default="backtest.json")
    a = ap.parse_args()

    cur, prev = load(a.data, a.season, a.prior)
    pts = actual_points(cur)
    fx = cur["fixtures"]
    t0 = time.time()

    managed, frozen = None, None
    rows, ft = [], 1
    for gw in range(1, a.until + 1):
        hist = cur["gw"][cur["gw"].GW < gw]
        frames = (frame_for(cur, gw), cur["teams"], fx)
        try:
            df, teams, _, gws = model.build(
                horizon=min(a.horizon, 39 - gw), start_gw=gw,
                frames=frames, gw26=hist if len(hist) else None,
                prev_frames=(prev["players"], prev["teams"], prev["gw"]))
        except TypeError:                    # engine without the prev_frames hook
            df, teams, _, gws = model.build(
                horizon=min(a.horizon, 39 - gw), start_gw=gw,
                frames=frames, gw26=hist if len(hist) else None)
        pool = optimize.prune(df, gws, always=(managed or []) + (frozen or []))

        if managed is None:
            first = optimize.solve(pool, gws, allow_infeasible=True)
            if first is None:
                print("could not build a gameweek 1 squad"); return
            managed = frozen = first["squad"]
            moved = []
        else:
            r = optimize.solve(pool, gws, max_changes=ft, current=managed,
                               allow_infeasible=True)
            if r is not None:
                moved = sorted(set(r["squad"]) - set(managed))
                used = len(moved)
                managed = r["squad"]
                ft = min(5, ft - used + 1) if used <= ft else 1
            else:
                moved = []
                ft = min(5, ft + 1)

        m_pts, m_cap, _ = score(df, managed, gw, pts)
        f_pts, _, _ = score(df, frozen, gw, pts)
        name = df.set_index("id").name.to_dict()
        rows.append({"gw": gw, "managed": m_pts, "frozen": f_pts,
                     "captain": name.get(m_cap), "transfers": len(moved),
                     "free_transfers": ft,
                     "in": [name.get(i) for i in moved]})
        print(f"GW{gw:2d}  managed {m_pts:3d}  frozen {f_pts:3d}  "
              f"C {str(name.get(m_cap))[:14]:14s} "
              f"({len(moved)} transfer{'s' if len(moved) != 1 else ''})")

    tot_m = sum(r["managed"] for r in rows)
    tot_f = sum(r["frozen"] for r in rows)
    print(f"\nmanaged {tot_m}   frozen {tot_f}   difference {tot_m - tot_f:+d}")
    print(f"mean per gameweek: managed {tot_m/len(rows):.1f}, frozen {tot_f/len(rows):.1f}")
    print(f"ran in {time.time() - t0:.0f}s")
    Path(a.out).write_text(json.dumps(
        {"season": a.season, "weeks": rows,
         "managed_total": tot_m, "frozen_total": tot_f}, indent=1))


if __name__ == "__main__":
    main()
