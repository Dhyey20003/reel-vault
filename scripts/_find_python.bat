@echo off
rem Shared helper: locates Python 3.12 or 3.13 (64-bit). Sets PYEXE and PYVER. Called by the other scripts.
set "PYEXE="
set "PYVER="
for %%V in (3.13 3.12) do (
  if not defined PYEXE (
    py -%%V -c "import sys" >nul 2>&1 && (set "PYEXE=py -%%V" & set "PYVER=%%V")
  )
)
if not defined PYEXE (
  python -c "import sys; assert sys.version_info[:2] in ((3,12),(3,13))" >nul 2>&1 && (
    set "PYEXE=python"
    for /f %%i in ('python -c "import sys;print(f'{sys.version_info[0]}.{sys.version_info[1]}')"') do set "PYVER=%%i"
  )
)
