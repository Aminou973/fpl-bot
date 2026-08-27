# Step 1 — Diagnosis: why the dashboard squads were wrong / stale

Date: 2026-08-27 · Entries: **Minoux_69** (4894622), **Minoux_41** (4896428)

## What the user saw

- Dashboard squads did not match the real FPL squads.
- Dashboard not updating.
- GW2 transfer plan not usable / wanted auto-submission.

## Root causes found (verified against the live FPL API)

### 1. The dashboard was showing the `config.yml` fallback squad, not the real squad

`fplbot/pipeline.py:22` `resolve_squad()` silently discards API picks unless they
resolve to exactly 15 known players, and falls back to the `squad:` list in
`config.yml`. That fallback list is an old/imaginary squad (Kinsky, Hume, Le Fée,
Palmer IPS, Tzolis, "Georginio"…). Because the failure is silent
(`deadline_plan.py:144` catches everything and just prints one line), the
dashboard happily rendered the config squad as "As it stands".

**Real squads (from `entry/{id}/event/1/picks/`):**

| Minoux_69 | Minoux_41 |
|---|---|
| Raya, Gabriel, Senesi, Tarkowski, Guéhi, Rice, Anderson, Szoboszlai, Calvert-Lewin, Thiago, Haaland (C), Verbruggen, Diop, Hughes, Yates | Kelleher, Collins, Thiaw, Gabriel, Guéhi, Wilson, B.Fernandes (C), Gibbs-White, Semenyo, Enzo, Thiago, Roefs, Truffert, Beto, Obi |

The **2026-08-26 21:45 UTC plan run** (after the code rewrite on 08-25) did
resolve the real squads — the currently deployed bundle matches the picks above.
So the remaining visible defect was №2 and №3:

### 2. Unavailable-but-owned players silently vanish from the pitch

`deadline_plan.py:344`: `bundle["players"] = df[df.avail > 0]` — only available
players are published. **Yates (id 489, Minoux_69) is owned and flagged
"Unspecified injury — unknown return date"**, so he is missing from
`bundle.players`, and the dashboard's pitch builder (`byId[i] && …`) drops his
card silently → Minoux_69 renders a **14-man squad**. 100 real players were
missing from the bundle for this reason (57 injured, 42 unavailable, 1
suspended) — none of them "fit", but any owned one must still be shown.

### 3. Staleness / no signal when the plan could not read the squad

- `api.squad_state()` (`api.py:231`) swallows a failed picks call and returns
  `picks: []` — it never retries the previous gameweek, so any hiccup → config
  fallback → wrong squad, with nothing on the dashboard saying so.
- Nothing records *where* the squad came from (API vs config), so a degraded run
  is indistinguishable from a good one.
- `state/last_plan.json` stores only in/out element ids — not the full squad,
  captain or vice — so nothing downstream (e.g. an auto-submit job) can act on
  the plan.

### 4. No transfer submission path exists at all

The whole codebase is GET-only against the public FPL API. Auto-transfers need
an authenticated session (login → cookies → `POST /api/my-team/{team_id}/`).
Nothing exists for that today (`entry_transfers()` is defined and never called).

### 5. Local repo was behind `origin/main`

The Actions bot had pushed newer dashboard commits than the local copy; the
local `site/bundle.json` (2026-08-21) was 6 days old while the deployed one
(2026-08-26) was fresh. Synced with `git pull --rebase`.

## Current live state (as of this diagnosis)

- GW1 finished (Minoux_69: 48 pts, Minoux_41: 43 pts), 0 transfers used → both
  teams have **2 free transfers**, £0.0m bank, squad value £100.0m.
- GW2 deadline: **2026-08-28 17:30 UTC** (tomorrow).
- Plan of record (from the 08-26 run, built on the real squads):
  - Minoux_69: OUT Gabriel, Calvert-Lewin → IN João Pedro, Virgil
  - Minoux_41: OUT Wilson, Gibbs-White → IN Rogers, Szoboszlai
  - This gets re-verified/rebuilt on live data in step 3.