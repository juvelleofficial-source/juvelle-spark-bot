@echo off
title Stop Juvelle Bot
echo Stopping Juvelle AI Bot and Cloudflare Tunnel...

:: Find and kill process listening on port 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo Stopping backend server PID %%a...
    taskkill /f /pid %%a >nul 2>&1
)

:: Stop cloudflared
taskkill /f /im cloudflared.exe >nul 2>&1

echo All Juvelle Bot services stopped successfully.
ping 127.0.0.1 -n 2 >nul
exit
