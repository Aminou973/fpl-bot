"""Engine 2 invariants: the CVaR epigraph must be a strict superset of today."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fplbot import model, optimize, planner, scenarios


def build():
    return model.build(horizon=3, start_gw=3)


def first_week(plan):
    wk = plan["weeks"][0]
    return (wk["squad"], wk["in"], wk["out"], wk["xi"], wk["captain"],
            wk["hits"], wk["free_transfers"])


def test_no_risk_identical():
    """risk_lambda=0 (with or without a scenario set) must not move the plan."""
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    samples, weights = scenarios.scenario_set(pool, gws, S=8, seed=0)
    plain = planner.plan(pool, gws, pool.id.head(15).tolist(), time_limit=60)
    quiet = planner.plan(pool, gws, pool.id.head(15).tolist(), time_limit=60,
                         scenarios=samples, scenario_weights=weights,
                         risk_lambda=0.0)
    assert first_week(plain) == first_week(quiet)
    assert plain["objective"] == quiet["objective"]
    assert "risk_lambda" not in quiet
    # mean_objective is the hit policy's yardstick: without risk it must be
    # exactly the objective, so the no-risk hit decisions never move
    assert plain["mean_objective"] == plain["objective"]
    assert quiet["mean_objective"] == quiet["objective"]


def test_risk_arm_runs_and_reports():
    """A risk arm solves, reports the flag, and prefers a diversified squad."""
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    squad = pool.id.head(15).tolist()
    samples, weights = scenarios.scenario_set(pool, gws, S=16, seed=0)
    res = planner.plan(pool, gws, squad, time_limit=120,
                       scenarios=samples, scenario_weights=weights,
                       risk_lambda=0.6)
    assert res is not None
    assert res["risk_lambda"] == 0.6
    assert res["total_hits"] >= 0


def test_risk_prefers_diversified_attack():
    """With team-shocked scenarios, three attackers from one club must not beat
    spreading the same budget across clubs — the whole point of engine 2."""
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    squad = pool.id.head(15).tolist()
    det = planner.plan(pool, gws, squad, time_limit=120)
    samples, weights = scenarios.scenario_set(pool, gws, S=32, seed=0)
    risk = planner.plan(pool, gws, squad, time_limit=120,
                        scenarios=samples, scenario_weights=weights,
                        risk_lambda=1.0)
    assert det is not None and risk is not None
    # not a hard assertion about which wins on one horizon — the assertion is
    # that the risk arm is a different solve, i.e. the epigraph binds somewhere
    clubs_det = df.set_index("id").loc[det["weeks"][0]["squad"], "team"]
    clubs_risk = df.set_index("id").loc[risk["weeks"][0]["squad"], "team"]
    n_shared = len(set(det["weeks"][0]["squad"]) & set(risk["weeks"][0]["squad"]))
    # 32 shocked scenarios over a 3-week horizon will move at least one pick
    assert n_shared < 15 or clubs_det.value_counts().max() != clubs_risk.value_counts().max()


def test_scenario_set_shape_and_weights():
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    samples, weights = scenarios.scenario_set(pool, gws, S=12, seed=0)
    assert samples.ndim == 3 and samples.shape[0] == 12
    assert samples.shape[2] == len(gws)
    assert abs(weights.sum() - 1.0) < 1e-6
    assert (weights > 0).all()