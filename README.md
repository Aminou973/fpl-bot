# fpl-bot — Minoux_69 &amp; Minoux_41

An FPL engine that runs itself. GitHub Actions does the scheduling, the official
FPL API supplies the data, Telegram carries the alerts, and GitHub Pages hosts a
dashboard that is always current. No server, no cost.

```
watch.yml   hourly    price moves, injury news, deadline countdown  -> Telegram
plan.yml    3x daily  full transfer + captain + chip plan            -> Telegram + Pages
submit.yml  hourly    applies the plan to your FPL squad before each deadline (auto-transfers)
live.yml    10 min    live points and provisional bonus during matches -> Telegram
```

The transfer plan is always built on the **live API squad** for both entries —
if the API picks ever cannot be read, the run warns loudly and the submit job
refuses to act, so a wrong squad can never be planned on or submitted. To arm
the auto-transfers, set the FPL account credentials as repo secrets (the two
squads live on two accounts, so four secrets — see
`docs/2026-08-27-squad-fix/04-auto-transfers.md`):

```bash
gh secret set FPL_EMAIL      --body "first-account-email"
gh secret set FPL_PASSWORD   --body "first-account-password"
gh secret set FPL_EMAIL_2    --body "second-account-email"
gh secret set FPL_PASSWORD_2 --body "second-account-password"
```

---

## Setup — one command

From inside this folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1     # Windows
```
```bash
bash setup.sh                                            # macOS / Linux
```

You need `git` and the GitHub CLI (`winget install --id GitHub.cli`, or
`brew install gh`). The script signs you in to GitHub in a browser, asks for your
two entry ids and your Telegram bot token, detects your chat id automatically,
then creates the repo, pushes, sets the secrets, enables Pages and Actions
permissions, and starts the first run. Your token is read locally and passed
straight to GitHub — it is never written to a file.

The manual route is below if you would rather do it by hand.

---

## Setup by hand

**1. Create the repo.** Make it **public**: public repositories get unlimited
Actions minutes and free Pages. Nothing here is sensitive — your team IDs are
already visible on the FPL site.

```bash
git init && git add . && git commit -m "fpl-bot"
git branch -M main
git remote add origin https://github.com/<you>/fpl-bot.git
git push -u origin main
```

**2. Make a Telegram bot.** Message [@BotFather](https://t.me/BotFather), send
`/newbot`, follow the prompts, and copy the token it gives you. Then message your
new bot once (say anything) and open:

```
https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
```

Your chat id is the number at `result[0].message.chat.id`.

**3. Add the secrets.** Repo → Settings → Secrets and variables → Actions → New
repository secret:

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | the token from BotFather |
| `TELEGRAM_CHAT_ID` | the chat id from the step above |

**4. Find your entry ids.** Open each team's points page on the FPL site. The URL
is `https://fantasy.premierleague.com/entry/1234567/event/1` — `1234567` is the
entry id. Put both into `config.yml`.

**5. Turn on Pages.** Settings → Pages → Source: **GitHub Actions**. After the
first `plan` run your dashboard lives at
`https://<you>.github.io/fpl-bot/`. Paste that URL into `site_url` in `config.yml`
so it appears at the bottom of every Telegram brief.

**6. Allow Actions to push.** Settings → Actions → General → Workflow permissions
→ **Read and write permissions**. The jobs commit the state files they use to
detect changes.

**7. Run it.** Actions → `plan` → Run workflow (leave *force* ticked). You should
get a Telegram message within a couple of minutes.

---

## Configuration

Everything lives in `config.yml`. The two teams are already set up:

```yaml
Minoux_69:            # main - template safe
  hit_threshold: 6    # only take a -4 if the plan gains more than 6 points
  ownership_bonus: 0.04
  lock: [["Haaland", "MCI"]]

Minoux_41:            # risk - full differential
  hit_threshold: 4
  objective: ceiling
  max_captain_ownership: 25
  ban: [["Haaland", "MCI"]]
  min_differentials: {count: 9, max_ownership: 8}
```

`horizon` sets how many gameweeks the planner looks ahead (5 is a good default).
`plan_window_hours` stops the planner burning cycles when the deadline is days
away.

The `squad:` lists are only a fallback. Once `entry_id` is filled in, the bot
reads your real squad, bank and free transfers from the API on every run, so it
always plans from where you actually are.

---

## What the planner actually decides

`fplbot/planner.py` is a single integer program over the whole horizon. In one
solve it chooses, for every gameweek: who leaves, who arrives, whether to spend a
free transfer or bank it, whether a −4 is worth paying, the starting XI, and the
captain. Free transfers accumulate to five exactly as the rules allow, and the
unlimited pre-season window is handled as a special case that does not carry over.

Hits are decided by solving twice — once allowing them, once forbidding them — and
taking the hit only when it beats the team's threshold. That is why the brief can
tell you *"a hit was considered and rejected: it gained 1.4 points against a
6-point threshold"* rather than silently doing one or the other.

Team briefs — locked players, barred players, the differential quota — are applied
to the **end** of the horizon, not to every week. A squad that breaks its own brief
is the problem the plan is meant to solve, so the planner is allowed to take a
route through it. When no route exists inside the horizon, the brief says so and
tells you that is what a wildcard is for.

Chips are evaluated on top of the finished plan rather than inside it: for each
week you get the value of a triple captain and a bench boost, and the dashboard
maps all 38 gameweeks so you can see the windows coming.

---

## Running it locally

```bash
pip install -r requirements.txt
python jobs/deadline_plan.py --offline --force --no-notify   # CSV snapshots, no network
python jobs/deadline_plan.py --force                          # live API, sends Telegram
python jobs/watch.py
python jobs/live_scores.py
open site/index.html
```

`--offline` runs the whole engine against the CSV snapshots in `data/`, which is
handy for testing model changes without hammering the API.

---

## Layout

```
config.yml              teams, thresholds, horizon
fplbot/api.py           official FPL API client
fplbot/model.py         expected-points and ceiling engine
fplbot/optimize.py      single-window squad optimiser
fplbot/planner.py       multi-week transfer + free-transfer + hit planner
fplbot/dashboard.py     self-contained HTML dashboard
fplbot/notify.py        Telegram
fplbot/pipeline.py      glue
jobs/                   the three scheduled entry points
data/2025-26/           last season's gameweek history (model priors)
data/2026-27/           offline snapshot, refreshed from the API in normal use
state/                  change-detection snapshots, committed by the bot
site/                   generated dashboard, published to Pages
```

---

## Notes and limits

- The model is built from 2025/26 evidence until this season has real gameweeks;
  it starts folding them in automatically from about gameweek 3 and sharpens from
  there. The opening weeks are the least reliable part of the year.
- Provisional bonus during live matches is computed from BPS the same way FPL
  does it, but it can move until a match is finalised.
- Free transfers are inferred from your transfer history. If the number ever looks
  wrong, set it under the team in `config.yml` and the bot will use that instead.
- Scheduled Actions runs are best-effort and can be delayed by a few minutes at
  busy times. Nothing here needs second-level precision except `live`, which
  simply catches up on the next run.
