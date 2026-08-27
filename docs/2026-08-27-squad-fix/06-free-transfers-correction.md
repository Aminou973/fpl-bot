# Step 6 — Correction: 1 free transfer, not 2

Date: 2026-08-27 (evening)

## What happened

The bot recomputed free transfers from transfer history using the standard
banking rule (unused GW1 transfer → 2 FT for GW2): history showed 0 transfers
in GW1 on both entries. But **both official FPL apps/sites show 1 free
transfer** for both accounts — the game's own screen is the authority, so
either unused FTs do not bank this season or the rule changed. The plan was
rebuilt pinned to 1 FT.

## Changes

- `config.yml`: `free_transfers: 1` pinned for **both** teams (dated comment).
- `jobs/deadline_plan.py`: a `free_transfers` value in config now **overrides**
  the API-recomputed count, with a log line (`free transfers pinned to 1 by
  config`). Remove the pin from config to return to automatic counting.

## Corrected GW2 plan (1 FT each, no hit)

| Team | OUT | IN | Captain |
|---|---|---|---|
| Minoux_69 | Thiago (BRE £8.0) | João Pedro (CHE £7.6) | Haaland (V Szoboszlai) |
| Minoux_41 | Gibbs-White (NFO £8.0, 75% flagged) | Szoboszlai (LIV £7.0) | Thiago (V Enzo) |

The second moves from the earlier 2-FT plan (Calafiori in for Gabriel;
Senesi in for Thiaw) are forgone — with 1 FT the planner's hit policy refused
to pay a −4 for them (thresholds: 6 pts Minoux_69, 4 pts Minoux_41).

## Verification

- Plan re-run `--force`: both teams 15/15 live API picks, FT pinned to 1,
  submission payloads valid (15 slots, captain in XI).
- Dashboard (`site/`) and `state/last_plan.json` regenerated with the 1-FT
  plan; the auto-submit job will therefore make exactly 1 free transfer per
  team before the GW2 deadline.