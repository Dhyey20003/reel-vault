@echo off
rem Shared helper: locates Python 3.12 or 3.13 (64-bit). Sets PYEXE and PYVER. Called by the other scripts.
set "PYEXE="
set "PYVER="
for %%V in (3.13 3.12) do (
  if not defined PYEXE (
    py -%%V -c "import sys" >nul 2>&1 && (set "PYEXE=py -%%V" & set "PYVER=%%V")
  )
)
if defined PYEXE goto :done
python -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,12),(3,13)) else 1)" >nul 2>&1
if errorlevel 1 goto :done
set "PYEXE=python"
for /f "tokens=2 delims= " %%i in ('python --version 2^>^&1') do set "PYFULL=%%i"
for /f "tokens=1,2 delims=." %%a in ("%PYFULL%") do set "PYVER=%%a.%%b"
:done
