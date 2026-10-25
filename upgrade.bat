@echo off
rem ============================================================
rem ArchCore upgrade script (gap-analysis #13).
rem Run on the deployment host, from the repo root.
rem Golden rule: BACKUP FIRST, then update. Safe to re-run.
rem Online mode: git pull. Offline mode: overwrite repo files
rem from a release zip first, then run this script.
rem ============================================================
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [upgrade] .venv not found. Run install.bat first.
    pause & exit /b 1
)

echo [1/6] current version ...
curl -s http://127.0.0.1:8000/api/v1/version
echo.

echo [2/6] pre-upgrade backup (mandatory, timestamped by backup.py) ...
"%PY%" "%ROOT%deploy\backup.py" --db "%ROOT%data\archcore.db" --media "%ROOT%data\media" --config "%ROOT%collector\config.yaml" --plain "%ROOT%data\wechat4_plain" --out "%ROOT%backups\pre-upgrade"
if errorlevel 1 (
    echo [upgrade] BACKUP FAILED - aborting. Fix backup issue and retry.
    pause & exit /b 1
)

echo [3/6] update code (git pull) ...
where git >nul 2>&1
if exist "%ROOT%.git" (
    git -C "%ROOT%" pull --ff-only
    if errorlevel 1 (
        echo [upgrade] git pull failed. Offline mode: unzip release over the repo, then re-run.
        pause & exit /b 1
    )
) else (
    echo [upgrade] no .git - assume offline mode ^(files already updated^).
)

echo [4/6] reinstall deps ...
"%PY%" -m pip install -q -e "%ROOT%server" -e "%ROOT%collector"
if errorlevel 1 ( echo [upgrade] pip failed & pause & exit /b 1 )

echo [5/6] database migration ...
cd /d "%ROOT%server"
set "ARCHCORE_DB_URL=sqlite:///%ROOT%data/archcore.db"
"%PY%" -m alembic upgrade head
if errorlevel 1 (
    echo [upgrade] MIGRATION FAILED - database untouched by rollback plan:
    echo   restore from backups\pre-upgrade per local-deploy-guide section 11.
    pause & exit /b 1
)
cd /d "%ROOT%"

echo [6/6] web build (optional) ...
where node >nul 2>&1
if errorlevel 1 (
    echo [upgrade] node not found - skip web build.
) else (
    cd /d "%ROOT%web" && call npm install --silent && call npm run build
    cd /d "%ROOT%"
)

echo.
echo [upgrade] DONE. Restart the server ^(close start-server.bat window and re-run it^),
echo then verify: curl http://127.0.0.1:8000/api/v1/version
echo Rollback if needed: restore backups\pre-upgrade per local-deploy-guide section 11.
pause
