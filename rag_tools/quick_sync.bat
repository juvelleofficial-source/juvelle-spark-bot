@echo off
REM =========================================================================
REM Juvelle RAG Quick Sync 1-Click Batch Script
REM =========================================================================
echo ===============================================================
echo Starting Juvelle RAG Quick Sync...
echo ===============================================================
cd /d "%~dp0\.."
python rag_tools\quick_sync.py %*
echo.
pause
