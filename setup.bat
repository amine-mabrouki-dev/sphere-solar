@echo off
setlocal enabledelayedexpansion
title Sphere Solar - Setup

echo.
echo  ============================================
echo   Sphere Solar ^| First-Time Setup
echo  ============================================
echo.

:: ── 1. Prerequisite checks ───────────────────────────────────────────────────

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo         Download and install Python 3.11+ from https://www.python.org/downloads/
    echo         Make sure to check "Add Python to PATH" during installation.
    echo.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version') do echo [OK] %%v found

node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found.
    echo         Download and install Node.js 18+ from https://nodejs.org/
    echo.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('node --version') do echo [OK] Node.js %%v found

npm --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found. Reinstall Node.js from https://nodejs.org/
    pause & exit /b 1
)
echo [OK] npm found

echo.

:: ── 2. Python backend setup ───────────────────────────────────────────────────

echo --- Backend (Python / FastAPI) ---

if not exist "backend\venv" (
    echo Creating Python virtual environment...
    :: Prefer Python 3.12 — the app segfaults on the 3.15 beta, and the default
    :: "python" on this machine may be that beta. Fall back to plain python.
    py -3.12 -m venv backend\venv 2>nul || python -m venv backend\venv
    if errorlevel 1 (
        echo [ERROR] Could not create virtual environment.
        pause & exit /b 1
    )
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment already exists
)

echo Installing Python dependencies...
call backend\venv\Scripts\activate.bat
pip install -r backend\requirements.txt -q
if errorlevel 1 (
    echo [ERROR] pip install failed. Check your internet connection.
    pause & exit /b 1
)
echo [OK] Python dependencies installed
call deactivate

echo.

:: ── 3. Mobile app setup ───────────────────────────────────────────────────────

echo --- Mobile app (Expo / React Native) ---

:: Detect the machine's local IP (first non-loopback IPv4)
set LOCAL_IP=
for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /i "IPv4"') do (
    set CANDIDATE=%%A
    set CANDIDATE=!CANDIDATE: =!
    if not "!CANDIDATE!"=="127.0.0.1" (
        if "!LOCAL_IP!"=="" set LOCAL_IP=!CANDIDATE!
    )
)
if "!LOCAL_IP!"=="" set LOCAL_IP=localhost

if not exist "mobile\.env" (
    echo Creating mobile\.env ...
    (
        echo # Backend API URL
        echo # - Emulator ^(Android^):  http://10.0.2.2:8000
        echo # - Emulator ^(iOS sim^):  http://localhost:8000
        echo # - Physical device:      http://!LOCAL_IP!:8000
        echo EXPO_PUBLIC_API_URL=http://localhost:8000
    ) > mobile\.env
    echo [OK] mobile\.env created
    echo     NOTE: for a real phone edit mobile\.env and use: http://!LOCAL_IP!:8000
) else (
    echo [OK] mobile\.env already exists
)

if not exist "mobile\node_modules" (
    echo Installing Node.js dependencies ^(this may take a minute^)...
    pushd mobile
    npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        popd
        pause & exit /b 1
    )
    popd
    echo [OK] Node.js dependencies installed
) else (
    echo [OK] node_modules already present ^(run "npm install" inside mobile\ to update^)
)

echo.
echo  ============================================
echo   Setup complete!
echo   Run  start.bat  to launch everything.
echo  ============================================
echo.
pause
