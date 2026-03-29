@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0task_runner.ps1" -Mode meta-db-sync
