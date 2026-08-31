"""
FPL squad optimiser.

Exact integer program (HiGHS via scipy.optimize.milp) that maximises weighted
expected points over a multi-gameweek horizon subject to the official rules:
  15 players - 2 GKP / 5 DEF / 5 MID / 3 FWD
  max 3 players from any one club
  budget 100.0m
  a legal starting XI each gameweek (1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD)
  one captain (points doubled)
"""
import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix

POS_MIN = {"GKP": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}
SQUAD_N = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
BENCH_W = 0.12          # bench points are worth something, but not much
DEFAULT_WEIGHTS = [1.0, 0.55, 0.35, 0.22, 0.15]


def prune(df, gws, keep_top=150, per_bucket=4, always=()):
    """Shrink the candidate pool without discarding anything competitive."""
    d = df[(df.avail > 0) & (df.xp_total > 0)].copy()
    keep = set(d.nlargest(keep_top, "xp_total").id)
    keep |= set(d.nlargest(60, "value").id)
    for (pos, price), grp in d.groupby(["pos", "price"]):
        keep |= set(grp.nlargest(per_bucket, "xp_total").id)
    keep |= set(always)
    return df[df.id.isin(keep)].reset_index(drop=True)


def solve(pool, gws, budget=100.0, weights=None, locked=(), banned=(),
          max_changes=None, current=(), bench_weight=BENCH_W,
          max_per_club=3, time_limit=120, xp_prefix="xp",
          own_bonus=0.0, min_differentials=None, differ_from=None,
          min_differences=0, allow_infeasible=False):
    """min_differentials: (count, ownership_pct) - require at least `count`
    players owned by fewer than `ownership_pct` of managers.
    differ_from / min_differences: force at least N players not in that squad.
    own_bonus: points added per 1% ownership, to tilt toward the template."""
    w = (weights or DEFAULT_WEIGHTS)[: len(gws)]
    w = np.array(w, dtype=float)
    w = w / w.sum() * len(w)

    n = len(pool)
    G = len(gws)
    xp = np.array([[pool[f"{xp_prefix}{g}"].values[i] for g in gws] for i in range(n)])
    price = pool.price.values
    pos = pool.pos.values
    club = pool.team.values
    ids = pool.id.values
    own = pool.selected_by.values if "selected_by" in pool else np.zeros(n)

    # variable blocks: squad(n) | start_g(n) for each g | captain(n) for gw1
    nS, nX, nC = n, n * G, n
    N = nS + nX + nC

    def xi(i, g):
        return nS + g * n + i

    def ci(i):
        return nS + nX + i

    c = np.zeros(N)
    for i in range(n):
        c[i] -= bench_weight * float(np.dot(w, xp[i]))          # bench value
        for g in range(G):
            c[xi(i, g)] -= (1 - bench_weight) * w[g] * xp[i, g]  # promote to XI
        c[ci(i)] -= w[0] * xp[i, 0]                              # captain bonus
        if own_bonus:
            c[i] -= own_bonus * float(own[i])                    # template safety

    A, lb, ub = [], [], []

    def add(rowmap, lo, hi):
        r = lil_matrix((1, N))
        for k, v in rowmap.items():
            r[0, k] = v
        A.append(r)
        lb.append(lo)
        ub.append(hi)

    add({i: 1 for i in range(n)}, 15, 15)
    for p, cnt in SQUAD_N.items():
        add({i: 1 for i in range(n) if pos[i] == p}, cnt, cnt)
    add({i: float(price[i]) for i in range(n)}, 0, budget)
    for cl in set(club):
        add({i: 1 for i in range(n) if club[i] == cl}, 0, max_per_club)

    for g in range(G):
        add({xi(i, g): 1 for i in range(n)}, 11, 11)
        for p, (lo, hi) in POS_MIN.items():
            add({xi(i, g): 1 for i in range(n) if pos[i] == p}, lo, hi)
        for i in range(n):
            add({xi(i, g): 1, i: -1}, -np.inf, 0)          # start => in squad

    add({ci(i): 1 for i in range(n)}, 1, 1)
    for i in range(n):
        add({ci(i): 1, xi(i, 0): -1}, -np.inf, 0)          # captain must start
        if pos[i] in ("GKP", "DEF"):
            add({ci(i): 1}, 0, 0)   # nobody captains a defender in practice

    idx = {int(v): i for i, v in enumerate(ids)}
    for pid in locked:
        if pid in idx:
            add({idx[pid]: 1}, 1, 1)
    for pid in banned:
        if pid in idx:
            add({idx[pid]: 1}, 0, 0)
    if min_differentials:
        cnt, thresh = min_differentials
        add({i: 1 for i in range(n) if own[i] < thresh}, cnt, 15)
    if differ_from is not None and min_differences:
        keep = [idx[p] for p in differ_from if p in idx]
        add({i: 1 for i in keep}, 0, 15 - min_differences)
    if max_changes is not None and len(current):
        cur = [idx[p] for p in current if p in idx]
        # keeping at least 15 - max_changes of the current squad
        add({i: 1 for i in cur}, 15 - max_changes, 15)

    from scipy.sparse import vstack
    cons = LinearConstraint(vstack(A).tocsr(), np.array(lb), np.array(ub))
    res = milp(c=c, constraints=cons, integrality=np.ones(N),
               bounds=Bounds(0, 1),
               options={"time_limit": time_limit, "mip_rel_gap": 1e-4})
    if not res.success:
        if allow_infeasible:
            return None
        raise RuntimeError(f"optimiser failed: {res.message}")

    x = np.round(res.x).astype(int)
    squad = [int(ids[i]) for i in range(n) if x[i]]
    lineups = {gws[g]: [int(ids[i]) for i in range(n) if x[xi(i, g)]] for g in range(G)}
    captain = next(int(ids[i]) for i in range(n) if x[ci(i)])
    return {"squad": squad, "lineups": lineups, "captain": captain,
            "objective": -res.fun}


# ----------------------------------------------------------------- reporting --
def best_xi(df, squad_ids, gw):
    """Highest-scoring legal XI from a 15 for one gameweek, plus bench order."""
    s = df[df.id.isin(squad_ids)].copy().sort_values(f"xp{gw}", ascending=False)
    xi_, bench = [], []
    gks = s[s.pos == "GKP"]
    if not len(gks):
        raise ValueError(f"squad has no goalkeeper: {sorted(squad_ids)}")
    xi_.append(gks.iloc[0])
    # a free-hit or partially resolved 15 can carry a single keeper: the XI is
    # still legal, there is simply no keeper to put on the bench
    bench_gk = gks.iloc[1] if len(gks) > 1 else None
    out = s[s.pos != "GKP"]
    need = {"DEF": 3, "MID": 2, "FWD": 1}
    for p, k in need.items():
        sel = out[out.pos == p].head(k)
        xi_ += [r for _, r in sel.iterrows()]
        out = out[~out.id.isin(sel.id)]
    xi_ += [r for _, r in out.head(4).iterrows()]
    used = {r.id for r in xi_}
    bench = [r for _, r in s.iterrows() if r.id not in used and r.pos != "GKP"]
    return xi_, ([bench_gk] if bench_gk is not None else []) + bench


def pick_vice(df, xi_ids, captain_id, gw, max_ownership=None):
    """Best armband deputy: the vice only counts if the captain plays no minutes.

    Taken from a different club than the captain, because the one scenario that
    strands you is both of them in a match that never happens - a postponement,
    an abandonment, a shared rest week.
    """
    s = df[df.id.isin(xi_ids) & (df.id != captain_id)]
    cap = df[df.id == captain_id]
    if len(cap):
        s = s[s.team != cap.iloc[0].team]
    s = s[s.pos.isin(["MID", "FWD"])]
    if max_ownership is not None:
        capped = s[s.selected_by <= max_ownership]
        if len(capped):
            s = capped
    if not len(s):
        s = df[df.id.isin(xi_ids) & (df.id != captain_id)]
    if not len(s):
        return None
    return int(s.sort_values(f"xp{gw}", ascending=False).iloc[0].id)


def squad_report(df, squad_ids, gws, max_captain_ownership=None):
    s = df[df.id.isin(squad_ids)]
    rep = {"cost": round(float(s.price.sum()), 1), "gws": {}}
    for gw in gws:
        xi_, bench = best_xi(df, squad_ids, gw)
        att = [r for r in xi_ if r.pos in ("MID", "FWD")] or xi_
        if max_captain_ownership is not None:
            capped = [r for r in att if r.selected_by <= max_captain_ownership]
            att = capped or att
        cap = max(att, key=lambda r: r[f"xp{gw}"])
        xi_ids = [int(r.id) for r in xi_]
        vice = pick_vice(df, xi_ids, int(cap.id), gw, max_captain_ownership)
        rep["gws"][gw] = {
            "xi": xi_ids,
            "bench": [int(r.id) for r in bench],
            "captain": int(cap.id),
            "vice": vice,
            "xp": round(sum(r[f"xp{gw}"] for r in xi_) + cap[f"xp{gw}"], 2),
        }
    rep["xp_total"] = round(sum(v["xp"] for v in rep["gws"].values()), 2)
    return rep
