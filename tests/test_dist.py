"""Invariant tests for the distribution layer (fplbot/dist.py)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fplbot import dist, model


def build():
    return model.build(horizon=5, start_gw=3)


def test_sample_mean_equals_xp():
    df, _, _, gws = build()
    s = dist.sample_points(df, gws, n_sims=64, seed=3)
    err = np.abs(s.mean(axis=0) - df[[f"xp{g}" for g in gws]].values).max()
    assert err < 0.02, f"sampler mean drifted from xp by {err}"


def test_samples_nonnegative_and_finite():
    df, _, _, gws = build()
    s = dist.sample_points(df, gws, n_sims=64, seed=3)
    assert np.isfinite(s).all()
    assert (s >= 0).all()


def test_quantile_ordering():
    df, _, _, gws = build()
    q85 = df[[f"q85{g}" for g in gws]].values
    q95 = df[[f"q95{g}" for g in gws]].values
    assert (q85 <= q95 + 1e-9).all()


def test_cxp_is_q85_alias():
    df, _, _, _ = build()
    assert (df.cxp3 == df.q853).all()


def test_seed_reproducibility():
    df, _, _, gws = build()
    a = dist.sample_points(df, gws, n_sims=32, seed=7)
    b = dist.sample_points(df, gws, n_sims=32, seed=7)
    assert np.array_equal(a, b)


def test_low_ownership_players_are_genuinely_low_variance():
    """A 5th-choice defender must not get a fantasy ceiling."""
    df, _, _, gws = build()
    cheap = df[df.price <= 4.5].nsmallest(40, "start_share")
    assert (cheap[f"q95{gws[0]}"] < 3.0).all()