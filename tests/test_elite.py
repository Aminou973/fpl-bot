"""Engine 1b: the elite-template ownership blend.

The blend must be opt-in twice over: a config that never sets elite_weight
plans bit-identically to before, and a weight without an elite_by column
(often the case offline, where no sample exists) degrades silently to the
field's own ownership rather than erroring.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fplbot import model, optimize, planner  # noqa: E402


def mini_pool():
    df, _, _, gws = model.build(horizon=3, start_gw=3)
    top = df.sort_values("xp_total", ascending=False).head(80).copy()
    return top, gws


def squad_of(pool, gws):
    """A feasible 15: cheap keeper/def block + the best attackers."""
    p = pool.sort_values(["price", "xp_total"])
    gk = list(p[p.pos == "GKP"].id[:2])
    dfn = list(p[p.pos == "DEF"].sort_values("xp_total", ascending=False).id[:5])
    mid = list(p[p.pos == "MID"].sort_values("xp_total", ascending=False).id[:5])
    fwd = list(p[p.pos == "FWD"].sort_values("xp_total", ascending=False).id[:3])
    return list(map(int, gk + dfn + mid + fwd))


def plan(pool, **kw):
    gws = [3, 4, 5]
    squad = squad_of(pool, gws)
    return planner.plan(pool, gws, squad, bank=0.0, **kw)


def test_no_weight_is_bit_identical():
    pool, _ = mini_pool()
    pool["elite_by"] = np.random.default_rng(0).uniform(0, 80, len(pool))
    a, b = plan(pool), plan(pool, elite_weight=0.0)
    pd.testing.assert_frame_equal(pd.DataFrame(a["weeks"]), pd.DataFrame(b["weeks"]))


def test_missing_column_degrades_to_field_ownership():
    pool, _ = mini_pool()
    base = plan(pool.copy())                       # no elite_by column at all
    tilted = plan(pool.copy(), elite_weight=1.0)   # weight but nothing to blend
    pd.testing.assert_frame_equal(pd.DataFrame(base["weeks"]),
                                  pd.DataFrame(tilted["weeks"]))


def test_blend_pulls_toward_elite_template():
    pool, gws = mini_pool()
    # a mediocre player the elite all hold: full elite weight must get him in
    # over an equally-priced field favourite the elite ignore
    pool = pool.assign(elite_by=np.where(pool.price < 9.0, 60.0, 1.0))
    pool = pool.assign(selected_by=np.where(pool.price > 9.0, 60.0, 1.0))
    w = plan(pool.copy(), elite_weight=1.0, template_tilt=1.0)
    cheap = {int(i) for i in pool[pool.price < 9.0].id}
    got = {int(i) for wk in w["weeks"] for i in wk["squad"]}
    # far more of the cheap, elite-held players than the field-tilt run picks
    b = plan(pool.copy(), template_tilt=1.0)
    got_b = {int(i) for wk in b["weeks"] for i in wk["squad"]}
    assert len(got & cheap) > len(got_b & cheap), "elite blend had no effect"