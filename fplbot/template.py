"""The field, modelled (engine 1).

Rank is a relative game: a point is worth more when the field is bunched
around your score and worth less when you are already clear of the pack.
This module turns ownership data into the per-gameweek weight the ILP
consumes, plus the signed template tilt that buys the field's players (or
fades them).

Everything here is computed from deadline-visible data only: ownership at the
previous deadline and the model's own projections. No end-of-week hindsight.
"""
from __future__ import annotations

import numpy as np

POS_MIN = {"GKP": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}
SQUAD_N = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}


def _sample_squads(df, n_sims, seed, budget=None,
                   need=None, per_club_max=3):
    """Index-sets of `n_sims` squads drawn with inclusion weight = ownership.

    Slot-based rather than rejection-sampled: an xp-pruned pool is expensive,
    so naive draws run out of budget before filling 15. Each slot picks from
    its position weighted by ownership, but only among players who keep the
    remaining slots affordable — so every draw completes. budget=None adapts
    to the pool (mean price x 15, trimmed slightly): the field owns a
    mid-price squad, not the most expensive one.
    """
    if budget is None:
        budget = float(df["price"].mean() * 15 * 0.97)
    rng = np.random.default_rng(seed)
    own = df["selected_by"].values + 0.05
    pos_col = df["pos"].values
    club_col = df["team"].values
    price = df["price"].values
    need = need or SQUAD_N
    slots = [p for p, k in need.items() for _ in range(k)]
    min_by_pos = {p: float(price[pos_col == p].min()) for p in need}
    squads = []
    for _ in range(n_sims):
        order = slots.copy()
        rng.shuffle(order)
        # cheapest possible completion from slot k onward, for affordability
        suffix_min = []
        running = 0.0
        for p in reversed(order):
            running += min_by_pos[p]
            suffix_min.append(running)
        suffix_min.reverse()
        squad, per_club, cost, ok = [], {}, 0.0, True
        taken = set()
        for k, p in enumerate(order):
            rest_min = suffix_min[k + 1] if k + 1 < len(order) else 0.0
            cap = budget - cost - rest_min
            cand = [i for i in range(len(df))
                    if pos_col[i] == p and i not in taken
                    and price[i] <= max(cap, min_by_pos[p])
                    and per_club.get(club_col[i], 0) < per_club_max]
            if not cand:
                ok = False
                break
            w = np.array([own[i] for i in cand])
            i = int(rng.choice(cand, p=w / w.sum()))
            squad.append(i)
            taken.add(i)
            cost += float(price[i])
            per_club[club_col[i]] = per_club.get(club_col[i], 0) + 1
        if ok and len(squad) == 15:
            squads.append(squad)
    return squads


def _xi_and_cap(xp_col, pos_arr):
    """Best-XI points plus captain points for one squad in one gameweek.

    xp_col: (15,) expected points in this gameweek; pos_arr: (15,) position
    strings. Mirrors optimize.best_xi's formation rules and the field's
    captain-the-best-attacker habit, in plain numpy.
    """
    order = np.argsort(-xp_col)
    picked, need = [], dict(POS_MIN)
    gk_done = False
    for i in order:
        p = pos_arr[i]
        if p == "GKP":
            if gk_done:
                continue
            gk_done = True
            picked.append(i)
        else:
            lo, _ = need[p]
            if lo > 0:
                need[p] = (lo - 1, 0)
                picked.append(i)
            elif len(picked) < 11:
                picked.append(i)
        if len(picked) == 11 and gk_done and all(v[0] == 0 for v in need.values()):
            break
    pts = float(xp_col[picked].sum())
    att = [i for i in picked if pos_arr[i] in ("MID", "FWD")]
    pool = att or picked
    pts += float(xp_col[max(pool, key=lambda i: xp_col[i])])
    return pts


def field_scores(pool, gws, n_sims=1500, seed=0, budget=None):
    """Per-gameweek expected scores of simulated field squads: (n_sims, G).

    Scored with the model's own xp — this is the *projected* field, used for
    rank weights before the week plays out. The replay harness separately
    scores real field squads with actual points for percentiles.
    """
    squads = _sample_squads(pool, n_sims, seed, budget)
    n, G = len(pool), len(gws)
    xp_mat = np.array([[pool[f"xp{g}"].values[i] for g in gws] for i in range(n)])
    pos_arr = pool["pos"].values
    out = np.zeros((len(squads), G))
    for k, squad in enumerate(squads):
        idx = np.array(squad)
        for j in range(G):
            out[k, j] = _xi_and_cap(xp_mat[idx, j], pos_arr[idx])
    return out


def _my_scores(pool, gws, current):
    """Projected best-XI score of `current` (pool indices) per gameweek."""
    n, G = len(pool), len(gws)
    xp_mat = np.array([[pool[f"xp{g}"].values[i] for g in gws] for i in range(n)])
    pos_arr = pool["pos"].values
    idx = np.array(current)
    return np.array([_xi_and_cap(xp_mat[idx, j], pos_arr[idx]) for j in range(G)])


def rank_weight(pool, gws, current, alpha=0.5, n_sims=1200, seed=0,
                budget=None, floor=0.25):
    """Per-gameweek multiplier m_g on the objective's time weights.

    m_g = phi(d_g, 0, sd_g) — the density of the projected field's score
    distribution at YOUR squad's projected score. In the pack (small |d|)
    every point moves rank; far clear (or far behind) points move it less.
    Normalised by the horizon median so the median gameweek keeps weight 1
    and hit_threshold keeps its meaning; `alpha` blends with flat weights so
    alpha=0 reproduces the deterministic objective exactly.
    """
    if alpha <= 0:
        return np.ones(len(gws))
    field = field_scores(pool, gws, n_sims=n_sims, seed=seed, budget=budget)
    if len(field) < 30:                       # too few squads to trust a shape
        return np.ones(len(gws))
    mine = _my_scores(pool, gws, current)
    mu, sd = field.mean(axis=0), field.std(axis=0)
    sd = np.maximum(sd, 1e-6)
    dens = np.exp(-0.5 * ((mine - mu) / sd) ** 2) / (sd * np.sqrt(2 * np.pi))
    med = float(np.median(dens))
    m = dens / med if med > 0 else np.ones(len(gws))
    m = np.clip(1.0 + alpha * (m - 1.0), floor, 1.0 / floor)
    return m