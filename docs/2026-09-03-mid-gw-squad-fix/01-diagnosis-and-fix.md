# GW3 2026-09-03: the planner could not see mid-gameweek transfers

## What happened

Timeline (UTC):

| time | event |
| --- | --- |
| 06:46 | plan built on the GW2 **published** picks, plans Pickford + Tarkowski + Gibbs-White in for Truffert + B.Fernandes + Roefs (2 hits) |
| 11:43 | submit job applies that plan — squad is genuinely transformed |
| 11:46 / 12:05 | plan job runs again, still reads the **GW2 published picks** (public picks only publish at a deadline) and plans on the pre-11:43 squad: it proposes to *re-buy Gibbs-White* and sell Semenyo/Thiaw |
| 16:40 | account 1 (Minoux_69) refresh token rejected (HTTP 400 invalid_grant) |
| 16:41 | submit job acts on the 12:05 plan: ownership filter skips ghosts, but one leg survives — **Senesi in for Thiaw, a real −4 hit** — then the lineup write is rejected (`Element 426/529/61 not in the player's picks`: the plan's payload still named the three players sold at 11:43). Minoux_69 is skipped with it, so its triple captain was never submitted |

Total cost of the confusion: −12 pts in hits for GW3 (all four transfers were
planned moves, but executed in two overlapping batches from stale plans).

## Root cause

`api.squad_state` reads **published** picks, and FPL publishes a gameweek's
picks only at its deadline. Any transfer made mid-gameweek — the bot's own
submit job included — is invisible to the planner for the rest of the week.
Two plan jobs ran after the submit and both planned on the pre-transfer squad;
the submit job's ownership filter caught most ghost legs but not all.

## Fix (same day)

1. **Live snapshot** — `jobs/submit_transfers.py` writes an authenticated
   my-team snapshot to `state/live_squad.json` on every run (dry runs and
   refusals included), keyed by entry id: picks, selling prices, bank,
   `fetched_at`.
2. **Planner prefers the snapshot** — `jobs/deadline_plan.py` uses the
   snapshot when it is fresh (`pipeline.snapshot_fresh`, ≤26h old, 15 picks)
   and otherwise falls back to published picks as before.
3. **Submitter refuses stale plans** — `stale_plan_note` refuses to act when
   the plan's base squad differs from the live my-team squad; the plan must
   be regenerated first.
4. **Failures are contained** — per-team transfer/lineup failures are
   recorded in `state/auto_submit.json` (`transfers-failed` /
   `lineup-failed`) and alerted, and the remaining teams are still
   processed instead of the run crashing mid-loop.

## Residual risks

- Manual transfers made in the FPL app are only picked up at the next
  hourly submit read (≤1h), never by the planner directly — the plan job
  deliberately does not refresh tokens (rotation without the Secrets-write
  PAT would kill the account).
- If an account dies, its snapshot ages out (26h) and the planner falls
  back to published picks — correct as long as no mid-GW moves happened,
  and the submit guard blocks bad execution regardless.