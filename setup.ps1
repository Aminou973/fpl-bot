<#
  fpl-bot installer (Windows / PowerShell).

  Run it from anywhere:

      powershell -ExecutionPolicy Bypass -File .\setup.ps1

  Creates the GitHub repo, pushes the code, sets the two secrets, turns on Pages
  and the right Actions permissions, and starts the first run. Your Telegram
  token is read locally and handed straight to GitHub - never written to a file
  and never echoed to the screen.
#>

# git and gh both write ordinary progress messages to stderr, which PowerShell
# would treat as fatal under "Stop". Exit codes are checked explicitly instead.
$ErrorActionPreference = "Continue"
$ProgressPreference    = "SilentlyContinue"
Set-Location -Path $PSScriptRoot

function Fail($msg) {
  Write-Host ""
  Write-Host $msg -ForegroundColor Red
  Write-Host ""
  exit 1
}

function Ok($msg)   { Write-Host "  $msg" -ForegroundColor Green }
function Step($msg) { Write-Host "`n$msg" -ForegroundColor Cyan }

function Need($cmd, $hint) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    Fail "$cmd is not installed.`n  $hint"
  }
}

Write-Host "`n=== fpl-bot setup ===`n" -ForegroundColor Cyan

if (-not (Test-Path "config.yml")) {
  Fail "config.yml is not next to this script. Extract the whole zip and run setup.ps1 from inside it."
}

Need git "Install from https://git-scm.com/download/win, then reopen PowerShell."
Need gh  "Run: winget install --id GitHub.cli   then reopen PowerShell."

# ---------------------------------------------------------------- 1. GitHub --
gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
  Step "Signing you in to GitHub. A browser window will open - approve it there."
  gh auth login --web --git-protocol https --scopes repo,workflow
  if ($LASTEXITCODE -ne 0) { Fail "GitHub sign-in did not complete. Run 'gh auth login' by hand, then rerun this script." }
}
$user = (gh api user --jq .login 2>&1)
if ($LASTEXITCODE -ne 0 -or -not $user) { Fail "Could not read your GitHub account. Try 'gh auth login' again." }
Write-Host "GitHub account: $user" -ForegroundColor Green

$repo = Read-Host "Repository name [fpl-bot]"
if ([string]::IsNullOrWhiteSpace($repo)) { $repo = "fpl-bot" }

# ------------------------------------------------------------ 2. entry ids --
Write-Host "`nYour FPL entry ids. Open each team's points page; the URL looks like"
Write-Host "  https://fantasy.premierleague.com/entry/1234567/event/1   ->  1234567`n"
$id69 = (Read-Host "entry id for Minoux_69 (your main team)").Trim()
$id41 = (Read-Host "entry id for Minoux_41 (your risk team)").Trim()
if ($id69 -notmatch '^\d+$' -or $id41 -notmatch '^\d+$') { Fail "Entry ids must be numbers only." }

$cfg = Get-Content config.yml -Raw
$cfg = [regex]::Replace($cfg, '(Minoux_69:\s*\r?\n\s*entry_id:\s*)\d+', "`${1}$id69")
$cfg = [regex]::Replace($cfg, '(Minoux_41:\s*\r?\n\s*entry_id:\s*)\d+', "`${1}$id41")
Set-Content config.yml $cfg -NoNewline
Ok "config.yml updated"

# ------------------------------------------------------------- 3. telegram --
Write-Host "`nTelegram. In the app, message @BotFather, send /newbot and follow the"
Write-Host "prompts. He replies with a token like 8123456789:AAH...`n"
$sec = Read-Host "Paste the bot token" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$tok  = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
if (-not $tok) { Fail "No token entered." }

Step "Now open a chat with your new bot and send it any message."
Read-Host "Press Enter once you've done that" | Out-Null

$chat = $null
for ($i = 0; $i -lt 6 -and -not $chat; $i++) {
  try {
    $r = Invoke-RestMethod "https://api.telegram.org/bot$tok/getUpdates" -TimeoutSec 20
    $chat = ($r.result | Select-Object -Last 1).message.chat.id
  } catch { }
  if (-not $chat) { Start-Sleep 3 }
}
if ($chat) {
  Ok "chat id detected: $chat"
} else {
  Write-Host "Couldn't read the chat id automatically." -ForegroundColor Yellow
  $chat = (Read-Host "Open https://api.telegram.org/bot<token>/getUpdates and paste the chat id").Trim()
  if (-not $chat) { Fail "No chat id given." }
}

# ------------------------------------------------------------ 4. push repo --
Step "Preparing the repository..."
if (-not (Test-Path ".git")) {
  git init -q 2>&1 | Out-Null
  git branch -M main 2>&1 | Out-Null
}
git add -A 2>&1 | Out-Null
git commit -q -m "fpl-bot" 2>&1 | Out-Null      # no-op if nothing changed

gh repo view "$user/$repo" 2>&1 | Out-Null
$exists = ($LASTEXITCODE -eq 0)

if ($exists) {
  Step "Repository $user/$repo already exists - pushing to it."
  git remote remove origin 2>&1 | Out-Null
  git remote add origin "https://github.com/$user/$repo.git" 2>&1 | Out-Null
  git push -u origin main --force 2>&1 | Out-Host
} else {
  Step "Creating public repository $user/$repo ..."
  gh repo create $repo --public --source=. --remote=origin --push 2>&1 | Out-Host
}
if ($LASTEXITCODE -ne 0) { Fail "Push failed. Check the message above, then rerun this script." }

# --------------------------------------------------------------- 5. config --
Step "Configuring the repository..."

gh secret set TELEGRAM_BOT_TOKEN --repo "$user/$repo" --body $tok 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "Could not set TELEGRAM_BOT_TOKEN." }
gh secret set TELEGRAM_CHAT_ID --repo "$user/$repo" --body "$chat" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "Could not set TELEGRAM_CHAT_ID." }
$tok = $null
Ok "secrets set"

gh api -X PUT "repos/$user/$repo/actions/permissions/workflow" `
  -f default_workflow_permissions=write `
  -F can_approve_pull_request_reviews=false 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Ok "Actions can write to the repo" }
else { Write-Host "  could not set workflow permissions - do it by hand at Settings > Actions > General" -ForegroundColor Yellow }

gh api -X POST "repos/$user/$repo/pages" -f build_type=workflow 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
  gh api -X PUT "repos/$user/$repo/pages" -f build_type=workflow 2>&1 | Out-Null
}
if ($LASTEXITCODE -eq 0) { Ok "Pages will build from Actions" }
else { Write-Host "  could not enable Pages - do it by hand at Settings > Pages > Source: GitHub Actions" -ForegroundColor Yellow }

# ------------------------------------------------------------ 6. first run --
$site = "https://$user.github.io/$repo/"
$cfg = Get-Content config.yml -Raw
$cfg = $cfg -replace 'site_url:\s*""', ("site_url: `"$site`"")
Set-Content config.yml $cfg -NoNewline
git add config.yml 2>&1 | Out-Null
git commit -q -m "config: entry ids and site url" 2>&1 | Out-Null
git push -q 2>&1 | Out-Null

Step "Starting the first run..."
gh workflow run plan.yml --repo "$user/$repo" -f force=true 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) {
  Write-Host "  could not start it from here - open the Actions tab and run 'plan' manually" -ForegroundColor Yellow
}

Write-Host "`n=== done ===" -ForegroundColor Green
Write-Host "Repo      https://github.com/$user/$repo"
Write-Host "Actions   https://github.com/$user/$repo/actions"
Write-Host "Dashboard $site"
Write-Host "          (live a few minutes after the first run finishes)"
Write-Host "`nA Telegram message should arrive within about three minutes."
Write-Host "If it doesn't, open the Actions link and read the failing step.`n"