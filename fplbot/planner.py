"""
Multi-gameweek transfer planner.

One integer program covering the whole horizon at once. It decides, for every
gameweek: who to sell, who to buy, whether to spend a free transfer or bank it,
whether a -4 hit is worth taking, the starting XI and the captain. Free transfers
accumulate to a maximum of five, exactly as the 2026/27 rules allow.

Chips are handled in two tiers, because they are not the same kind of decision.
Bench boost and triple captain only change how the CURRENT squad scores in one
gameweek, so they are pure objective/lineup changes and belong inside the ILP
(blocks TC/BB/Y below) - sequencing them after the solve would score them
against a plan built as if they did not exist. Wildcard and free hit rewrite
the whole squad, which as an ILP constraint needs a big-M continuity
relaxation that wrecks the model - so they are branch evaluations instead
(wildcard_plan / freehit_plan), compared against the base plan by
chip_branches at the calendar's flagged weeks.
"""
import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix, vstack

from .optimize import POS_MIN, SQUAD_N, best_xi, pick_vice, squad_report

HIT_COST = 4.0
MAX_FT = 5
DECAY = 0.85


def attach_vice(df, weeks, max_captain_ownership=None):
    """Fill in the vice-captain for every gameweek of a finished plan."""
    for wk in weeks:
        wk["vice"] = pick_vice(df, wk["xi"], wk["captain"], wk["gw"],
                               max_captain_ownership)
    return weeks


def plan(pool, gws, current, free_transfers=1, bank=0.0, budget=None,
         bench_weight=0.12, max_per_club=3, allow_hits=True,
         locked=(), banned=(), own_bonus=0.0, min_differentials=None,
         max_captain_ownership=None, xp_prefix="xp", decay=DECAY, time_limit=300,
         scenarios=None, scenario_weights=None, risk_lambda=0.0, cvar_beta=0.75,
         rank_alpha=0.0, template_tilt=0.0, cap_tilt=0.0, elite_weight=0.0,
         chips_tc_bb=False, chip_windows=None, chips_used=(),
         price_matrix=None, sell_price=None, price_gamma=0.0):
    """Return the optimal transfer plan over `gws` starting from `current`.

    free_transfers: how many you have available for the first gameweek.
    bank: money in the bank, in millions.
    allow_hits: when False, no gameweek may exceed its free-transfer allowance.
    scenarios: (S, n, G) point samples aligned with `pool`'s rows, from
        fplbot.scenarios.scenario_set. With risk_lambda > 0 the objective
        becomes mean + risk_lambda * CVaR over these scenarios (Rockafellar-
        Uryasev epigraph), so correlated bad weeks are priced in. With
        risk_lambda = 0 the scenario set is ignored entirely and the model is
        bit-identical to the deterministic one - asserted in the test suite.
    rank_alpha / elite_weight / template_tilt / cap_tilt: engine 1. rank_alpha > 0 rescales
        each gameweek's weight by the field's score density at your squad's
        projection (points are worth more when the field is bunched around
        you); template_tilt adds a signed per-ownership term to squad picks
        (positive = template-safe, negative = differential), cap_tilt rewards
        low-owned captains. All three are scalars; the field model lives in
        fplbot.template.
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
    ew = float(np.clip(elite_weight, 0.0, 1.0))
    if ew and "elite_by" in pool:
        # engine 1b: blend the field's ownership with the elite template's
        # (fplbot.elite). A column that is missing silently degrades to the
        # field's share, so offline/selfcheck runs stay bit-identical.
        own = (1.0 - ew) * own + ew * pool.elite_by.values.astype(float)
    idx = {int(v): i for i, v in enumerate(ids)}

    cur = [idx[p] for p in current if p in idx]
    if len(cur) != 15:
        raise ValueError(f"current squad resolved to {len(cur)} players, need 15")
    if budget is None:
        if sell_price is not None:
            budget = float(np.asarray(sell_price)[cur].sum()) + float(bank)
        else:
            budget = float(price[cur].sum()) + float(bank)

    w = np.array([decay ** k for k in range(G)])

    # engine 1: rescale the time weights by the field's density at your score
    if rank_alpha and "selected_by" in pool and float(own.max()) > 0:
        from .template import rank_weight
        m = rank_weight(pool, gws, cur, alpha=float(rank_alpha))
        w = w * m
    tilt = float(np.clip(template_tilt, -1.0, 1.0))

    # engine 5: buying a predicted riser now is cheaper than in three weeks,
    # so the budget row uses an expected per-deadline price matrix; the sell
    # haircut prices owned players at what FPL actually pays back for them
    use_price = price_matrix is not None
    if use_price:
        pm = np.asarray(price_matrix, dtype=float)
        if pm.shape != (n, G):
            raise ValueError(f"price_matrix shape {pm.shape}, want {(n, G)}")
    else:
        pm = np.tile(price.reshape(n, 1), (1, G))

    # ---- variable layout -------------------------------------------------
    # x[i,g] squad | bin[i,g] transfer in | sout[i,g] transfer out
    # st[i,g] starts | cp[i,g] captain | ft[g] free transfers | ht[g] hits
    # with risk active: zeta[g] CVaR pivot (free) | u[s,g] epigraph slack >= 0
    B = n * G
    OFF_X, OFF_IN, OFF_OUT, OFF_ST, OFF_CP = 0, B, 2 * B, 3 * B, 4 * B
    OFF_FT, OFF_HT = 5 * B, 5 * B + G
    N = 5 * B + 2 * G

    use_risk = bool(risk_lambda) and scenarios is not None
    OFF_ZETA = OFF_U = None
    S = 0
    if use_risk:
        S = scenarios.shape[0]
        OFF_ZETA, OFF_U = 5 * B + 2 * G, 5 * B + 2 * G + G
        N = 5 * B + 2 * G + G + S * G
        if scenario_weights is None:
            scenario_weights = np.full(S, 1.0 / S)

    # Tier A chips: triple captain and bench boost as ILP blocks. TC(i,g)
    # triples the captain, BB(i,g) pays a bench player in full; Y are the
    # one-chip-per-week switches. Window legality and already-used chips pin
    # Y to 0 outside the legal weeks, so the solver cannot break either rule.
    use_chips = bool(chips_tc_bb)
    OFF_TC = OFF_BB = OFF_YTC = OFF_YBB = None
    chip_ok = {"3xc": [], "bboost": []}
    if use_chips:
        OFF_TC, OFF_BB = N, N + B
        OFF_YTC, OFF_YBB = N + 2 * B, N + 2 * B + G
        N = N + 2 * B + 2 * G
        used = set(chips_used or ())
        for key, name in (("3xc", "3xc"), ("bboost", "bboost")):
            if name in used:
                chip_ok[key] = []
                continue
            for wdw in (chip_windows or {}).get(key, []):
                chip_ok[key].append((wdw["start"], wdw["stop"]))

    def X(i, g): return OFF_X + g * n + i
    def IN(i, g): return OFF_IN + g * n + i
    def OUT(i, g): return OFF_OUT + g * n + i
    def ST(i, g): return OFF_ST + g * n + i
    def CP(i, g): return OFF_CP + g * n + i

    c = np.zeros(N)
    for g in range(G):
        gw = gws[g]
        tc_ok = any(a <= gw <= b for a, b in chip_ok["3xc"])
        bb_ok = any(a <= gw <= b for a, b in chip_ok["bboost"])
        for i in range(n):
            c[ST(i, g)] -= (1 - bench_weight) * w[g] * xp[i, g]
            # engine 1: the tilt is xp-weighted (a 14-pointer moves rank more
            # than a 3-pointer per 1% owned) and applies every gameweek, not
            # just the first. The own_bonus path below is the deprecated
            # g==0-only form, kept only while engines.rank is disabled.
            c[X(i, g)] -= bench_weight * w[g] * xp[i, g]
            if tilt:
                c[X(i, g)] -= tilt * w[g] * (float(own[i]) / 100.0) * xp[i, g]
            elif own_bonus and g == 0:
                c[X(i, g)] -= own_bonus * float(own[i])
            c[CP(i, g)] -= w[g] * xp[i, g] * (1.0 + cap_tilt * (1.0 - float(own[i]) / 100.0))
            if use_price and price_gamma:
                # bounded timing reward: buying a predicted riser before he
                # rises earns gamma points per £0.1m of avoided rise
                c[IN(i, g)] -= (price_gamma * w[g]
                                * max(0.0, float(pm[i, g] - price[i])))
        c[OFF_HT + g] += HIT_COST * decay ** g
        if use_risk:
            # CVaR_b(score) = max_zeta { zeta - E[(zeta - score)+] / (1 - b) };
            # in minimisation terms the pivot is bought, the slack is paid for
            c[OFF_ZETA + g] -= risk_lambda * w[g]
            for s in range(S):
                c[OFF_U + s * G + g] += (risk_lambda * w[g]
                                         * float(scenario_weights[s])
                                         / (1.0 - cvar_beta))
        if tc_ok:
            # the captain already earns double via CP; the chip adds the third
            for i in range(n):
                c[OFF_TC + g * n + i] -= w[g] * xp[i, g]
        if bb_ok:
            # bench players already earn bench_weight via X; the chip pays the rest
            for i in range(n):
                c[OFF_BB + g * n + i] -= (1 - bench_weight) * w[g] * xp[i, g]

    A, lb, ub = [], [], []

    def add(rowmap, lo, hi):
        r = lil_matrix((1, N))
        for k, v in rowmap.items():
            r[0, k] = v
        A.append(r); lb.append(lo); ub.append(hi)

    if use_risk:
        # epigraph: u[s,g] >= zeta[g] - score(s,g), where a scenario's score is
        # the same bench-weighted lineup score as the mean objective, only with
        # scenario points instead of expected points
        for s in range(S):
            ps = scenarios[s]                       # (n, G)
            for g in range(G):
                row = {OFF_U + s * G + g: 1.0, OFF_ZETA + g: -1.0}
                for i in range(n):
                    p = float(ps[i, g])
                    if p:
                        row[ST(i, g)] = (1 - bench_weight) * p
                        row[X(i, g)] = row.get(X(i, g), 0.0) + bench_weight * p
                        row[CP(i, g)] = row.get(CP(i, g), 0.0) + p
                add(row, 0.0, np.inf)

    for g in range(G):
        add({X(i, g): 1 for i in range(n)}, 15, 15)
        for p, cnt in SQUAD_N.items():
            add({X(i, g): 1 for i in range(n) if pos[i] == p}, cnt, cnt)
        # budget at each deadline's expected prices, not today's
        add({X(i, g): float(pm[i, g]) for i in range(n)}, 0, budget)
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

        # Tier A chip mechanics
        if use_chips:
            for i in range(n):
                add({OFF_TC + g * n + i: 1, CP(i, g): -1}, -np.inf, 0)   # chip only on the captain
                add({OFF_TC + g * n + i: 1, OFF_YTC + g: -1}, -np.inf, 0)
                add({OFF_BB + g * n + i: 1, X(i, g): -1, ST(i, g): 1}, -np.inf, 0)
            add({**{OFF_TC + g * n + i: 1 for i in range(n)}, OFF_YTC + g: -1}, 0, 0)
            add({**{OFF_BB + g * n + i: 1 for i in range(n)},
                 OFF_YBB + g: -4}, 0, 0)                     # exactly the 4 bench spots
            add({OFF_YTC + g: 1, OFF_YBB + g: 1}, -np.inf, 1)  # one chip per week

    add({OFF_FT: 1}, free_transfers, free_transfers)

    # each chip is a season resource: once per half, never twice
    if use_chips:
        add({OFF_YTC + g: 1 for g in range(G)}, 0, 1)
        add({OFF_YBB + g: 1 for g in range(G)}, 0, 1)

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
    if use_risk:
        # zeta is free, the epigraph slacks are nonnegative and continuous
        # end both slices explicitly: with Tier A chips active the U block is
        # not the tail of the variable vector - the TC/BB blocks follow it, and
        # they must stay binary and bounded at 1
        integrality[OFF_ZETA:OFF_U + S * G] = 0
        lo_b[OFF_ZETA:OFF_ZETA + G] = -np.inf
        hi_b[OFF_ZETA:OFF_ZETA + G] = np.inf
        hi_b[OFF_U:OFF_U + S * G] = np.inf
    if use_chips:
        for g in range(G):
            gw = gws[g]
            hi_b[OFF_YTC + g] = 1 if any(a <= gw <= b for a, b in chip_ok["3xc"]) else 0
            hi_b[OFF_YBB + g] = 1 if any(a <= gw <= b for a, b in chip_ok["bboost"]) else 0

    res = milp(c=c, constraints=LinearConstraint(vstack(A).tocsr(),
                                                 np.array(lb), np.array(ub)),
               integrality=integrality, bounds=Bounds(lo_b, hi_b),
               options={"time_limit": time_limit, "mip_rel_gap": 2e-4})
    if not res.success:
        return None

    x = np.round(res.x).astype(int)
    # HiGHS status 1 means the time/iteration limit stopped the search: the
    # result is usable but no longer provably optimal, so callers comparing
    # two solves must not treat the gap between them as exact
    solve_info = {"status": int(res.status),
                  "mip_gap": round(float(getattr(res, "mip_gap", 0.0) or 0.0), 6)}
    # the hit policy must judge a -4 in points, not in risk-adjusted units, so
    # the plan also reports the mean component alone (== objective when no risk)
    mean_obj = -res.fun
    if use_risk:
        zeta = res.x[OFF_ZETA:OFF_ZETA + G]
        # end the slice explicitly: with Tier A chips active the U block is
        # not the tail of the variable vector - the TC/BB blocks follow it
        u = res.x[OFF_U:OFF_U + S * G].reshape(S, G)
        risk_val = sum(
            risk_lambda * w[g] * (zeta[g]
                                  + float(np.dot(scenario_weights, u[:, g]))
                                  / (1.0 - cvar_beta))
            for g in range(G))
        mean_obj -= risk_val
    weeks = []
    for g in range(G):
        squad = [int(ids[i]) for i in range(n) if x[X(i, g)]]
        chip = None
        if use_chips:
            if x[OFF_YTC + g]:
                chip = "3xc"
            elif x[OFF_YBB + g]:
                chip = "bboost"
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
            "chip": chip,
        })
    played = [wk["chip"] for wk in weeks if wk["chip"]]
    return {"weeks": weeks,
            "objective": round(-res.fun, 2),
            "mean_objective": round(mean_obj, 2),
            "total_xp": round(sum(wk["xp"] for wk in weeks), 2),
            "total_hits": sum(wk["hits"] for wk in weeks),
            "transfers": sum(len(wk["in"]) for wk in weeks),
            "solve": solve_info,
            **({"chips_played": played} if played else {}),
            **({"risk_lambda": risk_lambda} if use_risk else {})}


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
    # a solve that hit its time limit is not provably optimal, so the gap
    # between the two arms could be search luck rather than plan quality -
    # refuse the comparison and fall back to the free-transfer plan
    if (with_hits["solve"]["status"] != 0 or no_hits["solve"]["status"] != 0):
        return no_hits, {"took_hits": False, "gain_over_no_hit": None,
                         "threshold": hit_threshold, "truncated": True,
                         "advice": "a solve hit its time limit, so the hit/no-hit "
                                   "comparison is not trustworthy - free transfers only"}
    # compare on the mean component: a -4 is worth taking for points, never
    # merely because it damps the CVaR tail (that is what squad choice is for)
    gain = with_hits["mean_objective"] - no_hits["mean_objective"]
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
    """How much a wildcard this gameweek would be worth versus the normal plan.

    Deprecated shim kept for callers; chip_branches is the real evaluator.
    The whitelist is explicit because **kw used to carry persona kwargs that
    silently vanished here - a Minoux_41 "wildcard" that forgot its
    differentials constraint is worse than no suggestion at all.
    """
    from .optimize import solve
    kw = {k: v for k, v in kw.items() if k in SOLVE_KW}
    wc = solve(pool, gws, allow_infeasible=True, **kw)
    if wc is None:
        return None
    rep = squad_report(df, wc["squad"], gws)
    return {"squad": wc["squad"], "xp_total": rep["xp_total"],
            "gain": round(rep["xp_total"] - base_objective, 2)}


# kwargs the branch evaluators pass through to plan()/solve() - persona
# settings survive a chip branch instead of being dropped by a **kw sieve
BRANCH_KW = ("budget", "locked", "banned", "own_bonus", "min_differentials",
             "max_captain_ownership", "xp_prefix", "max_per_club",
             "bench_weight", "decay", "rank_alpha", "template_tilt",
             "cap_tilt", "elite_weight", "price_matrix", "sell_price",
             "price_gamma", "time_limit")

# BRANCH_KW is shaped for plan(). optimize.solve() is a different, smaller
# signature - handing it plan()-only knobs (rank_alpha, template_tilt,
# elite_weight, price_*) raises TypeError. That crashed every free-hit branch
# for any team with engine 1 enabled; it stayed hidden only because no team
# had delegated the free hit, so the path never ran. The hard constraints
# (locked/banned/min_differentials/budget) survive the narrower sieve; the
# soft rank tilt has no equivalent in solve() and is simply not applied to a
# single-week free-hit squad.
SOLVE_KW = ("budget", "weights", "locked", "banned", "max_changes", "current",
            "bench_weight", "max_per_club", "time_limit", "xp_prefix",
            "own_bonus", "min_differentials", "differ_from", "min_differences")


def wildcard_plan(pool, gws, current, bank=0.0, **kw):
    """A wildcard at `gws[0]`: unlimited free transfers that week, ft resets to 1.

    A wildcard is exactly the unlimited-transfer window the ILP already models
    for gameweek 1 - 15 free moves, no hits, continuity anchored to the current
    squad, then back to one free transfer a week. So no new solver structure is
    needed: the same program with an inflated first-week allowance IS the
    wildcard branch. `pool`/`gws` must start at the chip week.
    """
    kw = {k: v for k, v in kw.items() if k in BRANCH_KW}
    return plan(pool, gws, current, free_transfers=15, bank=bank,
                allow_hits=False, **kw)


def freehit_plan(pool, gws, current, bank=0.0, **kw):
    """A free hit for `gws[0]` only: one week's squad rebuilt for free.

    Solved as a single-gameweek squad selection (optimize.solve) with the
    current squad's full sell value plus bank as budget - a free hit pays no
    sell haircut and the squad reverts, so the following weeks keep the base
    plan untouched. The caller composes the branch value from this week's
    result plus the base plan's remaining weeks.
    """
    from .optimize import solve
    if len(gws) != 1:
        raise ValueError("freehit_plan takes exactly one gameweek")
    cur_idx = [i for i in range(len(pool)) if int(pool.id.values[i]) in set(current)]
    budget = float(pool.price.values[cur_idx].sum()) + float(bank)
    kw = {k: v for k, v in kw.items() if k in SOLVE_KW}
    res = solve(pool, gws, allow_infeasible=True, budget=budget, **kw)
    return res


def chip_branches(pool, gws, current, base, candidates, bank=0.0, **kw):
    """Value of each chip play against the base plan.

    candidates: [{"chip": "wildcard"|"free_hit", "gw": <gameweek number>}],
    typically the top weeks chips.calendar flags. Each branch is scored on
    plain xp (mean points, not the risk-adjusted objective) so the gain reads
    in the same units as the chip calendar's own estimates. Returns one dict
    per candidate with "gain" = branch xp over the remaining horizon minus the
    base plan's xp over the same weeks.
    """
    out = []
    for cand in candidates:
        chip, gw = cand["chip"], cand["gw"]
        if gw not in gws:
            continue
        at = gws.index(gw)
        base_rest = sum(wk["xp"] for wk in base["weeks"][at:])
        entry = {"chip": chip, "gw": gw, "gain": None}
        # The squad a chip is played FROM is the one the base plan holds going
        # into that week, not the one you own today - they differ as soon as the
        # plan makes a transfer before `gw`. Using today's squad silently priced
        # every future-week branch against the wrong starting point.
        from_squad = current if at == 0 else base["weeks"][at - 1]["squad"]
        from_bank = bank if at == 0 else base["weeks"][at - 1].get("bank", bank)
        if chip == "wildcard":
            wc = wildcard_plan(pool, gws[at:], from_squad, bank=from_bank, **kw)
            if wc is not None:
                entry.update(squad=wc["weeks"][0]["squad"],
                             xp=wc["total_xp"],
                             gain=round(wc["total_xp"] - base_rest, 2))
        elif chip == "free_hit":
            fh = freehit_plan(pool, [gw], from_squad, bank=from_bank, **kw)
            if fh is not None:
                xi, _ = best_xi(pool, fh["squad"], gw)
                pos = pool.set_index("id").pos.to_dict()
                xm = pool.set_index("id")[f"xp{gw}"].to_dict()
                pts = sum(xm[int(r.id)] for r in xi)
                att = [r for r in xi if pos[int(r.id)] in ("MID", "FWD")] or xi
                pts += xm[int(max(att, key=lambda r: xm[int(r.id)]).id)]
                after = sum(wk["xp"] for wk in base["weeks"][at + 1:])
                entry.update(squad=fh["squad"], xp=round(pts + after, 2),
                             gain=round(pts + after - base_rest, 2))
        out.append(entry)
    return out
