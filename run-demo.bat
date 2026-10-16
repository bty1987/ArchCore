@echo off
rem ============================================================
rem ArchCore Demo Mode (P0 #7) - synthetic data ONLY, fully
rem isolated from real data (data/demo/). Safe on any machine.
rem Login: admin / demo-arch-2026
rem ============================================================
setlocal
set "ROOT=%~dp0"
set "ROOT=%ROOT:\=/%"
set "PY=%ROOT%.venv/Scripts/python.exe"
set "COLLECTOR=%ROOT%.venv/Scripts/archcore-collector.exe"

if not exist "%PY%" (
    echo [demo] .venv not found. Run install.bat first.
    pause
    exit /b 1
)

rem ---- demo-isolated environment (never touches data/archcore.db) ----
set "ARCHCORE_DB_URL=sqlite:///%ROOT%data/demo/archcore.db"
set "ARCHCORE_MEDIA_DIR=%ROOT%data/demo/media"
set "ARCHCORE_JWT_SECRET=demo-only-secret-3f8a1c"
set "ARCHCORE_COLLECTOR_TOKEN=demo-collector-token"
set "ARCHCORE_COLLECTOR_WXID=wxid_demo_collector"
set "ARCHCORE_ADMIN_BOOTSTRAP_PASSWORD=demo-arch-2026"

echo [1/6] generating synthetic fixture data (120 days)...
"%PY%" scripts/gen-fixtures.py --out "%ROOT%data/demo/fixture_wechat.db" --days 120 >nul

echo [2/6] writing demo collector config...
"%PY%" scripts/demo_setup.py init

echo [3/6] migrating demo database...
cd /d "%ROOT%server"
"%PY%" -m alembic upgrade head
cd /d "%ROOT%"

echo [4/6] starting server (new window)...
start "ArchCore-Demo-Server" cmd /c ""%PY%" -m uvicorn archcore_server.main:app --host 127.0.0.1 --port 8000"

set /a TRIES=0
:wait_health
set /a TRIES+=1
if %TRIES% GTR 30 (
    echo [demo] server health check timeout - see ArchCore-Demo-Server window.
    pause
    exit /b 1
)
timeout /t 2 /nobreak >nul
curl -s -o nul http://127.0.0.1:8000/api/v1/health
if errorlevel 1 goto wait_health

echo [5/6] importing fixture data via collector (--full)...
"%COLLECTOR%" -c "%ROOT%data/demo/collector_config.yaml" --full

echo [6/6] seeding demo customers, rules and alert scenarios...
"%PY%" scripts\demo_setup.py seed

start "" http://127.0.0.1:8000
echo.
echo [demo] READY - login: admin / demo-arch-2026
echo [demo] data lives in data\demo\ only; close the ArchCore-Demo-Server window to stop.
pause
