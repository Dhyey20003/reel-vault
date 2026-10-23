@echo off
rem Builds dist\ReelVault.exe (single-file, console) with PyInstaller.
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" goto :novenv
for /f "tokens=2 delims= " %%i in ('".venv\Scripts\python.exe" --version 2^>^&1') do set "PYFULL=%%i"
for /f "tokens=1,2 delims=." %%a in ("%PYFULL%") do set "PYVER=%%a.%%b"
set "WHEELS=wheelhouse\py%PYVER:.=%"
echo [1/3] Installing build tools ...
if not exist "%WHEELS%\pyinstaller-*.whl" goto :pypi
".venv\Scripts\python.exe" -m pip install --no-index --find-links "%WHEELS%" -r requirements-build.txt
if errorlevel 1 goto :toolfail
goto :build
:pypi
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto :toolfail
:build
echo [2/3] Building with PyInstaller, this takes a minute ...
".venv\Scripts\python.exe" -m PyInstaller reelvault.spec --noconfirm --clean
if errorlevel 1 goto :buildfail
echo [3/3] Verifying ...
if not exist "dist\ReelVault.exe" goto :noexe
"dist\ReelVault.exe" --help >nul 2>&1
if errorlevel 1 (echo [WARN] The exe did not respond to --help; try running it manually.) else (echo       exe responds OK)
echo.
echo [OK] Built dist\ReelVault.exe
echo      Run it directly, no Python needed. Data stays in %%LOCALAPPDATA%%\ReelVault\Data.
echo      Note: Windows SmartScreen may warn on first run because the exe is unsigned.
pause
exit /b 0

:novenv
echo [FAIL] .venv not found. Run scripts\setup.bat first.
pause
exit /b 1
:toolfail
echo [FAIL] Could not install PyInstaller.
pause
exit /b 1
:buildfail
echo [FAIL] PyInstaller failed. See the messages above.
pause
exit /b 1
:noexe
echo [FAIL] dist\ReelVault.exe was not produced.
pause
exit /b 1
