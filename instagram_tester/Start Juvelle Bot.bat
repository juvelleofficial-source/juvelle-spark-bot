@echo off
title Juvelle AI Bot Launcher
cd /d "c:\Users\sahil\.gemini\antigravity-ide\scratch\Gemini Spark Chat Bot"

echo Starting Juvelle AI Bot in background...

:: Check if port 8000 is already active
netstat -ano | findstr :8000 | findstr LISTENING >nul
if %errorlevel% equ 0 (
    echo Backend server is already running on port 8000.
) else (
    echo Launching FastAPI Neural Backend Server with Live Hot-Reload...
    start /B python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload >nul 2>&1
)

:: Check if cloudflared is running
tasklist /fi "imagename eq cloudflared.exe" | findstr /i "cloudflared.exe" >nul
if %errorlevel% equ 0 (
    echo Cloudflare tunnel is already running.
) else (
    if exist "cloudflared.exe" (
        echo Launching Cloudflare Tunnel...
        start /B .\cloudflared.exe tunnel --url http://127.0.0.1:8000 >nul 2>&1
    )
)

:: Short wait before launching browser
ping 127.0.0.1 -n 2 >nul
start http://127.0.0.1:8000/tester/

exit
