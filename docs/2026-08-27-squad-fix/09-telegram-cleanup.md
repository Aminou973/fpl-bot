# Step 9 — Telegram cleanup: three tiers, red alerts only ring

Date: 2026-08-27 (evening)

## The noise problem

The bot was sending everything to one chat with sound on: a long plan brief
three times a day (even unchanged), **every** price move in the game each
hour, matchday scores every ten minutes. Hundreds of notifications a day,
none distinguishable.

## The fix: three tiers

| Tier | Sound | Chat secret | Contains |
|---|---|---|---|
| 🔴 `alert` | **rings** | `TELEGRAM_CHAT_ALERT` (fallback: `TELEGRAM_CHAT_ID`) | plan (only when it changed) · deadline warning · lineup applied / failed · weekly results · 🎯 chip windows |
| ⚽ `live` | silent | `TELEGRAM_CHAT_LIVE` (optional) | matchday scores, change-only |
| 💰 `watch` | silent | `TELEGRAM_CHAT_WATCH` (optional) | price moves of **your** players · team news |

Rate/selection limits that came with it:

- **plan brief**: compact one-block-per-team format, sent **only when the
  plan actually changed** (out/in/captain/vice/hits) and only inside the
  deadline window — the identical reruns are printed to the log, not sent.
- **watch**: price moves filtered to **owned players only**, max 12 lines;
  the "price pressure" block was removed; the deadline warning now fires
  **once per gameweek** (at ≤26 h) instead of twice.
- **live**: one tight line per team plus the top four scorers, silent.
- **submit**: new alerts — ✅ when a lineup is written, 🚨 when a run fails.
  These are the ones worth hearing.
- **chip windows** (added after the tiers went in): when the chip calendar
  says the best window for a team's Wildcard / Free Hit / Bench Boost /
  Triple Captain is this week — or next week (head-up) — the plan job rings
  once per team+chip+gameweek. Chips are never auto-played (irreversible),
  so the alert tells you to play it in the app before the deadline. Dedupe
  state lives in `state/chip_alerts.json`.

## Optional: fully separate chats

Create a Telegram channel/group for the noisy tiers (e.g. "FPL Live"), add
the bot as an administrator, get its chat id (forward a message to
@userinfobot or use the bot API `getUpdates`), then:

```bash
gh secret set TELEGRAM_CHAT_LIVE  --body "-100xxxxxxxxxx"
gh secret set TELEGRAM_CHAT_WATCH --body "-100xxxxxxxxxx"
```

Mute that chat on the phone; the alert chat stays loud. Without these
secrets, everything lands in the one existing chat — but only the alert
tier makes a sound.

## Files

- `fplbot/notify.py` — tier routing (`send(text, kind="alert|live|watch")`)
- `jobs/deadline_plan.py` — compact brief, change-only sending, 📊 results
- `jobs/watch.py` — owned-only prices, one-shot deadline warning
- `jobs/live_scores.py` — tighter live blocks
- `jobs/submit_transfers.py` — applied/failed alerts (red tier)