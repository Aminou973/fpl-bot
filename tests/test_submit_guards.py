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


def test_submit_head_says_what_happened():
    """GW5 2026-09-17: both refresh tokens were dead, every team was skipped,
    and the alert still opened with "lineup applied" - a message that reads
    as success with two warnings under it. The headline must reflect the
    outcome, not the flag that was passed.
    """
    st = submit_transfers.submit_head
    assert st(False, {"A": {"status": "dry-run"}}) == "dry run"
    assert st(True, {"A": {"status": "applied"},
                     "B": {"status": "applied"}}) == "lineup applied"
    assert st(True, {"A": {"status": "applied"},
                     "B": {"status": "already-applied"}}) == "lineup applied"
    assert st(True, {"A": {"status": "skipped"},
                     "B": {"status": "refused"}}) == "nothing applied"
    assert st(True, {"A": {"status": "applied"},
                     "B": {"status": "skipped"}}) == \
        "lineup partially applied (1/2)"
    # a lineup-failed team's transfers DID land on FPL: "nothing applied"
    # would tell the owner to stand down exactly when they must act (GW4)
    assert st(True, {"A": {"status": "lineup-failed"}}) == \
        "transfers landed but the lineup write FAILED"
    assert st(True, {"A": {"status": "applied"},
                     "B": {"status": "lineup-failed"}}) == \
        "lineup partially applied (1/2)"
    assert st(True, {"A": {"status": "transfers-failed"}}) == "submission failed"
    assert st(True, {"A": {"status": "chip-failed"}}) == "submission failed"
    # an all already-applied run wrote nothing this run - say so
    assert st(True, {"A": {"status": "already-applied"},
                     "B": {"status": "already-applied"}}) == \
        "lineup already in place"


def _payload(elements, captain, vice):
    return [{"element": e, "position": i + 1, "is_captain": e == captain,
             "is_vice": e == vice}
            for i, e in enumerate(sorted(elements))]


def test_payload_issues_refuse_the_gw4_ghost_before_transfers():
    """GW4 2026-09-11: the plan's payload named Lacroix (200), a player the
    squad never held, and omitted Porro (499), the player the transfer leg
    brought in. The transfers landed, then the my-team write was refused -
    the squad was left half-transformed and the run crashed without an
    auto_submit record. The submitter must catch the mismatch while it is
    still cheap to refuse: before any transfer is sent.
    """
    owned = (set(range(1, 16)) | {84}) - {15}       # the live squad, 15 players
    legs = [{"element_in": 499, "element_out": 84}]
    post = (owned - {84}) | {499}                   # what the legs produce
    ghost = (post - {499}) | {200}                  # what the plan carried
    issues = submit_transfers.payload_issues(_payload(ghost, 1, 2), post)
    assert any("will not hold" in i for i in issues)
    assert any("leaves squad players out" in i for i in issues)
    # the payload the plan should have carried passes clean
    assert submit_transfers.payload_issues(_payload(post, 1, 2), post) == []


def test_payload_issues_structural_garbage():
    """A payload that is not a legal 15-slot lineup is refused on its own
    shape, before squad membership is even considered."""
    dup = [{"element": 7, "position": 1, "is_captain": True}] * 15
    issues = submit_transfers.payload_issues(dup, set(range(1, 16)))
    assert any("duplicate" in i for i in issues)
    assert any("captains" in i for i in issues)
    assert any("leaves squad players out" in i for i in issues)


def test_payload_issues_formation_legality():
    """Slots 1-11 must be a legal XI and slot 12 the substitute keeper - a
    formation-broken payload would otherwise be rejected by FPL only AFTER
    the transfers had landed. Needs an element->position map with every
    element known to run; bootstrap's int codes are translated."""
    positions = {1: "GKP", 2: "GKP"}
    positions.update({i: "DEF" for i in range(3, 13)})
    positions.update({i: "MID" for i in range(13, 16)})
    # two starting keepers: legal squad, illegal XI
    payload = [{"element": e, "position": i + 1, "is_captain": e == 3,
                "is_vice": e == 4} for i, e in enumerate(sorted(positions))]
    issues = submit_transfers.payload_issues(payload, set(positions),
                                             positions=positions)
    assert any("GKP" in i and "1-1" in i for i in issues)
    assert any("bench slot" in i for i in issues)
    # slots 1-11 legal, slot 12 the keeper: passes clean
    ok = {1: "GKP", 12: "GKP"}
    ok.update({i: "DEF" for i in (2, 3, 4, 5, 13)})
    ok.update({i: "MID" for i in (6, 7, 8, 9, 14)})
    ok.update({i: "FWD" for i in (10, 11, 15)})
    good = [{"element": e, "position": i + 1, "is_captain": e == 6,
             "is_vice": e == 2} for i, e in enumerate(sorted(ok))]
    assert submit_transfers.payload_issues(good, set(ok), positions=ok) == []
    # a partial position map must skip the formation check, not refuse
    issues = submit_transfers.payload_issues(good, set(ok),
                                             positions={1: "GKP"})
    assert issues == []


def test_submission_plan_refuses_gw4_ghost_before_any_transfer():
    """The main() ordering invariant, pinned at the helper's contract: the
    legs come back NON-EMPTY together with the refusal issues, and a caller
    that only acts when issues is empty therefore refuses while nothing has
    been sent. Reordering main() so transfers happen before this check is
    what cost GW4 its squad - this pins the helper both sides rely on."""
    owned = (set(range(1, 16)) | {84}) - {15}
    entry = {"in": [499], "out": [84],
             "picks_payload": _payload((owned - {84} | {499}) - {499} | {200},
                                       1, 2)}
    mt = {"picks": [{"element": e} for e in sorted(owned)]}
    legs, post, issues = submit_transfers.submission_plan(
        entry, mt, {499: 65}, {499: 2, 84: 2, 200: 2}, {})
    assert legs and issues                       # valid legs, but refused
    assert any("will not hold" in i for i in issues)
    # and a clean plan produces legs and a consistent squad with no issues
    entry_ok = {**entry, "picks_payload": _payload(post, 1, 2)}
    legs, post2, issues2 = submit_transfers.submission_plan(
        entry_ok, mt, {499: 65}, {499: 2, 84: 2, 200: 2}, {})
    assert legs and not issues2 and post2 == post


def test_refresh_retries_transient_failures(monkeypatch):
    """2026-09-17: the same stored token was refused at 12:06 and 12:08 and
    accepted at 12:09 with nothing re-armed in between - the endpoint
    intermittently 400s a valid token. A retry costs nothing on a genuinely
    dead token (a failed refresh rotates nothing) and saves the deadline on
    a transient one."""
    calls = []

    def flaky(rt):
        calls.append(rt)
        if len(calls) < 3:
            raise RuntimeError("refresh failed: HTTP 400 invalid_grant")
        return {"access_token": "a", "refresh_token": "r"}

    monkeypatch.setattr(submit_transfers.api, "refresh_tokens", flaky)
    tok = submit_transfers.refresh_with_retry("t", wait=0)
    assert tok["access_token"] == "a" and len(calls) == 3
    monkeypatch.setattr(submit_transfers.api, "refresh_tokens",
                        lambda rt: (_ for _ in ()).throw(
                            RuntimeError("no")))
    try:
        submit_transfers.refresh_with_retry("t", attempts=2, wait=0)
        raise AssertionError("persistent failure must raise")
    except RuntimeError as e:
        assert "no" in str(e)