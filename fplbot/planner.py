"""
Multi-gameweek transfer planner.

One integer program covering the whole horizon at once. It decides, for every
gameweek: who to sell, who to buy, whether to spend a free transfer or bank it,
whether a -4 hit is worth taking, the starting XI and the captain. Free transfers
accumulate to a maximum of five, exactly as the 2026/27 rules allow.

Chips are evaluated on top of the finished plan, because a chip is a season-level
decision and forcing it into the same program makes the model worse at the thing
it is actually good at.
"""
import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix, vstack

from .optimize import POS_MIN, SQUAD_N, best_xi, squad_report

HIT_COST = 4.0
MAX_FT = 5
DECAY = 0.85


def plan(pool, gws, current, free_transfers=1, bank=0.0, budget=None,
         bench_weight=0.12, max_per_club=3, allow_hits=True,
         locked=(), banned=(), own_bonus=0.0, min_differentials=None,
         max_captain_ownership=None, xp_prefix="xp", decay=DECAY, time_limit=300):
    """Return the optimal transfer plan over `gws` starting from `current`.

    free_transfers: how many you have available for the first gameweek.
    bank: money in the bank, in millions.
    allow_hits: when False, no gameweek may exceed its free-transfer allowance.
    """
    n, G = len(pool), len(gws)
    xp = np.array([[pool[f"{xp_prefix}{g}"].values[i] for g in gws] for i in range(n)])
    # always report in plain expected points, even when optimising on ceiling
    xp_true = np.array([[pool[f"xp{g}"].values[i] for g in gws] for i in range(n)])
    price = pool.price.values.astype(float)
    pos = pool.pos.values
    club = pool.team.values
    ids = pool.id.values
    own = pool.selected_by.values if "selected_by" in pool else np.zeros(n)
    idx = {int(v): i for i, v in enumerate(ids)}

    cur = [idx[p] for p in current if p in idx]
    if len(cur) != 15:
        raise ValueError(f"current squad resolved to {len(cur)} players, need 15")
    if budget is None:
        budget = float(price[cur].sum()) + float(bank)

    w = np.array([decay ** k for k in range(G)])

    # ---- variable layout -------------------------------------------------
    # x[i,g] squad | bin[i,g] transfer in | sout[i,g] transfer out
    # st[i,g] starts | cp[i,g] captain | ft[g] free transfers | ht[g] hits
    B = n * G
    OFF_X, OFF_IN, OFF_OUT, OFF_ST, OFF_CP = 0, B, 2 * B, 3 * B, 4 * B
    OFF_FT, OFF_HT = 5 * B, 5 * B + G
    N = 5 * B + 2 * G

    def X(i, g): return OFF_X + g * n + i
    def IN(i, g): return OFF_IN + g * n + i
    def OUT(i, g): return OFF_OUT + g * n + i
    def ST(i, g): return OFF_ST + g * n + i
    def CP(i, g): return OFF_CP + g * n + i

    c = np.zeros(N)
    for g in range(G):
        for i in range(n):
            c[ST(i, g)] -= (1 - bench_weight) * w[g] * xp[i, g]
            c[X(i, g)] -= bench_weight * w[g] * xp[i, g]
            c[CP(i, g)] -= w[g] * xp[i, g]
            if own_bonus and g == 0:
                c[X(i, g)] -= own_bonus * float(own[i])
        c[OFF_HT + g] += HIT_COST * w[g]

    A, lb, ub = [], [], []

    def add(rowmap, lo, hi):
        r = lil_matrix((1, N))
        for k, v in rowmap.items():
            r[0, k] = v
        A.append(r); lb.append(lo); ub.append(hi)

    for g in range(G):
        add({X(i, g): 1 for i in range(n)}, 15, 15)
        for p, cnt in SQUAD_N.items():
            add({X(i, g): 1 for i in range(n) if pos[i] == p}, cnt, cnt)
        add({X(i, g): float(price[i]) for i in range(n)}, 0, budget)
        for cl in set(club):
            add({X(i, g): 1 for i in range(n) if club[i] == cl}, 0, max_per_club)

        # squad continuity
        for i in range(n):
            if g == 0:
                prev = 1 if i in cur else 0
                add({X(i, g): 1, IN(i, g): -1, OUT(i, g): 1}, prev, prev)
            else:
                add({X(i, g): 1, X(i, g - 1): -1, IN(i, g): -1, OUT(i, g): 1}, 0, 0)
            add({IN(i, g): 1, X(i, g): -1}, -np.inf, 0)      # can't buy and not own
            add({OUT(i, g): 1, X(i, g): 1}, -np.inf, 1)      # can't sell and still own

        # transfers in must equal transfers out
        add({**{IN(i, g): 1 for i in range(n)},
             **{OUT(i, g): -1 for i in range(n)}}, 0, 0)

        # hits: transfers beyond the free allowance
        add({**{IN(i, g): 1 for i in range(n)},
             OFF_FT + g: -1, OFF_HT + g: -1}, -np.inf, 0)

        # free-transfer accounting: ft_{g+1} <= ft_g - (transfers - hits) + 1, cap 5
        if g + 1 < G:
            if g == 0 and free_transfers > MAX_FT:
                # the unlimited pre-season window does not carry over: everyone
                # starts gameweek 2 with exactly one free transfer
                add({OFF_FT + 1: 1}, 1, 1)
            else:
                add({OFF_FT + g + 1: 1, OFF_FT + g: -1,
                     **{IN(i, g): 1 for i in range(n)}, OFF_HT + g: -1}, -np.inf, 1)

        # lineup
        add({ST(i, g): 1 for i in range(n)}, 11, 11)
        for p, (lo, hi) in POS_MIN.items():
            add({ST(i, g): 1 for i in range(n) if pos[i] == p}, lo, hi)
        for i in range(n):
            add({ST(i, g): 1, X(i, g): -1}, -np.inf, 0)
            add({CP(i, g): 1, ST(i, g): -1}, -np.inf, 0)
            if pos[i] in ("GKP", "DEF"):
                add({CP(i, g): 1}, 0, 0)
            elif max_captain_ownership is not None and own[i] > max_captain_ownership:
                add({CP(i, g): 1}, 0, 0)   # a captain the whole field owns wins no rank
        add({CP(i, g): 1 for i in range(n)}, 1, 1)

    add({OFF_FT: 1}, free_transfers, free_transfers)

    # Team-brief constraints describe where the squad should END UP, not where it
    # already is. Applying them to every gameweek makes the problem infeasible for
    # anyone starting from a squad that breaks the brief - which is exactly the
    # situation the plan is supposed to fix.
    if min_differentials:
        cnt, thresh = min_differentials
        add({X(i, G - 1): 1 for i in range(n) if own[i] < thresh}, cnt, 15)
    owned_now = {int(ids[i]) for i in cur}
    for pid in locked:
        if pid in idx:
            span = range(G) if pid in owned_now else [G - 1]
            for g in span:
                add({X(idx[pid], g): 1}, 1, 1)
    for pid in banned:
        if pid in idx:
            # already owned: one gameweek's grace to sell; otherwise never buy
            span = range(1, G) if pid in owned_now else range(G)
            for g in span:
                add({X(idx[pid], g): 1}, 0, 0)

    integrality = np.ones(N)
    lo_b = np.zeros(N); hi_b = np.ones(N)
    for g in range(G):
        # before the gameweek-1 deadline transfers are unlimited, so the caller can
        # pass a free-transfer count above the usual cap of five
        cap = max(MAX_FT, free_transfers) if g == 0 else MAX_FT
        lo_b[OFF_FT + g], hi_b[OFF_FT + g] = 0, cap
        lo_b[OFF_HT + g], hi_b[OFF_HT + g] = 0, (15 if allow_hits else 0)

    res = milp(c=c, constraints=LinearConstraint(vstack(A).tocsr(),
                                                 np.array(lb), np.array(ub)),
               integrality=integrality, bounds=Bounds(lo_b, hi_b),
               options={"time_limit": time_limit, "mip_rel_gap": 2e-4})
    if not res.success:
        return None

    x = np.round(res.x).astype(int)
    weeks = []
    for g in range(G):
        squad = [int(ids[i]) for i in range(n) if x[X(i, g)]]
        weeks.append({
            "gw": gws[g],
            "squad": squad,
            "in": [int(ids[i]) for i in range(n) if x[IN(i, g)]],
            "out": [int(ids[i]) for i in range(n) if x[OUT(i, g)]],
            "xi": [int(ids[i]) for i in range(n) if x[ST(i, g)]],
            "captain": next(int(ids[i]) for i in range(n) if x[CP(i, g)]),
            "free_transfers": int(x[OFF_FT + g]),
            "hits": int(x[OFF_HT + g]),
            "xp": round(float(sum(xp_true[i, g] for i in range(n) if x[ST(i, g)])
                              + sum(xp_true[i, g] for i in range(n) if x[CP(i, g)])
                              - HIT_COST * x[OFF_HT + g]), 2),
            "bank": round(budget - float(sum(price[i] for i in range(n) if x[X(i, g)])), 1),
        })
    return {"weeks": weeks,
            "objective": round(-res.fun, 2),
            "total_xp": round(sum(wk["xp"] for wk in weeks), 2),
            "total_hits": sum(wk["hits"] for wk in weeks),
            "transfers": sum(len(wk["in"]) for wk in weeks)}


def plan_with_hit_policy(pool, gws, current, hit_threshold=6.0, **kw):
    """Solve twice - with and without hits - and only take the hit if it pays.

    A -4 is worth taking only when the extra points clearly beat the cost, so the
    hit plan has to gain more than `hit_threshold` over the best plan that spends
    nothing but free transfers. Minoux_69 uses a high threshold, Minoux_41 a low one.
    """
    with_hits = plan(pool, gws, current, allow_hits=True, **kw)
    no_hits = plan(pool, gws, current, allow_hits=False, **kw)
    if with_hits is None and no_hits is None:
        return None, {"infeasible": True, "threshold": hit_threshold,
                      "advice": "the brief cannot be met from this squad inside the "
                                "horizon - this is what a wildcard is for"}
    if with_hits is None:
        return no_hits, {"took_hits": False, "gain_over_no_hit": None,
                         "threshold": hit_threshold}
    if no_hits is None:
        return with_hits, {"took_hits": True, "hits": with_hits["total_hits"],
                           "gain_over_no_hit": None, "threshold": hit_threshold,
                           "advice": "no plan without hits satisfies this team's brief - "
                                     "consider a wildcard instead of paying the hits"}
    if with_hits["total_hits"] == 0:
        return with_hits, {"took_hits": False, "gain_over_no_hit": 0.0,
                           "threshold": hit_threshold}
    gain = with_hits["objective"] - no_hits["objective"]
    if gain < hit_threshold:
        return no_hits, {"took_hits": False, "gain_over_no_hit": round(gain, 2),
                         "rejected_hits": with_hits["total_hits"],
                         "threshold": hit_threshold}
    return with_hits, {"took_hits": True, "gain_over_no_hit": round(gain, 2),
                       "hits": with_hits["total_hits"], "threshold": hit_threshold}


# ------------------------------------------------------------------- chips --
def evaluate_chips(df, weeks, gws):
    """Value of each chip in each gameweek of the plan, on top of the plan itself."""
    out = []
    for wk in weeks:
        g = wk["gw"]
        squad = df[df.id.isin(wk["squad"])]
        xi = df[df.id.isin(wk["xi"])]
        bench = squad[~squad.id.isin(wk["xi"])]
        cap = df[df.id == wk["captain"]].iloc[0]
        att = xi[xi.pos.isin(["MID", "FWD"])]
        best_tc = att[f"xp{g}"].max() if len(att) else 0.0
        out.append({
            "gw": g,
            "triple_captain": round(float(best_tc), 2),
            "bench_boost": round(float(bench[f"xp{g}"].sum()), 2),
            "captain": cap["name"],
            "note": "",
        })
    return out


def wildcard_gain(pool, df, gws, current, base_objective, **kw):
    """How much a wildcard this gameweek would be worth versus the normal plan."""
    from .optimize import solve
    kw = {k: v for k, v in kw.items()
          if k in ("budget", "locked", "banned", "own_bonus",
                   "min_differentials", "xp_prefix", "max_per_club")}
    wc = solve(pool, gws, allow_infeasible=True, **kw)
    if wc is None:
        return None
    rep = squad_report(df, wc["squad"], gws)
    return {"squad": wc["squad"], "xp_total": rep["xp_total"],
            "gain": round(rep["xp_total"] - base_objective, 2)}
