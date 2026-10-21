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
if not defined PYEXE goto :nopython

echo [1/4] Using Python %PYVER%
if exist ".venv\Scripts\python.exe" goto :venv_ok
echo [2/4] Creating the private Python environment in .venv ...
%PYEXE% -m venv .venv
if errorlevel 1 goto :venv_fail
goto :venv_done
:venv_ok
echo [2/4] .venv already exists
:venv_done

set "WHEELS=wheelhouse\py%PYVER:.=%"
if not exist "%WHEELS%\fastapi-*.whl" goto :pypi
echo [3/4] Installing components OFFLINE from %WHEELS% ...
".venv\Scripts\python.exe" -m pip install --no-index --find-links "%WHEELS%" -r requirements.txt
if errorlevel 1 goto :install_fail
goto :installed
:pypi
echo [3/4] No wheelhouse for Python %PYVER%. Installing from PyPI, internet needed ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :install_fail
:installed
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, segno, anthropic; print('      components OK')"
if errorlevel 1 goto :import_fail

echo [4/4] Initializing database and data folders ...
".venv\Scripts\python.exe" -c "from reelvault.workspace import Workspace; from reelvault.config import default_data_dir; w=Workspace(default_data_dir()); print('      data folder:', w.paths.data_dir); print('      schema version:', w.db.current_version()); w.close()"
if errorlevel 1 goto :db_fail
echo.
echo [OK] Setup finished.
echo      Next: double-click scripts\run_server.bat to start the workspace.
echo      Optional: install yt-dlp and ffmpeg for reference downloads, see README.md.
pause
exit /b 0

:nopython
echo.
echo [FAIL] Python 3.12 or 3.13 was not found.
echo        Install it from https://www.python.org/downloads/windows/ and tick "Add python.exe to PATH".
echo        Then run setup.bat again.
pause
exit /b 1
:venv_fail
echo [FAIL] Could not create .venv. See the messages above.
pause
exit /b 1
:install_fail
echo [FAIL] Dependency installation failed. See the messages above.
pause
exit /b 1
:import_fail
echo [FAIL] Import check failed. Delete the .venv folder and run setup.bat again.
pause
exit /b 1
:db_fail
echo [FAIL] Database initialization failed. See the messages above.
pause
exit /b 1
