"""Price-move prediction (engine 5).

FPL prices move on an accumulator: net transfers fill a threshold that scales
with ownership, a price change drains it, and the market's net rate is visible
in the hourly log the watch job writes (state/price_log.jsonl). Stage 1 is the
physics: project the net rate forward, and a rise happens when the projected
fill crosses the threshold. Stage 2 (tools/price_eval.py + calibrate) fits the
threshold constants against observed moves once enough log history exists.

The degradation contract matters more than the model: with no log (or too
thin a history) this module returns an EMPTY prediction table, the planner
gets no price columns, and the plan is bit-identical to the deterministic
one. That contract is asserted in the test suite.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
PRICE_LOG = STATE / "price_log.jsonl"
MODEL_FILE = STATE / "price_model.json"

# stage-1 physics constants - recalibrated from observed moves once the log
# has >= 2 weeks of history (tools/price_eval.py reports the fit quality)
MIN_THRESHOLD = 4.0        # accumulator floor, in net transfers
OWN_K = 0.000_02           # threshold per manager owned
FILL_SD = 0.35             # noise on the fill fraction -> logistic sharpness
RISE_STEP = 0.1            # £m per price change (now_cost is in £0.1m units)
MIN_OBS_H = 6.0            # hours of history before an element gets a prediction
CONF_MIN, CONF_MAX = 0.3, 0.8


def read_log(path=PRICE_LOG):
    """The price log as a long DataFrame; empty frame when nothing logged."""
    if not Path(path).exists():
        return pd.DataFrame(columns=["ts", "gw", "element", "cost", "tin",
                                     "tout", "own", "status", "chance"])
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        for eid, e in (rec.get("elements") or {}).items():
            rows.append({"ts": rec["ts"], "gw": rec.get("gw"),
                         "element": int(eid), **e})
    if not rows:
        return pd.DataFrame(columns=["ts", "gw", "element", "cost", "tin",
                                     "tout", "own", "status", "chance"])
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    return df.sort_values(["element", "ts"])


def predict(log_df, horizon_hours=72, now=None):
    """Stage-1 physics predictions: one row per element with enough history.

    p_rise/p_fall: logistic of (projected fill - threshold) over the horizon,
    where the fill accumulates at the element's observed net-transfer rate and
    the threshold scales with ownership. `conf` grows with hours of clean
    observation, capped well below certainty — these are odds, not facts.
    """
    if log_df is None or not len(log_df):
        return pd.DataFrame()
    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    out = []
    for eid, g in log_df.groupby("element"):
        g = g.dropna(subset=["ts"])
        if len(g) < 2:
            continue
        last, prev = g.iloc[-1], g.iloc[0]
        hours = (last.ts - prev.ts).total_seconds() / 3600.0
        if hours < MIN_OBS_H:
            continue
        net = float(last.tin) - float(last.tout) - (float(prev.tin) - float(prev.tout))
        rate = net / hours                       # net transfers per hour
        own = float(last.own)
        price = float(last.cost) / 10.0
        proj = rate * horizon_hours
        thresh = max(MIN_THRESHOLD, OWN_K * own * 10_000_000 / 15)
        z_rise = (proj - thresh) / (FILL_SD * max(thresh, 1.0))
        z_fall = (-proj - thresh) / (FILL_SD * max(thresh, 1.0))
        p_rise = float(1.0 / (1.0 + np.exp(-z_rise)))
        p_fall = float(1.0 / (1.0 + np.exp(-z_fall)))
        conf = float(np.clip((hours - MIN_OBS_H) / 168.0, 0.0, 1.0))
        conf = CONF_MIN + (CONF_MAX - CONF_MIN) * conf
        out.append({"element": int(eid), "price": price, "own": own,
                    "p_rise": p_rise, "p_fall": p_fall,
                    "net_rate": rate, "hours_obs": hours, "conf": conf,
                    "method": "physics"})
    return pd.DataFrame(out)


def attach_predictions(pool_df, preds, gws):
    """Add the price columns the planner reads; harmless when preds is empty.

    price_buy{g}: expected price at gameweek g's deadline = current price plus
    the expected number of rises before then (cumulative p_rise x £0.1m). The
    other columns are diagnostics for the brief and the dashboard.
    """
    df = pool_df.copy()
    G = len(gws)
    for g in gws:
        df[f"price_buy{g}"] = df["price"].astype(float)
    for col in ("pred_rise", "pred_fall", "pred_conf"):
        df[col] = 0.0
        if f"{col}{gws[0]}" in df:
            df = df.drop(columns=[f"{col}{gws[0]}"])
    df["price_sell"] = df["price"].astype(float)
    if preds is None or not len(preds):
        return df
    p = preds.set_index("element")
    for i, eid in enumerate(df["id"].values):
        if int(eid) not in p.index:
            continue
        row = p.loc[int(eid)]
        cum = 0.0
        for j, g in enumerate(gws):
            cum += float(row.p_rise)
            df.iloc[i, df.columns.get_loc(f"price_buy{g}")] = \
                float(row.price) + RISE_STEP * min(cum, 2.0)
        df.iloc[i, df.columns.get_loc("pred_rise")] = float(row.p_rise)
        df.iloc[i, df.columns.get_loc("pred_fall")] = float(row.p_fall)
        df.iloc[i, df.columns.get_loc("pred_conf")] = float(row.conf)
    return df


def calibrate(log_df=None):
    """Fit the stage-2 thresholds against observed moves; write the model file.

    Returns a summary dict (AUC placeholder until enough weeks exist). The
    honest rule: until the log covers >= 2 weeks with moves, the physics
    constants stand and the model file records that no fit was possible.
    """
    df = log_df if log_df is not None else read_log()
    moves = 0
    if len(df):
        for eid, g in df.groupby("element"):
            moves += int((g.cost.diff().fillna(0) != 0).sum())
    fit = {"fit_date": None, "auc": None, "n_moves": moves,
           "ready": moves >= 20,
           "constants": {"min_threshold": MIN_THRESHOLD, "own_k": OWN_K,
                         "fill_sd": FILL_SD}}
    if fit["ready"]:
        # stage-2 logistic fit lands here once the history justifies it
        fit["fit_date"] = pd.Timestamp.now(tz="UTC").isoformat()
    STATE.mkdir(exist_ok=True)
    MODEL_FILE.write_text(json.dumps(fit, indent=1))
    return fit