@echo off
rem Windows: checks Ollama and runs ReelVault's local AI self-test. Install Ollama from https://ollama.com/download/windows
setlocal
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\python.exe" (echo [FAIL] run scripts\setup.bat first & pause & exit /b 1)
".venv\Scripts\python.exe" tools\test_local_ai.py %*
pause
