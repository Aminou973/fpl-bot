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

from fplbot import api, pipeline                  # noqa: E402
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


def test_lineup_write_accepts_202():
    """A re-write of an unchanged lineup gets HTTP 202 from FPL.

    GW3 2026-09-03: the chip-rearm run posted the identical lineup again and
    FPL answered 202 (accepted, no change) — which the strict !=200 check
    reported to Telegram as a lineup failure although the write had landed.
    """
    class Resp:
        status_code = 202
        text = '{"picks": []}'

        def json(self):
            return {"picks": []}

    class Session:
        def post(self, *a, **k):
            return Resp()

    picks = [{"element": 1, "position": 1, "is_captain": False,
              "is_vice_captain": False}] * 15
    # 202 must not raise; 400 must
    assert api.submit_picks(Session(), 1, picks) == {"picks": []}
    api.submit_picks(Session(), 1, picks, chip="3xc")     # chip rides fine

    class Bad(Resp):
        status_code = 400
        text = '{"error": "squad_element_invalid"}'

    class BadSession:
        def post(self, *a, **k):
            return Bad()

    try:
        api.submit_picks(BadSession(), 1, picks)
        raise AssertionError("400 must raise")
    except RuntimeError as e:
        assert "400" in str(e)


def test_snapshot_records_free_transfers():
    """limit−made from the my-team read is the FTs left for THIS deadline.

    GW3 2026-09-03: Minoux_41 spent its FT on Rogers mid-week, but the plan
    still said "1 FT · rolls (2 next week)" — entry history's loop adds the
    next week's allocation as soon as the current week's transfers land.
    """
    snap = submit_transfers.snapshot_of(1, "t", 1, 3, {
        "picks": [], "transfers": {"bank": 21, "limit": 1, "made": 1}})
    assert snap["free_transfers"] == 0
    assert pipeline.snapshot_bank(snap) == 2.1
    # a rolled allowance reads back as two
    snap = submit_transfers.snapshot_of(1, "t", 1, 3, {
        "picks": [], "transfers": {"limit": 2, "made": 0}})
    assert snap["free_transfers"] == 2
    # no limit in the read -> no FT claim (planner falls back as before)
    assert submit_transfers.snapshot_of(1, "t", 1, 3, {
        "picks": [], "transfers": {"bank": 5}})["free_transfers"] is None