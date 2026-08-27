# Step 4 — Auto-transfers: how it works and how to arm it

Date: 2026-08-27

## Why not from the dashboard page

The dashboard is a **static GitHub Pages page** — it has no backend and the
browser cannot log in to FPL from another site (auth + CORS). So the
submission runs where the rest of the bot runs: **GitHub Actions**, using the
same plan file the dashboard renders. The dashboard shows what will be (and
was) submitted; the submission itself is automatic.

## What was added

### `fplbot/api.py` — authenticated client (new section)

- `login(email, password)` → authenticated `requests.Session` + mapping of
  **entry_id → my-team id** from `/api/me/` (the internal id the write
  endpoints need).
- `my_team(session, team_id)` → current picks, bank, chips (read-only).
- `submit_picks(session, team_id, picks, chip=None)` →
  `POST /api/my-team/{team_id}/` with the 15-slot lineup.

### `jobs/submit_transfers.py`

Reads `state/last_plan.json` and writes the planned lineup for each team.
**Dry run by default** (`--apply` to actually submit). It refuses to act
unless every guard passes:

1. the plan's gameweek equals the gameweek whose deadline is actually next;
2. the deadline is inside the act window (default 36 h, `--window` to change);
3. the plan's squads came **from the API** (a config-fallback squad is never
   submitted — this is the fix that makes wrong squads impossible to push);
4. the live squad already matching the plan → nothing to do;
5. `FPL_REFRESH_TOKEN` (and `_2` for the second account) must be set (repo
   secrets in Actions) — see step `07-oauth-migration.md`: FPL retired
   email/password login, so the job authenticates with a refresh token from
   the one-time browser login.

### `.github/workflows/submit.yml`

- Hourly (`cron 42 * * * *`); exits quietly unless inside the 36 h window.
- `workflow_dispatch` with an **`apply` toggle that defaults to false**
  (dispatch = dry run, always, unless explicitly ticked).
- Commits `state/auto_submit.json` (audit log per gameweek: mode, results).

## To arm it (one-time, ~1 minute per account)

**Two squads on two different accounts → two refresh tokens** (the job
refreshes each token, lists the entries each account manages, and picks the
one that actually manages each squad):

```bash
arm_fpl_login.bat                     # does both accounts + secret + dry run
# or manually:
python jobs/fpl_login.py              # first account  (e.g. Minoux_69)
python jobs/fpl_login.py --account 2  # second account (e.g. Minoux_41)
```

Each run opens the FPL sign-in page in the browser; sign in, then paste back
the redirected URL (it contains `?code=…`) and the token is stored with
`gh secret set`. The old `FPL_EMAIL` / `FPL_PASSWORD` secrets are no longer
used and can be deleted. Full detail: `07-oauth-migration.md`.

Then test read-only end-to-end:

```bash
gh workflow run submit && gh run watch
```

The dispatch run is a **dry run**: it logs in to each account, reads the live
squads, prints the exact OUT/IN/captain diff it would write per team, and
stops.

The hourly schedule submits for real, but never on an untested path: a real
submission requires a successful dry run for that gameweek in the audit log
(`state/auto_submit.json`). So the first scheduled tick after the 36 h window
opens performs the dry run, and the next hourly tick (still hours before the
deadline) applies. Re-runs that find the live squad already matching the plan
do nothing.

From the next deadline on, the loop is fully automatic:
**plan (3× daily) → submit (≤36 h before deadline) → dashboard shows the
lineup the game now holds**.

## Status / audit trail

- `state/auto_submit.json` — what was done, when, for which GW (committed by
  the workflow).
- The plan brief and results still go to Telegram; submissions are logged in
  the Actions run output.