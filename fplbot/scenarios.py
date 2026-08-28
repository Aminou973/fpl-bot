"""Scenario sets for the risk-aware planner (engine 2).

Sampling lives in fplbot/dist.py; this module owns the policy of which
scenarios the ILP sees. A planner objective is mean + risk_lambda * CVaR, and
CVaR is computed over a *scenario set*, not over thousands of raw draws —
a representative set of S weighted scenarios keeps the epigraph small
(+S*G continuous variables) while carrying the correlated team shocks.

With risk_lambda = 0 the scenario set changes nothing: the mean over scenarios
equals the deterministic xp exactly (dist.sample_points guarantees it), so the
objective reduces to today's. That reduction is asserted in the test suite —
it is the contract that lets engines be enabled per team without silently
changing the other's plan.
"""
from __future__ import annotations

import numpy as np
from scipy.cluster.vq import kmeans2

from . import dist


def scenario_set(pool, gws, S=32, seed=0, method="kmeans", team_shock=0.18):
    """Return (samples (S, n, G), weights (S,)) for the ILP's CVaR epigraph.

    method="kmeans": draw 8*S raw scenarios, cluster into S representative
    ones with scipy's kmeans2, weight each by its cluster share. The result
    preserves the raw draw distribution with S-fold fewer epigraph rows.
    method="iid": S raw draws at equal weight — the honest default when the
    cluster shapes are suspect.
    """
    n_raw = 8 * S if method == "kmeans" else S
    raw = dist.sample_points(pool, gws, n_sims=n_raw, seed=seed,
                             team_shock=team_shock)
    if method != "kmeans" or n_raw <= S:
        return raw, np.full(len(raw), 1.0 / len(raw))

    flat = raw.reshape(len(raw), -1)
    # kmeans2 with a fixed seed is deterministic; minit='++' needs k too, and
    # missing clusters can occur with degenerate data, so fall back to iid
    try:
        cent, label = kmeans2(flat, S, iter=12, minit="++", seed=seed)
    except ValueError:
        return raw[:S], np.full(S, 1.0 / S)
    counts = np.bincount(label, minlength=S).astype(float)
    keep = counts > 0
    if keep.sum() < 2:                       # degenerate clustering
        return raw[:S], np.full(S, 1.0 / S)
    cent = cent.reshape(int(keep.sum()), *raw.shape[1:])
    w = counts[keep] / counts[keep].sum()
    return cent, w


def to_pool_columns(df, gws, seed=0):
    """Attach the simulated-quantile ceiling columns (q85/q95) to a pool.

    Thin wrapper over dist.attach_quantiles, kept here so the planner-facing
    API is one module. xp itself is never touched.
    """
    from . import dist
    return dist.attach_quantiles(df, gws, seed=seed)