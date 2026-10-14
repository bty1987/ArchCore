@echo off
rem ============================================================
rem ArchCore one-shot installer (P0 #8).
rem Fixes the manual steps in deploy/install-windows.md:
rem   venv -> deps -> configs -> migrate -> web build.
rem Existing config files are NEVER overwritten.
rem After install: run start-server.bat, login admin / <bootstrap
rem password printed at step 4>, first login forces a password change.
rem ============================================================
setlocal
set "ROOT=%~dp0"

echo [1/7] checking Python 3.10+ ...
python --version >nul 2>&1
if errorlevel 1 (
    echo [install] Python not found in PATH. Install Python 3.10+ first.
    pause
    exit /b 1
)
python --version

echo [2/7] creating virtualenv (.venv) ...
if not exist "%ROOT%.venv\Scripts\python.exe" (
    python -m venv "%ROOT%.venv"
) else (
    echo [install] .venv exists, skipped.
)

echo [3/7] installing server + collector (editable) ...
"%ROOT%.venv\Scripts\python.exe" -m pip install -q -e "%ROOT%server" -e "%ROOT%collector"
if errorlevel 1 (
    echo [install] pip install failed - check network / python version.
    pause
    exit /b 1
)

echo [4/7] generating configs (existing files kept) ...
set /p "COLLECTOR_WXID=  input collector WeChat wxid (e.g. wxid_xxxxx): "
if "%COLLECTOR_WXID%"=="" (
    echo [install] wxid is required.
    pause
    exit /b 1
)
"%ROOT%.venv\Scripts\python.exe" scripts\install_config.py --wxid "%COLLECTOR_WXID%"

echo [5/7] migrating database ...
cd /d "%ROOT%server"
set "ARCHCORE_DB_URL=sqlite:///%ROOT%data/archcore.db"
"%ROOT%.venv\Scripts\python.exe" -m alembic upgrade head
cd /d "%ROOT%"

echo [6/7] building web console ...
where node >nul 2>&1
if errorlevel 1 (
    echo [install] node not found - skip web build (install Node 18+ and run: cd web ^&^& npm install ^&^& npm run build^)
) else (
    cd /d "%ROOT%web"
    call npm install --silent
    call npm run build
    cd /d "%ROOT%"
)

echo [7/7] done.
echo   - start server : start-server.bat  (then open http://127.0.0.1:8000)
echo   - start collector : .venv\Scripts\archcore-collector.exe  (config: collector\config.yaml)
echo   - first login  : admin / bootstrap password from step 4 - password change is forced.
echo   - demo mode (synthetic data only): run-demo.bat
pause
