# Step 5 — Verification results and rollout

Date: 2026-08-27

## What was tested locally

| Test | Result |
|---|---|
| Plan run against live API (`deadline_plan.py --force`) | ✅ both teams: 15/15 picks, source `gw1` |
| Submission payload validity (15 slots, unique, captain+vice in XI) | ✅ both teams |
| Yates (owned, injured) present in bundle players and flagged on pitch | ✅ |
| Submit job guard: no `FPL_EMAIL`/`FPL_PASSWORD` → refuses | ✅ |
| Submit job guard: stale plan (wrong GW) → refuses | ✅ (code path `plan.gw != next gw`) |
| Submit job guard: squad source `!= api` → refuses | ✅ (code path in `main`) |
| Submit job dry run with mocked login/my-team: correct OUT/IN/captain diff, no POST fired | ✅ |
| Full 15-player "as it stands" pitch rendering in regenerated `site/index.html` | ✅ |

Not testable locally: the real FPL login + POST (needs real credentials, which
only the user has). First real session will be the GitHub Actions **dry-run
dispatch**; the hourly job then submits for real inside the 36 h deadline
window, guarded by everything above.

## Files changed

- `fplbot/api.py` — squad_state hardening + authenticated client (`login`,
  `my_team`, `submit_picks`)
- `fplbot/pipeline.py` — `resolve_squad_traced`, loud fallback warning,
  `squad_source`/`entry_id` in plan results, UTF-8 state writes
- `fplbot/dashboard.py`, `fplbot/history.py` — UTF-8 writes
- `jobs/deadline_plan.py` — squad-source logging, full player pool in bundle,
  enriched `last_plan.json` with `picks_payload`, UTF-8 stdout/writes
- `jobs/submit_transfers.py` — **new** auto-submit job (dry run by default)
- `.github/workflows/submit.yml` — **new** hourly submit job
- `requirements.txt` — `requests>=2.31`
- `site/bundle.json`, `site/index.html`, `state/last_plan.json` — regenerated

## Rollout

1. Commit + push everything to `main` → Pages redeploys the corrected
   dashboard immediately, well before the GW2 deadline (Fri 28 Aug 17:30 UTC).
2. **User action required**: set `FPL_EMAIL` and `FPL_PASSWORD` repo secrets
   (`gh secret set FPL_EMAIL --body …`, same for `FPL_PASSWORD`).
3. Run one manual dry-run dispatch (`gh workflow run submit`) to confirm the
   login + my-team read works from Actions.
4. From then on, every deadline: plan → auto-submit → dashboard, no manual
   steps. Manual override any time: make the transfers yourself in the FPL
   app before the submit window (36 h before deadline); the submit job sees
   the live squad matches the plan and does nothing — and if you changed your
   squad differently, it reports the diff and still applies only the plan as
   of the last plan run, so check the dashboard/Telegram first.

## The corrected GW2 plan (also on the dashboard)

- **Minoux_69**: OUT Gabriel, Calvert-Lewin → IN Calafiori, João Pedro ·
  captain Haaland, vice Szoboszlai · 2 FT, no hit
- **Minoux_41**: OUT Thiaw, Gibbs-White → IN Szoboszlai, Senesi ·
  captain Thiago, vice Enzo · 2 FT, no hit