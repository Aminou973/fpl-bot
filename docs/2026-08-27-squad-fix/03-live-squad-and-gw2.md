# Step 3 — Live squad verified + corrected GW2 plan

Date: 2026-08-27 · Plan rebuilt at 13:25 UTC with `python jobs/deadline_plan.py --force`

## Verification against the live FPL API

| Check | Minoux_69 (4894622) | Minoux_41 (4896428) |
|---|---|---|
| Squad source | **api** (picks gw1) | **api** (picks gw1) |
| 15/15 players match the real GW1 picks | ✅ | ✅ |
| Yates (owned, injured) now renders flagged on the dashboard | ✅ | — |
| Free transfers | 2 (rolled from GW1) | 2 (rolled from GW1) |
| Bank | £0.0m | £0.0m |

Real GW1 squads confirmed from `entry/{id}/event/1/picks/`:

- **Minoux_69**: Raya · Gabriel, Senesi, Tarkowski, Guéhi · Rice, Anderson,
  Szoboszlai · Calvert-Lewin, Thiago, **Haaland (C)** · bench: Verbruggen,
  Diop, Hughes, Yates
- **Minoux_41**: Kelleher · Collins, Thiaw, Gabriel, Guéhi · Wilson,
  **B.Fernandes (C)**, Gibbs-White, Semenyo, Enzo · Thiago · bench: Roefs,
  Truffert, Beto, Obi

## Corrected GW2 plan (deadline Fri 28 Aug, 17:30 UTC)

The 26 Aug plan was built on the same real squads but is now superseded —
one day of fresh prices/news changed the optimiser's mind:

**Minoux_69** — 2 free transfers, no hit
- OUT: Gabriel (ARS £8.0), Calvert-Lewin (LEE £6.0)
- IN: **Calafiori** (ARS £5.6), **João Pedro** (CHE £7.6)
- Captain: **Haaland**, vice: Szoboszlai
- Projected 36.6 this week; ⚠️ Yates still out (unspecified injury)

**Minoux_41** — 2 free transfers, no hit
- OUT: Thiaw (NEW £5.0), Gibbs-White (NFO £8.0 — flagged, 75% to play)
- IN: **Szoboszlai** (LIV £7.0), **Senesi** (TOT £6.0)
- Captain: **Thiago** (BRE), vice: Enzo
- Projected 36.9 this week

Both plans respect the 2 free transfers → **0 points cost**.

`state/last_plan.json` now carries the submission-ready `picks_payload` for
each team (15 slots, unique, captain+vice in the XI, verified programmatically).

## Dashboard

`site/bundle.json` + `site/index.html` regenerated (614 players in the pool,
all squads rendered in full). Pushed to Pages in step 5.