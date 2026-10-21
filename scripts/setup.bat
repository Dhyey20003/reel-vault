@echo off
rem ===========================================================================
rem ReelVault setup (Windows 10/11, 64-bit). Idempotent: safe to run again.
rem  1. finds Python 3.12 or 3.13
rem  2. creates .venv
rem  3. installs pinned dependencies from wheelhouse\ (offline) or PyPI (fallback)
rem  4. initializes the SQLite database and data folders
rem ===========================================================================
setlocal
cd /d "%~dp0.."
call "scripts\_find_python.bat"
if not defined PYEXE (
  echo.
  echo [FAIL] Python 3.12 or 3.13 ^(64-bit^) was not found.
  echo        Install it from https://www.python.org/downloads/windows/ and tick "Add python.exe to PATH".
  echo        Then run setup.bat again.
  pause
  exit /b 1
)
echo [1/4] Using Python %PYVER%
if not exist ".venv\Scripts\python.exe" (
  echo [2/4] Creating the private Python environment in .venv ...
  %PYEXE% -m venv .venv || (echo [FAIL] Could not create .venv & pause & exit /b 1)
) else (
  echo [2/4] .venv already exists
)
set "WHEELS=wheelhouse\py%PYVER:.=%"
if exist "%WHEELS%\fastapi-*.whl" (
  echo [3/4] Installing components OFFLINE from %WHEELS% ...
  ".venv\Scripts\python.exe" -m pip install --no-index --find-links "%WHEELS%" -r requirements.txt
) else (
  echo [3/4] No wheelhouse for Python %PYVER%; installing from PyPI (internet needed) ...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
if errorlevel 1 (
  echo [FAIL] Dependency installation failed. See the messages above.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, segno, anthropic; print('      components OK')" || (echo [FAIL] Import check failed & pause & exit /b 1)
echo [4/4] Initializing database and data folders ...
".venv\Scripts\python.exe" -c "from reelvault.workspace import Workspace; from reelvault.config import default_data_dir; w=Workspace(default_data_dir()); print('      data folder:', w.paths.data_dir); print('      schema version:', w.db.current_version()); w.close()" || (echo [FAIL] Database initialization failed & pause & exit /b 1)
echo.
echo [OK] Setup finished.
echo      Next: double-click scripts\run_server.bat to start the workspace.
echo      Optional: install yt-dlp and ffmpeg for reference downloads (see README.md).
pause
exit /b 0
