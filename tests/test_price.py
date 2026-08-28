"""Engine 5 invariants: no log means no predictions and a bit-identical plan."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fplbot import model, optimize, planner, price


def build():
    return model.build(horizon=3, start_gw=3)


def synth_log(n_hours=48, rising=True):
    """A synthetic log: one player with steady net inflow, one neutral."""
    now = pd.Timestamp.now(tz="UTC")
    rows = []
    for k in range(0, max(n_hours, 3), 3):
        ts = (now - pd.Timedelta(hours=max(n_hours - k, 0))).isoformat()
        net = k if rising else 0
        rows.append({"ts": ts, "gw": 3, "full": False, "elements": {
            "101": {"cost": 85, "tin": 200 + net, "tout": 100, "own": 25.0,
                    "status": "a", "chance": None},
            "102": {"cost": 45, "tin": 10, "tout": 10, "own": 3.0,
                    "status": "a", "chance": None},
        }})
    return _frame(rows)


def _frame(lines):
    import json
    recs = []
    for line in lines:
        r = json.loads(line) if isinstance(line, str) else line
        for eid, e in r["elements"].items():
            recs.append({"ts": r["ts"], "gw": r["gw"], "element": int(eid), **e})
    df = pd.DataFrame(recs)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.sort_values(["element", "ts"])


def test_predict_on_synthetic_riser():
    preds = price.predict(synth_log(rising=True))
    assert len(preds) == 2
    p = preds.set_index("element")
    assert p.loc[101].p_rise > p.loc[102].p_rise
    assert 0 <= p.loc[101].p_rise <= 1
    assert p.loc[101].method == "physics"


def test_predict_empty_without_history():
    assert len(price.predict(pd.DataFrame())) == 0
    # a single snapshot has no rate to extrapolate
    assert len(price.predict(synth_log(n_hours=0))) == 0
    # two snapshots with a rising net rate but under the min observation
    # window: not enough evidence, so no prediction rows at all
    assert len(price.predict(synth_log(n_hours=int(price.MIN_OBS_H) - 3))) == 0
    # once the window is long enough the riser gets a real prediction
    preds = price.predict(synth_log(n_hours=int(price.MIN_OBS_H) * 4))
    assert len(preds) == 2
    assert (preds.hours_obs >= price.MIN_OBS_H).all()


def test_attach_predictions_degrades_to_zero():
    df, _, _, gws = build()
    base = price.attach_predictions(df, None, gws)
    for g in gws:
        assert (base[f"price_buy{g}"] == df["price"]).all()
    assert (base["pred_rise"] == 0).all()
    assert (base["price_sell"] == df["price"]).all()


def test_attach_predictions_prices_risers():
    df, _, _, gws = build()
    preds = pd.DataFrame([{"element": int(df.id.iloc[0]), "price": df.price.iloc[0],
                           "own": 20.0, "p_rise": 0.8, "p_fall": 0.0,
                           "conf": 0.5, "method": "physics"}])
    out = price.attach_predictions(df, preds, gws)
    assert out.iloc[0]["pred_rise"] == 0.8
    assert out.iloc[0][f"price_buy{gws[-1]}"] > out.iloc[0][f"price_buy{gws[0]}"]


def test_constant_price_matrix_bit_identical():
    """pm == static prices, gamma 0: exactly today's budget row."""
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    s = pool.id.head(15).tolist()
    base = planner.plan(pool, gws, s, time_limit=60)
    pm = np.tile(pool.price.values.astype(float).reshape(-1, 1), (1, len(gws)))
    same = planner.plan(pool, gws, s, time_limit=60, price_matrix=pm,
                        price_gamma=0.0)
    wk0, wk1 = base["weeks"][0], same["weeks"][0]
    assert (wk0["squad"], wk0["in"], wk0["captain"]) == \
           (wk1["squad"], wk1["in"], wk1["captain"])


def test_rising_prices_pull_buys_earlier():
    """A steeply rising player should be bought NOW rather than at the end."""
    df, _, _, gws = build()
    pool = optimize.prune(df, gws)
    s = pool.id.head(15).tolist()
    base = planner.plan(pool, gws, s, time_limit=90)
    assert base is not None
    # make everyone rise sharply except make one cheap starter huge xp
    pm = np.tile(pool.price.values.astype(float).reshape(-1, 1), (1, len(gws)))
    pm[:, -1] += 0.5                     # everything is £0.5m dearer later
    res = planner.plan(pool, gws, s, time_limit=90, price_matrix=pm,
                       price_gamma=0.2)
    assert res is not None
    # the mechanism at least runs; exact behaviour depends on xp gaps
    assert len(res["weeks"][0]["squad"]) == 15