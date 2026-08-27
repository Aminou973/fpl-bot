@echo off
REM One-time FPL login for both squads + secret storage + verification run.
REM Run from the repo root (double-click works too): arm_fpl_login.bat
chcp 65001 >nul
cd /d "%~dp0"

where gh >nul 2>nul
if errorlevel 1 (
    echo [!] The GitHub CLI ^(gh^) is not installed or not on PATH.
    echo     Install it from https://cli.github.com/ and run this file again.
    pause
    exit /b 1
)

echo ============================================
echo  Step 1/3 - FPL login: account 1 (Minoux_69)
echo ============================================
python jobs\fpl_login.py --account 1 --set-secret
if errorlevel 1 goto :fail

echo.
echo ============================================
echo  Step 2/3 - FPL login: account 2 (Minoux_41)
echo ============================================
python jobs\fpl_login.py --account 2 --set-secret
if errorlevel 1 goto :fail

echo.
echo ============================================
echo  Step 3/3 - Trigger submit DRY RUN
echo ============================================
gh workflow run submit
if errorlevel 1 goto :fail
timeout /t 15 /nobreak >nul
for /f "delims=" %%i in ('gh run list --workflow=submit --limit 1 --json databaseId --jq ".[0].databaseId"') do set RUNID=%%i
if defined RUNID (
    echo Watching dry run %RUNID% ^(read-only, submits nothing^)...
    gh run watch %RUNID% --exit-status
    if errorlevel 1 goto :fail
) else (
    echo Could not read the run id - check https://github.com/Aminou973/fpl-bot/actions
)

echo.
echo ALL DONE.
echo  - Both refresh tokens are stored as repo secrets.
echo  - The dry run above must show "authenticated (token 1/2)" and end with
echo    "dry run for GW2" - then the hourly schedule takes over automatically.
echo  - The old FPL_EMAIL / FPL_PASSWORD secrets can now be deleted:
echo      gh secret delete FPL_EMAIL
echo      gh secret delete FPL_PASSWORD
echo      gh secret delete FPL_EMAIL_2
echo      gh secret delete FPL_PASSWORD_2
pause
exit /b 0

:fail
echo.
echo [!] Something failed - see the messages above and fix, then run again.
pause
exit /b 1