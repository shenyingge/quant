@echo off
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_python_by_command.ps1" -Pattern "main.py t0-daemon" -LogFile "%CD%\logs\t0_stop_task.log"
