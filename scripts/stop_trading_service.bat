@echo off
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_python_by_command.ps1" -Pattern "main.py run" -LogFile "%CD%\logs\trading_stop_task.log"
