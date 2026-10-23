@echo off
rem Starts the ReelVault PC workspace, prints the localhost URL and the LAN IP:port, opens the browser.
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo [FAIL] .venv not found. Run scripts\setup.bat first.
  pause
  exit /b 1
)
echo Starting ReelVault ... (close this window or press Ctrl+C to stop)
".venv\Scripts\python.exe" launcher\run_server.py %*
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo.
  echo [FAIL] ReelVault stopped with exit code %RC%. See the log in %%LOCALAPPDATA%%\ReelVault\Data\logs\reelvault.log
  pause
)
exit /b %RC%
