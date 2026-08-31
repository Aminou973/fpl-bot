"""Engine 4 invariants: tuning applies only under explicit config, only when armed."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fplbot import pipeline


def cfg_team(**kw):
    base = {"role": "main", "hit_threshold": 6}
    base.update(kw)
    return base


def engines():
    return {"rank": {"enabled": True, "alpha": 0.5},
            "scenarios": {"enabled": True, "risk_lambda": 0.6, "n": 32}}


def write_best(params):
    """tuning.results as an absolute path: ROOT / <abs> resolves to <abs>."""
    f = Path(tempfile.mkstemp(suffix=".json")[1])
    f.write_text(json.dumps({"best": {"params": params}}), encoding="utf-8")
    return str(f)


def test_disabled_by_default(monkeypatch):
    monkeypatch.setattr(pipeline, "load_config",
                        lambda: {"tuning": {"auto_apply": False},
                                 "engines": engines()})
    kw, ht, applied = pipeline.apply_tuning({}, cfg_team(), 6)
    assert applied == {} and ht == 6


def test_best_params_applied_under_config(monkeypatch):
    f = write_best({"rank_alpha": 0.75, "template_tilt": 0.25,
                    "hit_threshold": 4, "risk_lambda": 0.3, "n_scenarios": 8})
    monkeypatch.setattr(pipeline, "load_config", lambda: {
        "tuning": {"auto_apply": True, "results": f}, "engines": engines()})
    kw, ht, applied = pipeline.apply_tuning({}, {"role": "main"}, 6)
    assert kw["rank_alpha"] == 0.75
    assert kw["template_tilt"] == 0.25
    assert kw["risk_lambda"] == 0.3 and kw["n_scenarios"] == 8
    assert ht == 4
    assert applied["hit_threshold"] == 4


def test_explicit_team_config_wins(monkeypatch):
    f = write_best({"rank_alpha": 0.75, "template_tilt": 0.25,
                    "hit_threshold": 4})
    monkeypatch.setattr(pipeline, "load_config", lambda: {
        "tuning": {"auto_apply": True, "results": f}, "engines": engines()})
    team = cfg_team(rank={"alpha": 0.9, "tilt": -0.4}, hit_threshold=8)
    kw, ht, applied = pipeline.apply_tuning({}, team, 8)
    assert "rank_alpha" not in kw
    assert "template_tilt" not in kw
    assert ht == 8
    assert applied == {}


def test_engine_gate_blocks_disabled_engine(monkeypatch):
    f = write_best({"rank_alpha": 0.75, "risk_lambda": 0.3, "n_scenarios": 8})
    monkeypatch.setattr(pipeline, "load_config", lambda: {
        "tuning": {"auto_apply": True, "results": f},
        "engines": {"rank": {"enabled": False},
                    "scenarios": {"enabled": False}}})
    kw, ht, applied = pipeline.apply_tuning({}, cfg_team(), 6)
    assert applied == {}          # no engine gate on -> no silent enabling


def test_missing_missing_results_file_is_harmless(monkeypatch):
    monkeypatch.setattr(pipeline, "load_config", lambda: {
        "tuning": {"auto_apply": True, "results": "data/backtest/nope.json"},
        "engines": engines()})
    kw, ht, applied = pipeline.apply_tuning({}, cfg_team(), 6)
    assert applied == {} and ht == 6