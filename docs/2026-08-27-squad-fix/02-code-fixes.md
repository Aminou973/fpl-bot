# Step 2 — Code fixes: no more silent wrong squads

Date: 2026-08-27

## Changes

### `fplbot/api.py` — `squad_state()` (lines ~212)

- **No longer swallows a failed picks call.** The function now tries the
  current gameweek's picks and, if the game has not published them yet,
  falls back to the previous gameweek (correct, because nothing transfers
  between a deadline and the next picks being published).
- Records **`picks_source`** (`"gw12"` / `"none"`) and **`picks_error`** on the
  returned state, so every caller can see what it got.

### `fplbot/pipeline.py` — `resolve_squad_traced()`

- New function alongside `resolve_squad()`: returns `(squad, source)` where
  source is `"api"` or `"config (api picks unusable: … missing ids […])"`.
- `plan_team()` now **prints a loud WARNING** when the plan is built on the
  config fallback squad, embeds `squad_source` in its result, and includes the
  real entry id in the result.

### `jobs/deadline_plan.py`

- Logs `[plan] live squad for Minoux_69: 15 picks (source gw1)` on success and
  a visible fallback line on failure (was a single quiet line before).
- **`bundle["players"]` now includes every player**, not only available ones
  (was `df[df.avail > 0]`). Owned-but-injured players like Yates can no longer
  vanish from the pitch — the dashboard flags them with its existing
  "doubt" chip instead of silently dropping them.
- `builds[name].squad_source` is published so the dashboard itself can prove
  where the squad came from.
- **`state/last_plan.json` is now a complete machine-actable plan**: per team —
  `entry`, `in`/`out`, `squad`, `squad_after`, `xi`, `bench`, `captain`,
  `vice`, `hits`, `squad_source`, and **`picks_payload`** — the exact 15-slot
  array the FPL `my-team` endpoint accepts (XI first in slot order, then bench,
  captain/vice applied). This is what the auto-submit job consumes.

### Encoding fixes (Windows)

All `write_text`/`print` paths now force UTF-8 (`dashboard.py`, `history.py`,
`pipeline.py`, `deadline_plan.py`). The dashboard build used to crash on
Windows consoles (cp1252) over characters like `▲` and `→`.

## Result

Both squads now resolve from the live API every run, and a degraded run is
impossible to miss: it warns in the log, records the source in the bundle, and
the auto-submit job (step 4) refuses to act on a config-fallback squad.