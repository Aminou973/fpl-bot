#!/usr/bin/env bash
# fpl-bot installer (macOS / Linux).
#
# Run from inside the fpl-bot folder:
#     bash setup.sh
#
# Creates the GitHub repo, pushes the code, sets the two secrets, turns on Pages
# and the right Actions permissions, and kicks off the first run. Your Telegram
# token is read locally and handed straight to GitHub - never written to a file.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

need() {
  command -v "$1" >/dev/null 2>&1 || { printf '\n%s is not installed.\n  %s\n\n' "$1" "$2"; exit 1; }
}

printf '\n=== fpl-bot setup ===\n\n'
need git "Install from https://git-scm.com/downloads"
need gh  "Install GitHub CLI: brew install gh   (or see https://cli.github.com)"

# ------------------------------------------------------------------ github --
if ! gh auth status >/dev/null 2>&1; then
  echo "Signing you in to GitHub (a browser window will open)..."
  gh auth login --web --git-protocol https --scopes repo,workflow
fi
USER_LOGIN=$(gh api user --jq .login)
echo "GitHub account: $USER_LOGIN"

read -rp "Repository name [fpl-bot]: " REPO
REPO=${REPO:-fpl-bot}

# --------------------------------------------------------------- entry ids --
cat <<'TXT'

Your FPL entry ids. Open each team's points page; the URL looks like
  https://fantasy.premierleague.com/entry/1234567/event/1   ->  1234567

TXT
read -rp "entry id for Minoux_69 (main team): " ID69
read -rp "entry id for Minoux_41 (risk team): " ID41

python3 - "$ID69" "$ID41" <<'PY'
import re, sys
id69, id41 = sys.argv[1], sys.argv[2]
s = open("config.yml").read()
s = re.sub(r"(Minoux_69:\s*\n\s*entry_id:\s*)\d+", r"\g<1>" + id69, s)
s = re.sub(r"(Minoux_41:\s*\n\s*entry_id:\s*)\d+", r"\g<1>" + id41, s)
open("config.yml", "w").write(s)
PY
echo "config.yml updated."

# ---------------------------------------------------------------- telegram --
cat <<'TXT'

Telegram. In the app, message @BotFather, send /newbot and follow the prompts.
He gives you a token that looks like 8123456789:AAH...

TXT
read -rsp "Paste the bot token: " TOKEN; echo
echo
echo "Now open a chat with your new bot and send it any message."
read -rp "Press Enter once you've done that: " _

CHAT=""
for _ in 1 2 3 4 5 6; do
  CHAT=$(curl -sf --max-time 20 "https://api.telegram.org/bot${TOKEN}/getUpdates" \
        | python3 -c 'import json,sys; r=json.load(sys.stdin).get("result",[]); print(r[-1]["message"]["chat"]["id"] if r else "")' 2>/dev/null || true)
  [ -n "$CHAT" ] && break
  sleep 3
done
if [ -z "$CHAT" ]; then
  echo "Couldn't read the chat id automatically."
  read -rp "Open https://api.telegram.org/bot<token>/getUpdates and paste the chat id: " CHAT
else
  echo "Chat id detected: $CHAT"
fi

# --------------------------------------------------------------- push repo --
[ -d .git ] || { git init -q; git branch -M main; }
git add -A
git commit -q -m "fpl-bot" 2>/dev/null || true

if gh repo view "$USER_LOGIN/$REPO" >/dev/null 2>&1; then
  echo; echo "Repository already exists, pushing..."
  git remote remove origin 2>/dev/null || true
  git remote add origin "https://github.com/$USER_LOGIN/$REPO.git"
  git push -u origin main --force
else
  echo; echo "Creating public repository $USER_LOGIN/$REPO ..."
  gh repo create "$REPO" --public --source=. --remote=origin --push
fi

# ------------------------------------------------------------ configure it --
echo; echo "Configuring the repository..."
gh secret set TELEGRAM_BOT_TOKEN --repo "$USER_LOGIN/$REPO" --body "$TOKEN" >/dev/null
gh secret set TELEGRAM_CHAT_ID  --repo "$USER_LOGIN/$REPO" --body "$CHAT"  >/dev/null
unset TOKEN
echo "  secrets set"

gh api -X PUT "repos/$USER_LOGIN/$REPO/actions/permissions/workflow" \
  -f default_workflow_permissions=write \
  -F can_approve_pull_request_reviews=false >/dev/null
echo "  Actions can write to the repo"

gh api -X POST "repos/$USER_LOGIN/$REPO/pages" -f build_type=workflow >/dev/null 2>&1 \
  || gh api -X PUT "repos/$USER_LOGIN/$REPO/pages" -f build_type=workflow >/dev/null 2>&1 || true
echo "  Pages set to build from Actions"

# ------------------------------------------------------------- first run ----
SITE="https://$USER_LOGIN.github.io/$REPO/"
python3 - "$SITE" <<'PY'
import sys
s = open("config.yml").read().replace('site_url: ""', f'site_url: "{sys.argv[1]}"')
open("config.yml", "w").write(s)
PY
git add config.yml
git commit -q -m "config: entry ids and site url"
git push -q

echo; echo "Starting the first run..."
gh workflow run plan.yml --repo "$USER_LOGIN/$REPO" -f force=true

cat <<TXT

=== done ===
Repo      https://github.com/$USER_LOGIN/$REPO
Actions   https://github.com/$USER_LOGIN/$REPO/actions
Dashboard $SITE   (live a few minutes after the first run finishes)

You should get a Telegram message within about three minutes.
If nothing arrives, open the Actions link and read the failing step.

TXT
