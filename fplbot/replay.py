"""Replay harness: run a season through the engine with only what was knowable.

This is the substrate every engine is validated on. At each deadline the replay
may use only: the previous season in full, this season's results up to the
previous gameweek, each player's price as it was that week, and each player's
ownership as it stood at the previous deadline (`selected` in the gameweek
history). End-of-season availability is hindsight and is deliberately erased.

Three arms run side by side:
- managed   — runs the real policy (planner.plan_with_hit_policy), the same
              solver path the live bot uses, under the ReplayParams knob set.
- frozen    — keeps its gameweek-1 squad all season and only picks its best XI.
- template  — holds the most-owned affordable squad, rebuilt each deadline from
              real ownership. This is what the rank-aware engine (engine 1) is
              measured against.

The projection cache is param-independent: model.build depends only on the data
visible at each deadline and on model constants, so it is built once per
(season, gameweek, MODEL_VERSION) and every parameter set reuses it.
"""
from __future__ import annotations

import json
import pickle
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
import pandas as pd

from . import model, optimize, planner
from .model import MODEL_VERSION

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ReplayParams:
    """One policy to replay. Everything here must be sweepable by tools/tune.py."""
    horizon: int = 5
    hit_threshold: float = 6.0
    decay: float = 0.85
    bench_weight: float = 0.12
    xp_prefix: str = "xp"
    own_bonus: float = 0.0                    # deprecated; engine 1 replaces it
    template_tilt: float = 0.0                # engine 1 (wired in P2)
    cap_tilt: float = 0.0                     # engine 1
    rank_alpha: float = 0.0                   # engine 1
    risk_lambda: float = 0.0                  # engine 2
    n_scenarios: int = 0                      # engine 2
    cvar_beta: float = 0.75                   # engine 2
    price_gamma: float = 0.0                  # engine 5
    news: str = "off"                         # engine 6
    chip_policy: str = "calendar"             # engine 3: "calendar" | "ilp_tc_bb"
    min_differentials: tuple | None = None
    max_captain_ownership: float | None = None
    time_limit: int = 20
    seed: int = 0

    def tag(self):
        """Short cache key for this parameter set."""
        d = asdict(self)
        return "|".join(f"{k}={d[k]}" for k in sorted(d))


@dataclass
class ReplayResult:
    season: str
    weeks: list = field(default_factory=list)
    totals: dict = field(default_factory=dict)
    field_pct_basis: str = "ownership"

    def summary(self):
        t = self.totals
        return (f"managed {t.get('managed', 0)}  frozen {t.get('frozen', 0)}  "
                f"template {t.get('template', 0)}  "
                f"field_pct {t.get('mean_field_pct', 0):.1f}  "
                f"hits {t.get('hits', 0)}  transfers {t.get('transfers', 0)}")

    def to_json(self):
        return {"season": self.season, "field_pct_basis": self.field_pct_basis,
                "weeks": self.weeks, "totals": self.totals}


class Replay:
    """Loads a season's history and replays policies across it."""

    def __init__(self, data_dir=ROOT / "data", season="2025-26", prior="2024-25",
                 cache_dir=None):
        self.data_dir = Path(data_dir)
        self.season = season
        self.prior = prior
        self.cache_dir = Path(cache_dir) if cache_dir else \
            ROOT / "data" / "backtest" / "cache" / f"{season}-v{MODEL_VERSION}"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        d = Path(data_dir)
        self.cur = {
            "players": pd.read_csv(d / season / "players_raw.csv"),
            "teams": pd.read_csv(d / season / "teams.csv"),
            "fixtures": None,          # _ensure_fixtures fills this in
            "gw": pd.read_csv(d / season / "gws" / "merged_gw.csv",
                              encoding="utf-8", on_bad_lines="skip",
                              low_memory=False),
        }
        self.prev = {
            "players": pd.read_csv(d / prior / "players_raw.csv"),
            "teams": pd.read_csv(d / prior / "teams.csv"),
            "gw": pd.read_csv(d / prior / "gws" / "merged_gw.csv",
                              encoding="utf-8", on_bad_lines="skip",
                              low_memory=False),
        }
        self.gw_df = self.cur["gw"]
        self.pts = {(int(r.element), int(r.GW)): int(r.total_points)
                    for r in self.gw_df.itertuples() if pd.notna(r.total_points)}
        self._ensure_fixtures()

    def _ensure_fixtures(self):
        """Synthesize the season's fixtures.csv from the gameweek history.

        vaastav-style downloads always carry fixtures.csv, but a repo that only
        committed the gameweek history does not — and every fixture's home/away
        pairing is recoverable from `opponent_team` + `was_home`.
        """
        fx_path = self.data_dir / self.season / "fixtures.csv"
        if fx_path.exists():
            self.cur["fixtures"] = pd.read_csv(fx_path)
            return
        g = self.gw_df
        p = self.cur["players"]
        team_of = dict(zip(p.id, p.team))
        pairs = {}
        for r in g.itertuples():
            if pd.isna(r.GW) or pd.isna(r.opponent_team) or r.opponent_team == 0:
                continue
            my = int(team_of.get(int(r.element), 0))
            opp = int(r.opponent_team)
            home = bool(r.was_home)
            key = (int(r.GW), my, opp) if home else (int(r.GW), opp, my)
            pairs[key] = True
        rows = [{"event": gw, "team_h": h, "team_a": a,
                 "team_h_difficulty": 3, "team_a_difficulty": 3, "finished": True}
                for (gw, h, a) in sorted(pairs)]
        fx = pd.DataFrame(rows)
        fx.to_csv(fx_path, index=False)
        print(f"[replay] synthesized {len(fx)} fixtures -> {fx_path.name}")
        self.cur["fixtures"] = fx

    # ------------------------------------------------------------ data views --
    def frame_for(self, gw):
        """The player table as it looked before gameweek `gw` kicked off."""
        p = self.cur["players"].copy()
        g = self.gw_df
        upto = g[g.GW <= max(gw - 1, 1)]
        if not len(upto):
            upto = g[g.GW == g.GW.min()]
        pr = upto.sort_values("GW").groupby("element")["value"].last()
        p["now_cost"] = p["id"].map(pr).fillna(p["now_cost"]).astype(int)
        # end-of-season availability is hindsight
        p["status"] = "a"
        p["news"] = ""
        p["chance_of_playing_next_round"] = np.nan
        return p

    def ownership_at(self, gw):
        """Ownership percentage per element as it stood at the previous deadline.

        Falls back to the first gameweek's numbers when there is no earlier
        gameweek, which is close enough to right for the opening deadline.
        """
        g = self.gw_df
        upto = g[g.GW <= max(gw - 1, 1)]
        if not len(upto):
            upto = g[g.GW == g.GW.min()]
        sel = upto.sort_values("GW").groupby("element")["selected"].last()
        # every manager owns 15 players, so the manager count is sum/15 — not
        # the raw sum, which would shrink every percentage fifteenfold
        total = float(sel.sum()) / 15.0
        if total <= 0:
            return {}
        return {int(k): 100.0 * v / total for k, v in sel.items()}

    def avg_squad_value(self, gw):
        """Rough value of a mid-field squad at this deadline — the template's budget."""
        g = self.gw_df
        upto = g[g.GW <= max(gw - 1, 1)]
        if not len(upto):
            upto = g[g.GW == g.GW.min()]
        pr = upto.sort_values("GW").groupby("element")["value"].last()
        # squad value = sum of 15 most-owned prices, scaled down a touch: the
        # template is never the most expensive squad in the game
        top = pr.sort_values(ascending=False).head(15)
        return round(float(top.sum()) / 10.0 * 0.965, 1)

    # ----------------------------------------------------------------- cache --
    def projections(self, gw, horizon=5):
        key = self.cache_dir / f"proj_gw{gw}_h{horizon}_v{MODEL_VERSION}.pkl"
        if key.exists():
            with open(key, "rb") as f:
                return pickle.load(f)
        hist = self.gw_df[self.gw_df.GW < gw]
        frames = (self.frame_for(gw), self.cur["teams"], self.cur["fixtures"])
        df, teams, _, gws = model.build(
            horizon=min(horizon, 39 - gw), start_gw=gw,
            frames=frames, gw26=hist if len(hist) else None,
            prev_frames=(self.prev["players"], self.prev["teams"], self.prev["gw"]))
        # graft the ownership the field actually had at this deadline onto the
        # projection — the model itself never sees it; only rank tools read it
        own = self.ownership_at(gw)
        df["selected_by"] = df["id"].map(own).fillna(0.0)
        out = (df, gws)
        with open(key, "wb") as f:
            pickle.dump(out, f)
        return out

    def scenarios(self, gw, S, seed=0):
        from . import dist
        key = self.cache_dir / f"scen_gw{gw}_S{S}_s{seed}_v{MODEL_VERSION}.npy"
        if key.exists():
            return np.load(key)
        df, gws = self.projections(gw)
        arr = dist.sample_points(df, gws, n_sims=S, seed=seed)
        np.save(key, arr)
        return arr

    # -------------------------------------------------------------- scoring --
    def score_xi(self, df, squad, gw, xi_ids=None, captain=None):
        """Actual points for a squad's best (or given) XI plus the captain."""
        if xi_ids is None:
            xi, _ = optimize.best_xi(df, squad, gw)
            xi_ids = [int(r.id) for r in xi]
            att = [r for r in xi if r.pos in ("MID", "FWD")] or xi
            captain = int(max(att, key=lambda r: r[f"xp{gw}"]).id)
        total = sum(self.pts.get((i, gw), 0) for i in xi_ids)
        total += self.pts.get((captain, gw), 0) if captain else 0
        return total, xi_ids, captain

    def template_squad(self, df, gw, budget=None):
        """The most-owned affordable 15 at this deadline — the field's squad."""
        own = df["selected_by"].values
        price = df["price"].values
        budget = self.avg_squad_value(gw)
        # greedy by ownership within the formation and club limits: the template
        # is what the crowd owns, not what an optimiser likes
        order = np.argsort(-own)
        squad, per_club, pos_n = [], {}, {"GKP": 0, "DEF": 0, "MID": 0, "FWD": 0}
        need = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
        cost = 0.0
        pos_col = df["pos"].values
        club_col = df["team"].values
        for i in order:
            p, c = pos_col[i], club_col[i]
            if pos_n[p] >= need[p] or per_club.get(c, 0) >= 3:
                continue
            if cost + price[i] > budget:
                continue
            squad.append(int(df["id"].values[i]))
            cost += price[i]
            pos_n[p] += 1
            per_club[c] = per_club.get(c, 0) + 1
            if all(pos_n[p] == need[p] for p in need):
                break
        if sum(pos_n.values()) < 15:
            return None
        return squad

    def field_scores(self, df, gw, n_sims=1500, seed=0):
        """Sampled field squads scored with ACTUAL points, for percentile ranking.

        Squads are drawn with inclusion weight = real ownership, respecting the
        formation; the XI is the best actual-scoring eleven and the captain the
        top actual scorer among attackers — slightly generous to the field, which
        makes a high percentile for the managed arm an honest result.
        """
        rng = np.random.default_rng(seed)
        own = df["selected_by"].values + 0.05
        pos_col = df["pos"].values
        club_col = df["team"].values
        ids = df["id"].values
        price = df["price"].values
        budget = self.avg_squad_value(gw)
        need = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
        scores = np.zeros(n_sims)
        for s in range(n_sims):
            squad, per_club, pos_n, cost = [], {}, {p: 0 for p in need}, 0.0
            taken = set()
            tries = 0
            while sum(pos_n.values()) < 15 and tries < 4000:
                tries += 1
                i = int(rng.integers(0, len(df)))
                p, c = pos_col[i], club_col[i]
                if i in taken or pos_n[p] >= need[p] or per_club.get(c, 0) >= 3:
                    continue
                if cost + price[i] > budget:
                    continue
                if rng.random() > own[i] / own.max():
                    continue
                squad.append(i)
                taken.add(i)
                pos_n[p] += 1
                per_club[c] = per_club.get(c, 0) + 1
                cost += price[i]
            if sum(pos_n.values()) < 15:
                continue
            ids_s = [int(ids[i]) for i in squad]
            pts, _, _ = self.score_xi(df, ids_s, gw)
            scores[s] = pts
        return scores

    # ------------------------------------------------------------------ run --
    def run_policy(self, params: ReplayParams, gw_from=1, gw_to=38,
                   field_sims=1500, verbose=True) -> ReplayResult:
        kw = {"bench_weight": params.bench_weight, "decay": params.decay,
              "xp_prefix": params.xp_prefix, "own_bonus": params.own_bonus,
              "min_differentials": params.min_differentials,
              "max_captain_ownership": params.max_captain_ownership,
              "time_limit": params.time_limit}
        # engines 1-3 extend this mapping as their planner kwargs land
        chips_used = set()                      # chips are once a season
        if params.risk_lambda:
            kw["risk_lambda"] = params.risk_lambda
            kw["cvar_beta"] = params.cvar_beta
        if params.rank_alpha:
            kw["rank_alpha"] = params.rank_alpha
        if params.template_tilt:
            kw["template_tilt"] = params.template_tilt
        if params.cap_tilt:
            kw["cap_tilt"] = params.cap_tilt
        if params.chip_policy == "ilp_tc_bb":
            from .chips import DEFAULT_WINDOWS
            kw.update(chips_tc_bb=True, chip_windows=DEFAULT_WINDOWS,
                      chips_used=tuple(chips_used))

        managed, frozen = None, None
        ft, bank = 15, 100.0                    # gw1: unlimited window
        rows = []
        name = None
        for gw in range(gw_from, gw_to + 1):
            df, gws = self.projections(gw, params.horizon)
            name = df.set_index("id").name.to_dict()
            hits, moved, captain, chip = 0, [], None, None
            if managed is None:
                # the managed arm opens like any manager would: the optimiser's
                # best squad for the opening deadline
                pool = optimize.prune(df, gws)
                first = optimize.solve(pool, gws, allow_infeasible=True,
                                       xp_prefix=params.xp_prefix,
                                       time_limit=params.time_limit)
                if first is None:
                    first_sq = df.nlargest(15, "xp_total")["id"].tolist()
                else:
                    first_sq = first["squad"]
                managed = frozen = first_sq
            else:
                pool = optimize.prune(df, gws, always=managed)
                if params.risk_lambda and params.n_scenarios:
                    from .scenarios import scenario_set
                    samples, weights = scenario_set(
                        pool, gws, S=params.n_scenarios, seed=params.seed)
                    kw.update(scenarios=samples, scenario_weights=weights)
                plan, info = planner_plan(pool, gws, managed,
                                          hit_threshold=params.hit_threshold,
                                          free_transfers=ft, bank=bank, **kw)
                if plan is None:
                    ft = min(5, ft + 1)
                else:
                    wk = plan["weeks"][0]
                    moved, hits = wk["in"], wk["hits"]
                    managed = wk["squad"]
                    captain = wk["captain"]
                    chip = wk.get("chip")
                    if chip:
                        chips_used.add(chip)
                        kw["chips_used"] = tuple(chips_used)
                    ft = (plan["weeks"][1]["free_transfers"]
                          if len(plan["weeks"]) > 1
                          else min(5, ft - len(moved) + hits + 1))
                    bank = (plan["weeks"][1]["bank"]
                            if len(plan["weeks"]) > 1 else wk["bank"])

            m_pts, xi_ids, captain = self.score_xi(df, managed, gw)
            # credit the chip the plan actually played this week
            if chip == "3xc" and captain:
                m_pts += self.pts.get((captain, gw), 0)      # third count
            elif chip == "bboost":
                bench = [i for i in managed if i not in xi_ids]
                m_pts += sum(self.pts.get((i, gw), 0) for i in bench)
            f_pts, _, _ = self.score_xi(df, frozen, gw)
            tmpl = self.template_squad(df, gw)
            t_pts, _, _ = self.score_xi(df, tmpl, gw) if tmpl else (0, [], None)

            row = {"gw": gw, "managed": m_pts, "frozen": f_pts, "template": t_pts,
                   "captain": name.get(captain), "transfers": len(moved),
                   "hits": hits, "free_transfers": ft,
                   "chip": chip,
                   "in": [name.get(i) for i in moved]}
            rows.append(row)
            if verbose:
                print(f"GW{gw:2d}  managed {m_pts:3d}  frozen {f_pts:3d}  "
                      f"template {t_pts:3d}  C {str(name.get(captain))[:14]:14s} "
                      f"({len(moved)} in, {row['hits']} hits)")

        field = self.field_scores(df, gw_to, n_sims=field_sims, seed=params.seed)
        for r in rows:
            r["field_pct"] = round(float((field < r["managed"]).mean() * 100), 1)
        tot = {
            "managed": sum(r["managed"] for r in rows),
            "frozen": sum(r["frozen"] for r in rows),
            "template": sum(r["template"] for r in rows),
            "hits": sum(r["hits"] for r in rows),
            "transfers": sum(r["transfers"] for r in rows),
            "mean_field_pct": round(float(np.mean([r["field_pct"] for r in rows])), 2),
            "worst5_managed": sum(sorted((r["managed"] for r in rows))[:5]),
        }
        return ReplayResult(season=self.season, weeks=rows, totals=tot,
                            field_pct_basis="ownership")


def planner_plan(pool, gws, current, **kw):
    """Indirection so engines can monkeypatch the planner path in tests."""
    from .planner import plan_with_hit_policy
    return plan_with_hit_policy(pool, gws, current, **kw)