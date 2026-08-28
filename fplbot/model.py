"""
FPL 2026/27 expected-points engine.

Builds a per-player, per-gameweek expected-points projection from:
  - 2026/27 official player list, prices, positions, availability (players_raw.csv)
  - 2026/27 full fixture list with FPL difficulty ratings
  - 2025/26 per-gameweek performance history (merged_gw.csv) for rate estimation

Scoring follows the 2026/27 FPL rules, including defensive contribution points.
"""
import numpy as np
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------- constants --
POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
GOAL_PTS = {1: 10, 2: 6, 3: 5, 4: 4}
CS_PTS = {1: 4, 2: 4, 3: 1, 4: 0}
LEAGUE_GPG = 1.45          # goals per team per game
HOME_ADV = 1.12
AWAY_ADV = 0.89
# ---------------------------------------------------------------------------
# Constants below are FITTED, not guessed. Sources, all measured over the
# 2021-22 to 2025-26 seasons of official Fantasy data (Covid-hit 2020-21 and
# 2021-22 excluded from the team-strength fit):
#
#   SHRINK_TEAM   a club's attack rating carries a slope of 0.56 into the next
#                 season (r=0.62, n=68 club-seasons); defence 0.53. So a little
#                 under half of last season's deviation from average should be
#                 thrown away, not a quarter.
#   PROMOTED_*    the twelve clubs promoted into the last four seasons averaged
#                 0.719 attack and 1.309 defence in their first year back.
#   SHRINK_K      regressing next-season goal involvement per 90 on a player's
#                 own history and on their price prior over 1,006 paired
#                 player-seasons gives 0.37 x history + 0.55 x price. The market
#                 predicts a player better than his own last season does, which
#                 works out at roughly 32 starts of shrinkage, not six.
#   MINUTES_*     a least-squares fit over 2,040 paired player-seasons:
#                   starts_next = 0.597*starts_prev + 0.053*apps_prev + 2.957
#                 (R^2 0.42). Even a player who appeared 38 times and started 35
#                 only starts about 68% of the following season - injuries,
#                 transfers, age and lost places all live in that number. The
#                 model previously assumed 90%+ for such players, which inflated
#                 every projection it produced.
# ---------------------------------------------------------------------------
SHRINK_TEAM = 0.45
PROMOTED_ATT = 0.719
PROMOTED_DEF = 1.309
SHRINK_K = 32.0          # with no current-season evidence
SHRINK_K_LIVE = 7.0      # once this season has spoken for itself


def shrink_k(n_cur):
    """How hard to pull a player toward what his price implies.

    The 32-start figure is calibrated for predicting a season before it starts,
    when a player's price is genuinely the better guide. Inside a season that
    stops being true: the market is slow to mark down a player who has stopped
    producing, and anchoring to his price inherits that lag. A 2025-26 backtest
    showed the cost plainly - the engine captained a collapsed Salah in 30 of 38
    gameweeks because his price never fell far enough to say otherwise. So the
    anchor loosens as this season's evidence accumulates.
    """
    try:
        n = float(n_cur)
    except (TypeError, ValueError):
        n = 0.0
    if n != n or n < 0:          # NaN is truthy, so it has to be tested for
        n = 0.0
    w = n / (n + 8.0)
    return SHRINK_K * (1 - w) + SHRINK_K_LIVE * w

MINUTES_B_STARTS = 0.5967
MINUTES_B_APPS = 0.0532
MINUTES_B0 = 2.957


def minutes_prior(apps, starts):
    """Expected share of gameweeks started next season, from the fitted model."""
    if apps <= 0:
        return None
    pred = MINUTES_B_STARTS * starts + MINUTES_B_APPS * apps + MINUTES_B0
    return float(min(max(pred / 38.0, 0.02), 0.85))


# Premier League clubs win roughly 5.5 penalties a season and convert about 79%,
# so being the designated taker is worth about 0.115 goals a game. Only the CHANGE
# in that role is applied: a player who took them last season already has those
# goals inside his own history, and counting them twice would inflate him.
PEN_GOALS_PER_GAME = 0.115


# ------------------------------------------------------------------- loading --
def load(frames=None, gw26=None, prev_frames=None):
    """Load the model's inputs.

    frames: optional (players, teams, fixtures) DataFrames straight from the live
    API. When omitted the CSV snapshots in data/ are used, which keeps the whole
    engine runnable offline.
    gw26: optional current-season gameweek history (same shape as merged_gw.csv).
    prev_frames: optional (players, teams, gameweeks) for the PREVIOUS season,
        so a backtest can hand the engine the season that was actually behind it
        rather than the one shipped in data/.
    """
    if frames is not None:
        p26, t26, fx = frames
    else:
        p26 = pd.read_csv(DATA / "2026-27/players_raw.csv")
        t26 = pd.read_csv(DATA / "2026-27/teams.csv")
        fx = pd.read_csv(DATA / "2026-27/fixtures.csv")
    if prev_frames is not None:
        p25, t25, gw = prev_frames
    else:
        p25 = pd.read_csv(DATA / "2025-26/players_raw.csv")
        t25 = pd.read_csv(DATA / "2025-26/teams.csv")
        gwp = DATA / "2025-26/gws/merged_gw.csv"
        gw = pd.read_csv(gwp if gwp.exists() else DATA / "2025-26/merged_gw.csv")
    # once the new season is under way the mirror publishes its own gameweek
    # files; those are far more relevant than last season's.
    if gw26 is None:
        cur = DATA / "2026-27/gws/merged_gw.csv"
        gw26 = pd.read_csv(cur) if cur.exists() else None
    if gw26 is not None and not len(gw26):
        gw26 = None
    return p26, t26, fx, p25, t25, gw, gw26


# ----------------------------------------------------------- team strengths --
def team_ratings(gw, t25, t26):
    """Attack / defence ratings per 2026/27 team id, from 2025/26 xG + goals."""
    # team-match level: one row per (fixture, team)
    m = gw[["fixture", "team", "opponent_team", "was_home", "team_h_score",
            "team_a_score", "expected_goals", "expected_goals_conceded"]].copy()
    per_match = m.groupby(["fixture", "team", "was_home"], as_index=False).agg(
        gf=("team_h_score", "first"), ga=("team_a_score", "first"),
        xg=("expected_goals", "sum"))
    # team_h_score/team_a_score are the match scoreline; orient them
    per_match["goals_for"] = np.where(per_match.was_home, per_match.gf, per_match.ga)
    per_match["goals_against"] = np.where(per_match.was_home, per_match.ga, per_match.gf)

    agg = per_match.groupby("team").agg(
        gf=("goals_for", "mean"), ga=("goals_against", "mean"),
        xg=("xg", "mean"), n=("fixture", "count")).reset_index()
    # de-home/away: ratings are averages over a balanced 38-game schedule
    agg["att_raw"] = (0.55 * agg.xg + 0.45 * agg.gf) / LEAGUE_GPG
    agg["def_raw"] = agg.ga / LEAGUE_GPG

    # merged_gw.csv stores the club's full name in `team`
    name25 = dict(zip(t25.name, t25.short_name))
    agg["short"] = agg.team.map(name25)
    if agg.short.isna().any():
        missing = sorted(set(agg.team[agg.short.isna()]))
        raise ValueError(f"unmapped clubs in gameweek data: {missing}")

    ratings = {}
    for _, r in agg.iterrows():
        ratings[r.short] = (r.att_raw, r.def_raw)

    out = {}
    for _, r in t26.iterrows():
        att, dfn = ratings.get(r.short_name, (PROMOTED_ATT, PROMOTED_DEF))
        # shrink toward league average - squads change over a summer
        att = 1 + (att - 1) * (1 - SHRINK_TEAM)
        dfn = 1 + (dfn - 1) * (1 - SHRINK_TEAM)
        out[r.id] = {"short": r.short_name, "name": r.name, "att": att, "def": dfn,
                     "promoted": r.short_name not in ratings}
    return out


def blend_team_ratings(prev, cur, n_gw):
    """Fold this season's results into last season's ratings as they accrue."""
    w = n_gw / (n_gw + 8.0)
    out = {}
    for tid, v in prev.items():
        c = cur.get(tid)
        if c is None:
            out[tid] = v
            continue
        out[tid] = {**v,
                    "att": (1 - w) * v["att"] + w * c["att"],
                    "def": (1 - w) * v["def"] + w * c["def"]}
    return out


def blend_rates(prev, cur, comp):
    """Weighted blend of per-start rates, current season gaining weight."""
    cols = comp + ["h_xg", "h_xa"]
    out = prev.reindex(prev.index.union(cur.index))
    for c in cols + ["n_starts", "apps", "tot_pts"]:
        if c not in out:
            out[c] = 0.0
    n_cur = cur.n_starts.reindex(out.index).fillna(0)
    w = n_cur / (n_cur + 6.0)
    for c in cols:
        a = out[c].fillna(0.0)
        b = cur[c].reindex(out.index).fillna(a)
        out[c] = (1 - w) * a + w * b
    out["n_starts"] = out.n_starts.fillna(0) + n_cur
    out["apps"] = out.apps.fillna(0) + cur.apps.reindex(out.index).fillna(0)
    out["n_cur"] = n_cur
    return out


def fixture_xg(teams, team_id, opp_id, home):
    """Expected goals for / against for one team in one fixture."""
    adv_f, adv_a = (HOME_ADV, AWAY_ADV) if home else (AWAY_ADV, HOME_ADV)
    xgf = LEAGUE_GPG * teams[team_id]["att"] * teams[opp_id]["def"] * adv_f
    xga = LEAGUE_GPG * teams[opp_id]["att"] * teams[team_id]["def"] * adv_a
    return xgf, xga


# ------------------------------------------------------- per-player history --
def player_rates(gw, p25, p26, teams25_to_short, t26):
    """Per-start scoring-component rates from 2025/26, keyed by player code."""
    g = gw.copy()
    g = g[g.minutes > 0]
    # Seasons before 2025-26 predate defensive-contribution scoring and simply do
    # not carry these columns. Treat them as zero rather than crashing, so the
    # engine can be run against any season.
    for c in ("clearances_blocks_interceptions", "recoveries", "tackles",
              "defensive_contribution", "expected_goals", "expected_assists",
              "expected_goals_conceded", "starts"):
        if c not in g.columns:
            g[c] = 0.0
        g[c] = pd.to_numeric(g[c], errors="coerce").fillna(0.0)

    # per-appearance component points
    g["pos"] = g.position.map({"GK": 1, "GKP": 1, "DEF": 2, "MID": 3, "FWD": 4})
    g = g.dropna(subset=["pos"])
    g["pos"] = g["pos"].astype(int)

    g["p_goals"] = g.goals_scored * g.pos.map(GOAL_PTS)
    g["p_assists"] = g.assists * 3
    g["p_cs"] = g.clean_sheets * g.pos.map(CS_PTS) * (g.minutes >= 60)
    g["p_conceded"] = -(g.goals_conceded // 2) * g.pos.isin([1, 2])
    g["p_saves"] = (g.saves // 3) * (g.pos == 1)
    g["p_bonus"] = g.bonus
    g["p_cards"] = -(g.yellow_cards + 3 * g.red_cards) - 2 * g.own_goals \
                   + 5 * g.penalties_saved - 2 * g.penalties_missed
    # defensive contribution: 2 pts, DEF need 10 CBIT, MID/FWD need 12 CBIT+recoveries
    dc_thresh = np.where(g.pos == 2, 10, 12)
    dc_stat = np.where(g.pos == 2, g.clearances_blocks_interceptions,
                       g.clearances_blocks_interceptions + g.recoveries)
    g["p_dc"] = 2 * (dc_stat >= dc_thresh) * (g.pos != 1)

    idmap = dict(zip(p25.id, p25.code))
    g["code"] = g.element.map(idmap)
    g = g.dropna(subset=["code"])
    g["code"] = g["code"].astype(int)

    comp = ["p_goals", "p_assists", "p_cs", "p_conceded", "p_saves",
            "p_bonus", "p_cards", "p_dc"]

    starts = g[g.minutes >= 60]
    rates = starts.groupby("code")[comp].mean()
    rates["n_starts"] = starts.groupby("code").size()
    rates["mins_pg"] = starts.groupby("code")["minutes"].mean()

    apps = g.groupby("code").agg(apps=("minutes", "size"),
                                 tot_min=("minutes", "sum"),
                                 tot_pts=("total_points", "sum"))
    rates = rates.join(apps, how="outer")
    rates["n_starts"] = rates.n_starts.fillna(0)
    for c in comp:
        rates[c] = rates[c].fillna(0.0)

    # xG-informed blend of attacking output (regresses hot/cold finishing)
    xg = starts.groupby("code")[["expected_goals", "expected_assists"]].mean()
    xg.columns = ["h_xg", "h_xa"]
    rates = rates.join(xg)
    rates["h_xg"] = rates.h_xg.fillna(0)
    rates["h_xa"] = rates.h_xa.fillna(0)
    return rates, comp


def price_curves(gw, p25, rates, comp):
    """Per-start component rates as a function of a player's price.

    FPL prices encode the market's expectation of a player's role and output,
    so a price-conditioned prior is a far better shrinkage target than the flat
    positional mean: it stops elite players being dragged down toward bench
    fodder, and it gives new signings with no Premier League history a sensible
    starting estimate.
    """
    g = gw[gw.minutes > 0].copy()
    idmap = dict(zip(p25.id, p25.code))
    g["code"] = g.element.map(idmap)
    start_price = g.sort_values("GW").groupby("code")["value"].first()

    et = dict(zip(p25.code, p25.element_type))
    tab = rates.join(start_price.rename("price0"))
    tab["et"] = tab.index.map(et)
    tab = tab[(tab.n_starts >= 8) & tab.price0.notna()]

    curves = {}
    for e in [1, 2, 3, 4]:
        h = tab[tab.et == e]
        if len(h) < 25:
            continue
        edges = np.unique(np.quantile(h.price0, np.linspace(0, 1, 7)))
        h = h.assign(b=pd.cut(h.price0, edges, include_lowest=True))
        agg = h.groupby("b", observed=True).agg(
            **{"price": ("price0", "mean")},
            **{c: (c, "mean") for c in comp},
            **{"h_xg": ("h_xg", "mean"), "h_xa": ("h_xa", "mean")}).dropna()
        curves[e] = agg
    return curves


def curve_prior(curves, et, cost, comp):
    c = curves.get(et)
    if c is None or len(c) == 0:
        return {k: 0.0 for k in comp}
    px = c.price.values
    return {k: float(np.interp(cost, px, c[k].values)) for k in comp}


def shrink(value, prior, n, k):
    """Empirical-Bayes shrink of a per-start rate toward a positional prior."""
    return (value * n + prior * k) / (n + k)


# ---------------------------------------------------- minutes / start model --
def start_prob_from_price(p26, rates, p25):
    """Map price rank within position to a starting probability.

    Calibrated on 2025/26: starting price vs. share of gameweeks started.
    Used as the prior for every player, and as the sole estimate for players
    with no Premier League history (new signings, promoted clubs).
    """
    hist = p25[["code", "element_type", "now_cost", "starts"]].copy()
    hist["share"] = (hist.starts / 38).clip(0, 1)
    curve = {}
    for et in [1, 2, 3, 4]:
        h = hist[hist.element_type == et]
        if len(h) < 20:
            continue
        bins = np.quantile(h.now_cost, np.linspace(0, 1, 9))
        bins = np.unique(bins)
        h = h.assign(b=pd.cut(h.now_cost, bins, include_lowest=True))
        curve[et] = h.groupby("b", observed=True).agg(
            price=("now_cost", "mean"), share=("share", "mean")).dropna()
    return curve


def price_prior(curve, et, cost):
    c = curve.get(et)
    if c is None or len(c) == 0:
        return 0.5
    return float(np.interp(cost, c.price.values, c.share.values))


def next_gw(fx=None):
    """First gameweek that has not finished yet."""
    if fx is None:
        fx = pd.read_csv(DATA / "2026-27/fixtures.csv")
    fx = fx[fx.event.notna()]
    pend = fx[~fx.finished.astype(bool)]
    return int(pend.event.min()) if len(pend) else 38


# ----------------------------------------------------------------- projector --
MODEL_VERSION = 2          # bump when projections change shape or meaning


def build(horizon=5, start_gw=1, frames=None, gw26=None, prev_frames=None,
          with_components=True, news=None):
    p26, t26, fx, p25, t25, gw, gw26 = load(frames=frames, gw26=gw26,
                                            prev_frames=prev_frames)
    teams = team_ratings(gw, t25, t26)
    if gw26 is not None and gw26.GW.nunique() >= 3:
        teams = blend_team_ratings(teams, team_ratings(gw26, t26, t26),
                                   gw26.GW.nunique())
    rates, comp = player_rates(gw, p25, p26, None, t26)
    if gw26 is not None and gw26.GW.nunique() >= 1:
        cur_rates, _ = player_rates(gw26, p26, p26, None, t26)
        rates = blend_rates(rates, cur_rates, comp)
    curve = start_prob_from_price(p26, rates, p25)

    short25 = dict(zip(t25.id, t25.short_name))
    short26 = {r.id: r.short_name for _, r in t26.iterrows()}
    old_team = dict(zip(p25.code, p25.team.map(short25)))
    prev_pen = dict(zip(p25.code, p25.get("penalties_order", pd.Series(dtype=float))))
    att26_by_short = {v["short"]: v["att"] for v in teams.values()}
    def26_by_short = {v["short"]: v["def"] for v in teams.values()}
    # 2025/26 attack ratings, unshrunk-ish, for club-move rescaling
    att25 = {}
    for _, r in t25.iterrows():
        att25[r.short_name] = att26_by_short.get(r.short_name, PROMOTED_ATT)

    # league-average per-start components by position (priors)
    p26 = p26.copy()
    p26["code"] = p26.code.astype(int)
    j = p26.merge(rates, left_on="code", right_index=True, how="left")
    curves = price_curves(gw, p25, rates, comp)

    # ---- availability -----------------------------------------------------
    # engine 6: scraped team news, as {element_id: news_risk}. Pre-agreement
    # constraint enforced here: a signal may only LOWER availability, and only
    # for a player the API itself flags doubtful - it can never rescue a
    # player FPL has ruled out, and never invents availability.
    news_map = {}
    if news is not None and len(news):
        news_map = {int(e): float(v) for e, v in
                    zip(news["element"], news["news_risk"])}

    def availability(r):
        st = r.status
        chance = r.chance_of_playing_next_round
        if st == "u":                       # unavailable / left the club
            return 0.0
        if st in ("i", "s"):                # injured / suspended
            return 0.0 if pd.isna(chance) else float(chance) / 100.0
        if st == "d":                       # doubtful
            return 0.5 if pd.isna(chance) else float(chance) / 100.0
        return 1.0

    fx = fx[fx.event.notna()].copy()
    fx["event"] = fx.event.astype(int)
    gws = list(range(start_gw, start_gw + horizon))

    # --- goalkeeper depth chart: exactly one keeper plays for each club.
    # Rank each club's keepers by price, then by 2025/26 starts.
    gk = j[j.element_type == 1].copy()
    gk["_starts"] = gk.n_starts.fillna(0)
    gk = gk.sort_values(["team", "now_cost", "_starts"], ascending=[True, False, False])
    gk_rank = {}
    for tid, grp in gk.groupby("team"):
        for i, code in enumerate(grp.code.values):
            gk_rank[int(code)] = i

    rows = []
    for _, r in j.iterrows():
        et = int(r.element_type)
        tid = int(r.team)
        n = 0 if pd.isna(r.n_starts) else float(r.n_starts)

        # --- expected share of games started
        prior_share = price_prior(curve, et, r.now_cost)
        apps_n = 0 if pd.isna(r.apps) else float(r.apps)
        if apps_n > 0:
            # Two independent, separately calibrated estimates of next season's
            # start share: what players with this appearance record actually went
            # on to do, and what players at this price actually do. Averaged,
            # because both are already unbiased - neither needs shrinking again.
            hist = minutes_prior(apps_n, n)
            share = 0.5 * hist + 0.5 * prior_share if hist is not None else prior_share
        else:
            share = prior_share
        avail = availability(r)
        nr = news_map.get(int(r.id))
        if nr is not None and nr < 1.0 and r.status == "d":
            avail = avail * nr
        if et == 1:
            # Only one keeper plays, so the depth chart decides who - but the
            # first choice gets the same calibrated share as everyone else
            # rather than an assumed near-certainty. Measured: premium keepers
            # start about 78% of a season, not 94%.
            rank = gk_rank.get(int(r.code), 1)
            if rank > 0:
                share = 0.05 if rank == 1 else 0.02
        elif n == 0 and apps_n == 0:
            share *= 0.88          # unproven in the Premier League
        share = float(np.clip(share, 0.02, 0.96)) * avail

        # --- per-start component rates, shrunk toward a price-conditioned prior
        pr = curve_prior(curves, et, r.now_cost, comp + ["h_xg", "h_xa"])
        k_eff = shrink_k(r.get("n_cur"))
        rate = {}
        for c in comp:
            v = 0.0 if pd.isna(r.get(c)) else float(r.get(c))
            rate[c] = shrink(v, pr[c], n, k_eff)

        # blend underlying numbers (xG/xA) with actual returns to damp variance
        if n >= 6:
            xg_pts = float(r.h_xg) * GOAL_PTS[et]
            xa_pts = float(r.h_xa) * 3
            pr_xg = pr["h_xg"] * GOAL_PTS[et]
            pr_xa = pr["h_xa"] * 3
            rate["p_goals"] = 0.5 * shrink(xg_pts, pr_xg, n, k_eff) + 0.5 * rate["p_goals"]
            rate["p_assists"] = 0.5 * shrink(xa_pts, pr_xa, n, k_eff) + 0.5 * rate["p_assists"]

        # --- penalties: credit the role only where it has actually changed
        cur_pen = r.get("penalties_order")
        was_taker = float(prev_pen.get(r.code, 99) or 99) == 1.0
        is_taker = float(cur_pen) == 1.0 if pd.notna(cur_pen) else False
        pen_delta = 0.0
        if is_taker and not was_taker:
            pen_delta = PEN_GOALS_PER_GAME * GOAL_PTS[et]
        elif was_taker and not is_taker:
            pen_delta = -PEN_GOALS_PER_GAME * GOAL_PTS[et]
        rate["p_goals"] = max(rate["p_goals"] + pen_delta, 0.0)

        # --- club-move rescaling of attacking output
        ot = old_team.get(r.code)
        move_mult = 1.0
        if ot and ot in att25:
            new_att = att26_by_short[short26[tid]]
            move_mult = float(np.clip(new_att / max(att25[ot], 0.4), 0.6, 1.6))
        elif n == 0:
            move_mult = 1.0
        rate["p_goals"] *= move_mult
        rate["p_assists"] *= move_mult

        # baseline 2025/26 context for this player's team (for fixture scaling)
        base_xgf = LEAGUE_GPG * att26_by_short[short26[tid]]
        base_xga = LEAGUE_GPG * def26_by_short[short26[tid]]
        base_cs = np.exp(-base_xga)

        player_fx = fx[((fx.team_h == tid) | (fx.team_a == tid)) & (fx.event.isin(gws))]
        per_gw = {}
        for _, f in player_fx.iterrows():
            home = f.team_h == tid
            opp = int(f.team_a if home else f.team_h)
            xgf, xga = fixture_xg(teams, tid, opp, home)
            att_mult = xgf / max(base_xgf, 0.2)
            cs_prob = np.exp(-xga)
            cs_mult = cs_prob / max(base_cs, 0.03)
            conc_mult = xga / max(base_xga, 0.2)

            pts_start = (
                2.0                                   # appearance (60+)
                + rate["p_goals"] * att_mult
                + rate["p_assists"] * att_mult
                + rate["p_cs"] * cs_mult
                + rate["p_conceded"] * conc_mult
                + rate["p_saves"] * conc_mult
                + rate["p_bonus"] * (0.6 + 0.4 * att_mult)
                + rate["p_dc"] * (0.85 + 0.15 * conc_mult)
                + rate["p_cards"]
            )
            # cameo appearances contribute a little
            cameo = 0.35 * (1 - share) * avail * (1.0 + 0.35 * rate["p_goals"])
            xp = share * pts_start + cameo
            gwno = int(f.event)
            # distribution layer inputs (fplbot/dist.py): Poisson means for the
            # sampling-variance components, and the CS probability as a real
            # probability. Summed across fixtures, so a double gameweek adds
            # its lambdas exactly as two independent Poisson draws would.
            per_gw[f"lg_{gwno}"] = per_gw.get(f"lg_{gwno}", 0.0) + share * rate["p_goals"] * att_mult
            per_gw[f"la_{gwno}"] = per_gw.get(f"la_{gwno}", 0.0) + share * rate["p_assists"] * att_mult
            per_gw[f"cs_{gwno}"] = per_gw.get(f"cs_{gwno}", 0.0) + share * rate["p_cs"] * cs_mult
            per_gw[f"csp_{gwno}"] = 1.0 - (1.0 - per_gw.get(f"csp_{gwno}", 0.0)) * (1.0 - float(cs_prob))
            per_gw[f"nfx_{gwno}"] = per_gw.get(f"nfx_{gwno}", 0) + 1
            if gwno == gws[0] and "brk" not in per_gw:
                per_gw["brk"] = {
                    "app": round(share * 2.0 + cameo, 2),
                    "goals": round(share * rate["p_goals"] * att_mult, 2),
                    "assists": round(share * rate["p_assists"] * att_mult, 2),
                    "cs": round(share * (rate["p_cs"] * cs_mult + rate["p_conceded"] * conc_mult), 2),
                    "saves": round(share * rate["p_saves"] * conc_mult, 2),
                    "dc": round(share * rate["p_dc"] * (0.85 + 0.15 * conc_mult), 2),
                    "bonus": round(share * rate["p_bonus"] * (0.6 + 0.4 * att_mult), 2),
                    "cs_prob": round(float(cs_prob), 3),
                    "team_xg": round(float(xgf), 2),
                    "team_xga": round(float(xga), 2),
                }
            per_gw[gwno] = per_gw.get(gwno, 0.0) + max(xp, 0.0)
            per_gw.setdefault(f"opp_{gwno}", [])
            per_gw[f"opp_{gwno}"].append(
                (teams[opp]["short"], "H" if home else "A",
                 int(f.team_h_difficulty if home else f.team_a_difficulty)))

        row = {
            "id": int(r.id), "code": int(r.code), "name": r.web_name,
            "full_name": f"{r.first_name} {r.second_name}" if "second_name" in r else r.web_name,
            "pos": POS[et], "et": et, "team": short26[tid], "team_id": tid,
            "price": r.now_cost / 10.0, "status": r.status,
            "news": "" if pd.isna(r.news) else str(r.news),
            "start_share": round(share, 3), "avail": avail,
            "hist_starts": int(n), "hist_pts": 0 if pd.isna(r.tot_pts) else int(r.tot_pts),
            "selected_by": float(r.selected_by_percent) if "selected_by_percent" in r and not pd.isna(r.selected_by_percent) else 0.0,
            "promoted_club": teams[tid]["promoted"],
            "penalties": None if pd.isna(r.get("penalties_order")) else int(r.get("penalties_order")),
            "set_pieces": None if pd.isna(r.get("corners_and_indirect_freekicks_order"))
                          else int(r.get("corners_and_indirect_freekicks_order")),
        }
        for g_ in gws:
            row[f"xp{g_}"] = round(per_gw.get(g_, 0.0), 3)
            opps = per_gw.get(f"opp_{g_}", [])
            row[f"fx{g_}"] = ", ".join(f"{o}({s}){d}" for o, s, d in opps) if opps else "BLANK"
            row[f"fdr{g_}"] = int(np.mean([d for _, _, d in opps])) if opps else 5
            # distribution-layer columns consumed by fplbot/dist.py
            row[f"p_start{g_}"] = round(float(share), 4)
            row[f"lam_goals{g_}"] = round(per_gw.get(f"lg_{g_}", 0.0), 4)
            row[f"lam_assists{g_}"] = round(per_gw.get(f"la_{g_}", 0.0), 4)
            row[f"cmp_cs{g_}"] = round(per_gw.get(f"cs_{g_}", 0.0), 4)
            row[f"csp{g_}"] = round(per_gw.get(f"csp_{g_}", 0.0), 4)
            row[f"nfx{g_}"] = per_gw.get(f"nfx_{g_}", 0)
        # explosive keeps its old meaning as a display feature (share of first-gw
        # xp from goals/assists/bonus). The ceiling score itself is no longer a
        # deterministic tilt on xp — cxp is now the simulated q85, attached below.
        b = per_gw.get("brk", {})
        expl = b.get("goals", 0.0) + b.get("assists", 0.0) + b.get("bonus", 0.0)
        base = max(row[f"xp{gws[0]}"], 0.01)
        row["explosive"] = round(min(expl / base, 1.0), 3)
        row["xp_total"] = round(sum(row[f"xp{g_}"] for g_ in gws), 3)
        brk = per_gw.get("brk", {})
        for k_, v_ in brk.items():
            row[f"b_{k_}"] = v_
        rows.append(row)

    df = pd.DataFrame(rows)
    df["value"] = (df.xp_total / df.price).round(3)

    # ceiling from simulation, not from a heuristic: q85 of the sampled point
    # distribution, with cxp kept as a deprecated alias for it
    from . import dist as _dist
    _dist.attach_quantiles(df, gws, seed=start_gw)

    if not with_components:
        # the full-season build (chip calendar) carries ~10 columns per gameweek
        # of sampling inputs the downstream consumers never read
        drop = [c for c in df.columns
                if c.startswith(("lam_", "cmp_", "csp", "nfx"))]
        df = df.drop(columns=drop)
    return df, teams, fx, gws


if __name__ == "__main__":
    df, teams, fx, gws = build(start_gw=next_gw())
    df.to_csv(DATA.parent / "projections.csv", index=False)
    print(df.sort_values("xp_total", ascending=False)
            .head(25)[["name", "pos", "team", "price", "start_share",
                       "xp1", "xp_total", "value"]].to_string(index=False))
