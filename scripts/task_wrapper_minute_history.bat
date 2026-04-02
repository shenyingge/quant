@echo off
cd /d "%~dp0\.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" main.py export-minute-daily
) else (
  python main.py export-minute-daily
)
