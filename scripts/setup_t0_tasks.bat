@echo off
echo QMT T0 Strategy - Task Setup
echo ============================
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Please run this script as Administrator
    echo Right-click this file and select "Run as Administrator"
    pause
    exit /b 1
)

cd /d "%~dp0\.."
set PROJECT_DIR=%CD%
echo Project directory: %PROJECT_DIR%
echo.

REM Ensure logs directory exists
if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"

REM Remove existing tasks
echo Removing existing tasks...
schtasks /delete /tn "QMT_T0_Daemon" /f >nul 2>&1
schtasks /delete /tn "QMT_T0_Sync_Position" /f >nul 2>&1
schtasks /delete /tn "QMT_T0_Daemon_Stop" /f >nul 2>&1

REM Create daemon start task
echo Creating daemon START task (09:25 AM daily)...
schtasks /create ^
    /tn "QMT_T0_Daemon" ^
    /tr "%PROJECT_DIR%\scripts\task_wrapper_t0_daemon.bat" ^
    /sc DAILY ^
    /st 09:25 ^
    /f ^
    /rl HIGHEST

if %errorLevel% == 0 (
    echo [OK] Daemon START task created successfully
) else (
    echo [ERROR] Daemon START task creation failed
    echo Error code: %errorLevel%
    pause
    exit /b 1
)

REM Create position sync task
echo Creating position SYNC task (03:00 PM daily)...
schtasks /create ^
    /tn "QMT_T0_Sync_Position" ^
    /tr "%PROJECT_DIR%\scripts\task_wrapper_t0_sync.bat" ^
    /sc DAILY ^
    /st 15:00 ^
    /f ^
    /rl HIGHEST

if %errorLevel% == 0 (
    echo [OK] Position SYNC task created successfully
) else (
    echo [ERROR] Position SYNC task creation failed
    pause
    exit /b 1
)

REM Create daemon stop task
echo Creating daemon STOP task (03:01 PM daily)...
schtasks /create ^
    /tn "QMT_T0_Daemon_Stop" ^
    /tr "%PROJECT_DIR%\scripts\stop_t0_daemon.bat" ^
    /sc DAILY ^
    /st 15:01 ^
    /f ^
    /rl HIGHEST

if %errorLevel% == 0 (
    echo [OK] Daemon STOP task created successfully
) else (
    echo [ERROR] Daemon STOP task creation failed
    pause
    exit /b 1
)

echo.
echo ============================================
echo Setup Complete!
echo ============================================
echo.
echo Created Tasks:
echo - QMT_T0_Daemon (09:25 AM daily)
echo - QMT_T0_Sync_Position (03:00 PM daily)
echo - QMT_T0_Daemon_Stop (03:01 PM daily)
echo.
echo To test the tasks manually:
echo   schtasks /run /tn "QMT_T0_Daemon"
echo   schtasks /run /tn "QMT_T0_Sync_Position"
echo.
echo To view logs:
echo   type "%PROJECT_DIR%\logs\task_execution_t0_daemon.log"
echo   type "%PROJECT_DIR%\logs\task_execution_t0_sync.log"
echo.
echo IMPORTANT:
echo 1. Make sure QMT client is running before 09:25 AM
echo 2. Check .env file configuration
echo 3. T0 daemon only evaluates during market hours
echo.
pause
