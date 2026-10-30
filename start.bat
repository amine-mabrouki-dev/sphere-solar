@echo off
setlocal enabledelayedexpansion
title Sphere Solar - Launcher

echo.
echo  ============================================
echo   Sphere Solar ^| Launching Services
echo  ============================================
echo.

:: ── Auto-setup if first run ───────────────────────────────────────────────────

if not exist "backend\venv" (
    echo [!] Backend not set up — running setup.bat first...
    echo.
    call setup.bat
    if errorlevel 1 exit /b 1
)

if not exist "mobile\.env" (
    echo [!] mobile\.env missing — running setup.bat first...
    echo.
    call setup.bat
    if errorlevel 1 exit /b 1
)

if not exist "mobile\node_modules" (
    echo [!] node_modules missing — running setup.bat first...
    echo.
    call setup.bat
    if errorlevel 1 exit /b 1
)

:: ── Detect local IP for info display ─────────────────────────────────────────

set LOCAL_IP=
for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /i "IPv4"') do (
    set CANDIDATE=%%A
    set CANDIDATE=!CANDIDATE: =!
    if not "!CANDIDATE!"=="127.0.0.1" (
        if "!LOCAL_IP!"=="" set LOCAL_IP=!CANDIDATE!
    )
)
if "!LOCAL_IP!"=="" set LOCAL_IP=localhost
:: ── Load backend environment from backend\.env (ignore comments/blank)
if exist "backend\.env" (
    for /f "usebackq delims=" %%A in ("backend\.env") do (
        set "LINE=%%A"
        setlocal enabledelayedexpansion
        if not "!LINE!"=="" (
            if not "!LINE:~0,1!"=="#" (
                for /f "tokens=1* delims==" %%K in ("!LINE!") do (
                    endlocal
                    set "%%K=%%L"
                )
            ) else (
                endlocal
            )
        ) else (
            endlocal
        )
    )
)

:: ── Start backend ─────────────────────────────────────────────────────────────

echo [1/2] Starting Backend (FastAPI on port 8000) ...
start "Sphere Solar - Backend" cmd /k ^
    "title Sphere Solar - Backend && cd /d "%~dp0backend" && call venv\Scripts\activate.bat && echo. && echo  Backend running at http://localhost:8000 && echo  API docs at   http://localhost:8000/docs && echo  Press Ctrl+C to stop && echo. && python run.py"

:: Small pause so the backend can bind before Expo starts
timeout /t 3 /nobreak >nul

:: ── Start mobile (Expo) ───────────────────────────────────────────────────────

echo [2/2] Starting Mobile App (Expo) ...
start "Sphere Solar - Mobile" cmd /k ^
    "title Sphere Solar - Mobile && cd /d "%~dp0mobile" && echo. && echo  Expo starting... scan the QR code with Expo Go && echo  Press Ctrl+C to stop && echo. && npx expo start"

:: ── Summary ───────────────────────────────────────────────────────────────────

echo.
echo  ============================================
echo   All services are starting in new windows.
echo.
echo   Backend API  : http://localhost:8000
echo   API Docs     : http://localhost:8000/docs
echo   Your LAN IP  : http://%LOCAL_IP%:8000
echo.
echo   Physical device? Edit mobile\.env and set:
echo   EXPO_PUBLIC_API_URL=http://%LOCAL_IP%:8000
echo.
echo   Close the two opened windows to stop.
echo  ============================================
echo.
pause
