# Step 8 — Dashboard upgrade: animated tabs, automation panel, live countdown

Date: 2026-08-27 (evening)

## What's new on https://aminou973.github.io/fpl-bot/

**New "Automation" panel (top of Overview)** — the bot's own parameters,
old and new, side by side:

- Live **deadline countdown** (d/h/m/s, ticking; pulses when under 24 h)
- Per team: free transfers, planned hit(s), **squad source badge**
  (green "live API" = planned on the real squad; red = fallback)
- **Submitter state** per team from the audit log: verified → will apply,
  lineup written, already in place
- Combined bank, and whether free transfers are **pinned by config** this
  season (the official app is the authority on banking)

**Better tabs** — the section nav is now an animated tab bar: the accent
underline slides between tabs as you scroll (scroll-spy) or click.

**Animations** (all disabled automatically under `prefers-reduced-motion`):

- cards and tiles **reveal on scroll** (fade + rise, staggered)
- stat tiles **count up** on first view
- captaincy bars **grow from zero**
- squad **cards stagger in** and lift on hover
- the transfer plan now uses **colored chips** — green IN, red OUT, grey roll

## Data plumbing

`jobs/deadline_plan.py` embeds a new `automation` block in
`site/bundle.json`: the submitter's audit log (state/auto_submit.json, latest
gameweek), the 36 h apply window, and whether FTs are pinned by config.
`fplbot/dashboard.py` renders it (Automation card + countdown + badges) and
keeps every existing section working unchanged.

Reduced motion is respected: a visitor who asked their OS for less motion
gets the same information with no animation.