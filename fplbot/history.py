"""
Season history and model self-grading.

Two jobs:

  1. Track how each team is actually doing - points, rank, and the field average -
     gameweek by gameweek, straight from the manager's own history endpoint.

  2. Grade the model. Every time a plan runs, the projections for the upcoming
     gameweek are snapshotted. Once that gameweek finishes, the snapshot is
     compared against what really happened, so the dashboard can show whether the
     numbers are worth trusting and where they are biased.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import api

POS_OF = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


# ------------------------------------------------------------- projections --
def snapshot_dir(root: Path) -> Path:
    d = Path(root) / "state" / "projections"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_projections(root: Path, gw: int, df) -> None:
    """Store this run's per-player projection for `gw`.

    Overwritten on every run until the gameweek starts, so what gets graded is
    the last projection made before the deadline - the one the advice was
    actually based on.
    """
    payload = {
        str(int(r.id)): round(float(r[f"xp{gw}"]), 3)
        for _, r in df.iterrows() if f"xp{gw}" in df.columns
    }
    (snapshot_dir(root) / f"gw{gw}.json").write_text(json.dumps(payload), encoding="utf-8")


def load_projections(root: Path, gw: int):
    f = snapshot_dir(root) / f"gw{gw}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


# ------------------------------------------------------------------ grading --
def grade_gameweek(boot, gw: int, projected: dict):
    """Compare a stored projection against the finished gameweek."""
    live = api.event_live(gw)
    meta = {e["id"]: e for e in boot["elements"]}
    rows = []
    for el in live.get("elements", []):
        eid = el["id"]
        stats = el.get("stats", {}) or {}
        proj = projected.get(str(eid))
        if proj is None:
            continue
        m = meta.get(eid)
        if not m:
            continue
        actual = stats.get("total_points", 0)
        minutes = stats.get("minutes", 0)
        rows.append({
            "id": eid, "name": m["web_name"],
            "pos": POS_OF.get(m["element_type"], "MID"),
            "proj": proj, "actual": actual, "minutes": minutes,
            "price": m["now_cost"] / 10.0,
        })
    if not rows:
        return None

    # Only judge the model on players it expected to feature. Grading it on the
    # 400 players it correctly projected near zero would flatter it enormously.
    played = [r for r in rows if r["minutes"] > 0 or r["proj"] >= 1.5]
    n = len(played) or 1
    err = [r["actual"] - r["proj"] for r in played]
    mae = sum(abs(e) for e in err) / n
    bias = sum(err) / n

    by_pos = {}
    for p in ("GKP", "DEF", "MID", "FWD"):
        sub = [r for r in played if r["pos"] == p]
        if not sub:
            continue
        by_pos[p] = {
            "n": len(sub),
            "mae": round(sum(abs(r["actual"] - r["proj"]) for r in sub) / len(sub), 2),
            "bias": round(sum(r["actual"] - r["proj"] for r in sub) / len(sub), 2),
            "proj": round(sum(r["proj"] for r in sub) / len(sub), 2),
            "actual": round(sum(r["actual"] for r in sub) / len(sub), 2),
        }

    ranked = sorted(played, key=lambda r: r["actual"] - r["proj"])
    return {
        "gw": gw, "n": len(played),
        "mae": round(mae, 2), "bias": round(bias, 2),
        "by_pos": by_pos,
        "worst_misses": [
            {k: r[k] for k in ("name", "pos", "proj", "actual")} for r in ranked[:6]
        ],
        "best_calls": [
            {k: r[k] for k in ("name", "pos", "proj", "actual")} for r in ranked[-6:][::-1]
        ],
    }


def grade_all(root: Path, boot, fx=None):
    """Grade every settled gameweek that has a stored projection.

    Settled, not finished - see api.settled_events. Grading a week the moment its
    bonus lands is the entire point of the accuracy panel.
    """
    out = []
    for gw in api.settled_events(boot, fx):
        proj = load_projections(root, gw)
        if not proj:
            continue
        try:
            g = grade_gameweek(boot, gw, proj)
        except Exception as e:                          # noqa: BLE001
            print(f"[history] could not grade GW{gw}: {e}")
            continue
        if g:
            out.append(g)
    return out


# ------------------------------------------------------------- team history --
def team_series(entry_id: int, boot):
    """Per-gameweek record for one team, with the field average alongside."""
    averages = {e["id"]: e.get("average_entry_score") for e in boot["events"]}
    highest = {e["id"]: e.get("highest_score") for e in boot["events"]}
    try:
        hist = api.entry_history(entry_id)
    except Exception as e:                              # noqa: BLE001
        print(f"[history] entry {entry_id} history unavailable: {e}")
        return {"weeks": [], "chips": []}

    weeks, prev_rank = [], None
    for h in hist.get("current", []):
        gw = h["event"]
        rank = h.get("overall_rank")
        weeks.append({
            "gw": gw,
            "points": h.get("points", 0),
            "net": h.get("points", 0) - h.get("event_transfers_cost", 0),
            "average": averages.get(gw),
            "highest": highest.get(gw),
            "total": h.get("total_points", 0),
            "overall_rank": rank,
            "rank_delta": (prev_rank - rank) if (prev_rank and rank) else None,
            "gw_rank": h.get("rank"),
            "transfers": h.get("event_transfers", 0),
            "hits": h.get("event_transfers_cost", 0) // 4,
            "bench": h.get("points_on_bench", 0),
            "value": h.get("value", 0) / 10.0,
            "bank": h.get("bank", 0) / 10.0,
        })
        prev_rank = rank or prev_rank
    return {
        "weeks": weeks,
        "chips": [{"name": c["name"], "gw": c["event"]} for c in hist.get("chips", [])],
    }


def build(root: Path, boot, entries: dict, df=None, gw=None, fx=None):
    """Everything the dashboard needs about the past."""
    if df is not None and gw is not None:
        save_projections(root, gw, df)
    settled, provisional = api.settled_events(boot, fx, with_provisional=True)
    return {
        "teams": {name: team_series(eid, boot) for name, eid in entries.items() if eid},
        "accuracy": grade_all(root, boot, fx),
        "settled": settled,
        "provisional": provisional,
    }
