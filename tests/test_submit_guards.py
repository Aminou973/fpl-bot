"""The submit job's stale-plan guard and the live-squad snapshot bridge.

GW3 2026-09-03: the planner planned on last week's published picks (public
picks only publish at a deadline), so the submitter dutifully sold a player
the plan thought it owned, paid a hit for it, and then had the lineup write
rejected because the plan's payload named three players the squad no longer
held. These pin the two layers that stop that: the submitter refuses plans
whose base squad is not the squad the game holds, and the planner prefers
the submitter's authenticated my-team snapshot over published picks.
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jobs"))

from fplbot import pipeline                       # noqa: E402
import submit_transfers                            # noqa: E402


def mt(picks):
    return {"picks": [{"element": e} for e in picks]}


def test_refuses_plan_built_on_pre_transfer_squad():
    plan = {"squad": list(range(1, 16))}
    live = mt(list(range(1, 15)) + [99])
    note = submit_transfers.stale_plan_note(plan, live)
    assert note is not None and "different squad" in note


def test_allows_plan_on_the_live_squad():
    ids = list(range(1, 16))
    assert submit_transfers.stale_plan_note({"squad": ids}, mt(ids)) is None


def test_snapshot_bank_units():
    assert pipeline.snapshot_bank({"bank_raw": 12}) == 1.2
    assert pipeline.snapshot_bank({"bank_raw": 1_200_000}) == 12_000.0
    assert pipeline.snapshot_bank({}) is None


def test_snapshot_freshness():
    now = dt.datetime.now(dt.timezone.utc)
    full = {"picks": list(range(1, 16))}
    assert pipeline.snapshot_fresh({**full, "fetched_at": now.isoformat()})
    stale = {**full, "fetched_at": (now - dt.timedelta(hours=27)).isoformat()}
    assert not pipeline.snapshot_fresh(stale)
    assert not pipeline.snapshot_fresh({**full, "fetched_at": now.isoformat(),
                                        "picks": []})
    assert not pipeline.snapshot_fresh({**full, "fetched_at": "nonsense"})