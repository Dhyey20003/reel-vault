@echo off
rem Convenience: runs setup.bat when needed, then run_server.bat.
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" goto :setup
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, segno, anthropic" >nul 2>&1
if errorlevel 1 goto :setup
goto :run
:setup
echo Running setup first ...
call "scripts\setup.bat"
if errorlevel 1 exit /b 1
:run
call "scripts\run_server.bat" %*
