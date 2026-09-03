@echo off
REM One-time FPL login for account 1 (Minoux_69) + secret storage + verification.
REM Double-click from anywhere; keep this window open and follow the prompts.
chcp 65001 >nul
cd /d "%~dp0"

where gh >nul 2>nul
if errorlevel 1 (
    echo [!] The GitHub CLI ^(gh^) is not installed or not on PATH.
    echo     Install it from https://cli.github.com/ and run this file again.
    pause
    exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
    echo [!] Python is not installed or not on PATH.
    pause
    exit /b 1
)

echo ============================================
echo  FPL login: account 1 - Minoux_69
echo ============================================
echo  1. A browser window opens on the FPL sign-in page.
echo  2. Sign in with the Minoux_69 account.
echo  3. Copy the FULL address-bar URL after sign-in and paste it below.
echo.
python jobs\fpl_login.py --account 1 --set-secret
if errorlevel 1 goto :fail

echo.
echo ============================================
echo  Verification: submit DRY RUN (read-only)
echo ============================================
gh workflow run submit
timeout /t 20 /nobreak >nul
for /f "delims=" %%i in ('gh run list --workflow^=submit --limit 1 --json databaseId --jq ".[0].databaseId"') do set RUNID=%%i
if defined RUNID (
    echo Watching dry run %RUNID% ^(read-only, submits nothing^)...
    gh run watch %RUNID% --exit-status
    if errorlevel 1 goto :fail
) else (
    echo Could not read the run id - check https://github.com/Aminou973/fpl-bot/actions
)

echo.
echo ALL DONE.
echo  - The dry run must show "authenticated (token 1)" and Minoux_69 no
echo    longer skipped - then the hourly schedule takes over automatically
echo    and submits the lineup and chips before each deadline.
pause
exit /b 0

:fail
echo.
echo [!] Something failed - fix it above and run this file again.
pause
exit /b 1