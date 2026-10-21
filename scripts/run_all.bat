@echo off
rem Convenience: runs setup.bat when needed, then run_server.bat.
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo .venv missing; running setup first ...
  call "scripts\setup.bat"
  if errorlevel 1 exit /b 1
) else (
  ".venv\Scripts\python.exe" -c "import fastapi, uvicorn, segno, anthropic" >nul 2>&1 || (
    echo Dependencies incomplete; running setup first ...
    call "scripts\setup.bat"
    if errorlevel 1 exit /b 1
  )
)
call "scripts\run_server.bat" %*
