@echo off
rem Upgrades an existing ReelVault v1 installation to v2 (Windows). Stop ReelVault first. Reuses .venv.
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (echo [FAIL] .venv not found; run scripts\setup.bat for a fresh install & pause & exit /b 1)
echo [1/2] Backup + migrate
".venv\Scripts\python.exe" tools\upgrade_db.py migrate %*
if errorlevel 1 (echo [FAIL] migration failed; nothing else was changed & pause & exit /b 1)
echo [2/2] Done. v2 adds no new Python packages. Start ReelVault again with scripts\run_server.bat
echo       Rollback: ".venv\Scripts\python.exe" tools\upgrade_db.py rollback --backup "%%LOCALAPPDATA%%\ReelVault\Data\backups\pre-v2-....db"
pause
