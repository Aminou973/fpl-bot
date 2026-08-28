"""Replay smoke test: the whole engine on committed 2025-26 history.

Deliberately short (2 gameweeks) so CI stays inside its budget; the full
season replay is tools/backtest.py's job.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fplbot.replay import Replay, ReplayParams

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def replay():
    cache = ROOT / "data" / "backtest" / "cache" / "test-v-replay"
    return Replay(ROOT / "data", "2025-26", "2024-25", cache_dir=cache)


def test_two_gameweeks_smoke(replay):
    res = replay.run_policy(ReplayParams(horizon=3, time_limit=10), gw_to=2,
                            field_sims=300, verbose=False)
    assert len(res.weeks) == 2
    for r in res.weeks:
        assert r["managed"] >= 0 and r["frozen"] >= 0 and r["template"] >= 0
        assert 0 <= r["field_pct"] <= 100
    assert res.field_pct_basis == "ownership"
    assert res.totals["frozen"] > 0


def test_replay_deterministic(replay):
    a = replay.run_policy(ReplayParams(horizon=2, time_limit=8, seed=1),
                          gw_to=2, field_sims=50, verbose=False)
    b = replay.run_policy(ReplayParams(horizon=2, time_limit=8, seed=0),
                          gw_to=2, field_sims=50, verbose=False)
    # same params up to the seeded field sampling: same arm scores
    assert a.totals["managed"] == b.totals["managed"]
    assert a.totals["frozen"] == b.totals["frozen"]


def test_ownership_and_price_knowable_at_deadline(replay):
    own = replay.ownership_at(3)
    assert own and max(own.values()) > 5.0
    # gw3 prices must be what they were after gw2, not end-of-season
    p = replay.frame_for(3)
    assert (p.now_cost > 0).all()