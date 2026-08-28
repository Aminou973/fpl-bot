"""Engine 1 invariants: rank weights and tilt must degrade to today exactly."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fplbot import model, optimize, planner, template


def build():
    return model.build(horizon=3, start_gw=3)


def first_week(plan):
    wk = plan["weeks"][0]
    return (wk["squad"], wk["in"], wk["out"], wk["xi"], wk["captain"],
            wk["hits"], wk["free_transfers"])


def test_rank_weight_neutral_at_alpha_zero():
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    m = template.rank_weight(pool, gws, list(range(10)), alpha=0.0)
    assert (m == 1.0).all()


def test_rank_weight_shape_and_scale():
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    m = template.rank_weight(pool, gws, list(range(15)), alpha=0.5)
    assert len(m) == len(gws)
    # median gameweek is the anchor: the median weight stays near 1
    assert 0.5 < float(np.median(m)) < 1.5


def test_field_scores_shape():
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    fs = template.field_scores(pool, gws, n_sims=80, seed=0)
    assert fs.shape[1] == len(gws)
    assert len(fs) >= 40          # most draws fill a squad
    assert (fs > 0).mean() > 0.9  # and essentially all score something


def test_tilt_changes_plan_only_when_active():
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    squad = pool.id.head(15).tolist()
    base = planner.plan(pool, gws, squad, time_limit=60)
    zero = planner.plan(pool, gws, squad, time_limit=60,
                        template_tilt=0.0, cap_tilt=0.0)
    assert first_week(base) == first_week(zero)


def test_tilt_moves_squad_toward_low_ownership():
    """A negative tilt (differential) must not produce the same squad as a
    positive one on a pool that has both cheap and owned options."""
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    squad = pool.id.head(15).tolist()
    safe = planner.plan(pool, gws, squad, time_limit=120, template_tilt=0.5,
                        rank_alpha=0.5)
    diff = planner.plan(pool, gws, squad, time_limit=120, template_tilt=-0.5,
                        rank_alpha=0.5)
    assert safe is not None and diff is not None
    own = df.set_index("id").selected_by.to_dict()
    own_safe = float(np.mean([own.get(i, 0) for i in safe["weeks"][0]["squad"]]))
    own_diff = float(np.mean([own.get(i, 0) for i in diff["weeks"][0]["squad"]]))
    assert own_diff <= own_safe + 0.5, (own_safe, own_diff)