@echo off
echo QMT Strategy Engine - Task Setup
echo =================================
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
schtasks /delete /tn "QMT_Strategy_Engine" /f >nul 2>&1
schtasks /delete /tn "QMT_Strategy_Position_Sync" /f >nul 2>&1
schtasks /delete /tn "QMT_Strategy_Engine_Stop" /f >nul 2>&1
schtasks /delete /tn "QMT_T0_Daemon" /f >nul 2>&1
schtasks /delete /tn "QMT_T0_Sync_Position" /f >nul 2>&1
schtasks /delete /tn "QMT_T0_Daemon_Stop" /f >nul 2>&1

REM Create strategy engine start task
echo Creating strategy engine START task (09:25 AM daily)...
schtasks /create ^
    /tn "QMT_Strategy_Engine" ^
    /tr "%PROJECT_DIR%\scripts\task_wrapper_t0_daemon.bat" ^
    /sc DAILY ^
    /st 09:25 ^
    /f ^
    /rl HIGHEST

if %errorLevel% == 0 (
    echo [OK] Strategy engine START task created successfully
) else (
    echo [ERROR] Strategy engine START task creation failed
    echo Error code: %errorLevel%
    pause
    exit /b 1
)

REM Create position sync task
echo Creating strategy position SYNC task (03:00 PM daily)...
schtasks /create ^
    /tn "QMT_Strategy_Position_Sync" ^
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

REM Create strategy engine stop task
echo Creating strategy engine STOP task (03:01 PM daily)...
schtasks /create ^
    /tn "QMT_Strategy_Engine_Stop" ^
    /tr "%PROJECT_DIR%\scripts\stop_t0_daemon.bat" ^
    /sc DAILY ^
    /st 15:01 ^
    /f ^
    /rl HIGHEST

if %errorLevel% == 0 (
    echo [OK] Strategy engine STOP task created successfully
) else (
    echo [ERROR] Strategy engine STOP task creation failed
    pause
    exit /b 1
)

echo.
echo ============================================
echo Setup Complete!
echo ============================================
echo.
echo Created Tasks:
echo - QMT_Strategy_Engine (09:25 AM daily)
echo - QMT_Strategy_Position_Sync (03:00 PM daily)
echo - QMT_Strategy_Engine_Stop (03:01 PM daily)
echo.
echo To test the tasks manually:
echo   schtasks /run /tn "QMT_Strategy_Engine"
echo   schtasks /run /tn "QMT_Strategy_Position_Sync"
echo.
echo To view logs:
echo   type "%PROJECT_DIR%\logs\task_execution_t0_daemon.log"
echo   type "%PROJECT_DIR%\logs\task_execution_t0_sync.log"
echo.
echo IMPORTANT:
echo 1. Make sure QMT client is running before 09:25 AM
echo 2. Check .env file configuration
echo 3. Strategy engine only evaluates during market hours
echo.
pause
