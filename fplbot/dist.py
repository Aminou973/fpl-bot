"""Scenario sampling: turn point projections into distributions.

model.build collapses every player-gameweek to one expected-points number. That
is exactly right for ranking players, but a squad's score is the SUM of players
whose outcomes move together — three attackers from one club do not diversify,
a 60%-to-start enabler is not a 100% starter, and a captain is bought for the
right tail. This module re-inflates the point estimates into scenarios that
respect those correlations, while staying tied to the model: the mean of the
samples equals the deterministic xp exactly, for every player and gameweek.

Inputs are the per-gameweek columns model.build emits (lam_goals, lam_assists,
cmp_cs, cmp_det, p_start, csp) — see model.build's fixture loop.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sample_points(pool, gws, n_sims=256, seed=0, team_shock=0.18):
    """Sample n_sims plausible point outcomes per player per gameweek.

    Returns an array (n_sims, n_players, n_gws). Invariant: for every (i, g),
    mean over axis 0 equals pool[f"xp{g}"] within 0.02 — the sampling adds
    variance around the model's expectation, never a different expectation.

    Structure per scenario s:
    - one lognormal shock per (s, club, gw) on the attack rate and one on the
      defence rate. This is what makes scenarios *correlated within a club*,
      which is the only reason a risk-aware objective changes squad composition.
    - minutes: a three-point draw — start (prob p_start) or not. The cameo
      expectation stays in the deterministic base rather than being re-sampled,
      so the mean is exact by construction.
    - goals / assists ~ Poisson(lam * attack shock); clean-sheet points as a
      Bernoulli draw on the shocked CS probability, paid at the per-event rate.
    - everything else (appearance, conceded, saves, bonus, dc, cards, cameo)
      stays deterministic; its variance is second-order.
    """
    rng = np.random.default_rng(seed)
    n = len(pool)
    G = len(gws)
    team_idx = pd.factorize(pool["team_id"].values)[0]
    n_clubs = int(team_idx.max()) + 1
    sh_att = np.exp(rng.normal(0.0, team_shock, (n_sims, n_clubs, G)))
    sh_def = np.exp(rng.normal(0.0, team_shock, (n_sims, n_clubs, G)))

    X = np.zeros((n_sims, n, G))
    xp_mat = np.empty((n, G))
    for gi, g in enumerate(gws):
        p_start = pool[f"p_start{g}"].values.astype(float)
        lam_g = pool[f"lam_goals{g}"].values.astype(float)
        lam_a = pool[f"lam_assists{g}"].values.astype(float)
        cmp_cs = pool[f"cmp_cs{g}"].values.astype(float)
        cs_prob = np.clip(pool[f"csp{g}"].values.astype(float), 0.0, 0.99)
        xp_g = pool[f"xp{g}"].values.astype(float)
        xp_mat[:, gi] = xp_g
        # points paid per clean-sheet event, so that E[draw] == cmp_cs
        cs_pts = np.where(p_start * cs_prob > 1e-4,
                          cmp_cs / np.maximum(p_start * cs_prob, 1e-4), 0.0)
        cs_pts = np.clip(cs_pts, 0.0, 12.0)
        # everything not explicitly sampled carries the rest of the expectation
        det = xp_g - lam_g - lam_a - cmp_cs
        for s in range(n_sims):
            sa = sh_att[s, team_idx, gi]
            sd = sh_def[s, team_idx, gi]
            start = rng.random(n) < p_start
            goals = rng.poisson(np.maximum(lam_g * sa, 0.0))
            assists = rng.poisson(np.maximum(lam_a * sa, 0.0))
            X[s, :, gi] = det + goals + assists + \
                np.where(start & (rng.random(n) < cs_prob ** sd), cs_pts, 0.0)

    # exact-mean repair: push the (tiny) residual of each player-gameweek mean
    # back into every scenario so downstream objectives stay on the model's scale
    X += (xp_mat[None, :, :] - X.mean(axis=0)[None, :, :])
    return np.maximum(X, 0.0)


def attach_quantiles(df, gws, n_sims=256, seed=0, team_shock=0.18):
    """Add q85{g} / q95{g} columns sampled from the model's own distribution.

    These replace the old cxp heuristic (xp * (1 + 0.55 * explosive)) with a
    real simulated quantile: the ceiling score is now the 85th percentile of
    what the player could actually score, given his minutes risk, his Poisson
    goal variance and his club's fixture-day shock.
    """
    samples = sample_points(df, gws, n_sims=n_sims, seed=seed,
                            team_shock=team_shock)
    for gi, g in enumerate(gws):
        df[f"q85{g}"] = np.round(np.quantile(samples[:, :, gi], 0.85, axis=0), 3)
        df[f"q95{g}"] = np.round(np.quantile(samples[:, :, gi], 0.95, axis=0), 3)
        # deprecated alias: cxp used to be the deterministic upside tilt; it is
        # the 85th-percentile draw now. xp_prefix="cxp" keeps working.
        df[f"cxp{g}"] = df[f"q85{g}"]
    df["ceiling_total"] = [round(sum(df[f"q85{g}"].iloc[i] for g in gws), 3)
                           for i in range(len(df))]
    return df