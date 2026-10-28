@echo off
title Cafy Agent Launcher
cd /d "%~dp0"

echo ================================================================
echo   Cafy Agent - Starting Backend + Frontend
echo ================================================================

:: Kill anything on port 8000 first
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

:: Start Backend (FastAPI on port 8000)
echo [1/2] Starting Backend on http://127.0.0.1:8000 ...
start "Cafy Backend" cmd /k "cd /d "%~dp0" && "%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" run.py"

:: Wait for backend to be ready
timeout /t 4 /nobreak >nul

:: Start Frontend (Vite dev server on port 5173)
echo [2/2] Starting Frontend on http://127.0.0.1:5173 ...
start "Cafy Frontend" cmd /k "cd /d "%~dp0\frontend" && npm run dev"

echo.
echo ================================================================
echo   Backend  : http://127.0.0.1:8000   (API + static fallback)
echo   Frontend : http://127.0.0.1:5173   (Vite dev server)
echo ================================================================
echo   Open http://127.0.0.1:5173 in your browser
echo ================================================================
