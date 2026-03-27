@echo off
echo QMT Trading Engine - Task Setup (Simplified)
echo =============================================
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
schtasks /delete /tn "QMT_Trading_Engine" /f >nul 2>&1
schtasks /delete /tn "QMT_Trading_Engine_Stop" /f >nul 2>&1
schtasks /delete /tn "QMT_Trading_Service" /f >nul 2>&1
schtasks /delete /tn "QMT_Trading_Service_Stop" /f >nul 2>&1

REM Create START task
echo Creating START task (8:40 AM daily)...
schtasks /create ^
    /tn "QMT_Trading_Engine" ^
    /tr "%PROJECT_DIR%\scripts\task_wrapper_trading.bat" ^
    /sc DAILY ^
    /st 08:40 ^
    /f ^
    /rl HIGHEST

if %errorLevel% == 0 (
    echo [OK] START task created successfully
) else (
    echo [ERROR] START task creation failed
    echo Error code: %errorLevel%
    pause
    exit /b 1
)

REM Create STOP task
echo Creating STOP task (9:00 PM daily)...
schtasks /create ^
    /tn "QMT_Trading_Engine_Stop" ^
    /tr "%PROJECT_DIR%\scripts\stop_trading_service.bat" ^
    /sc DAILY ^
    /st 21:00 ^
    /f ^
    /rl HIGHEST

if %errorLevel% == 0 (
    echo [OK] STOP task created successfully
) else (
    echo [ERROR] STOP task creation failed
    pause
    exit /b 1
)

echo.
echo ============================================
echo Setup Complete!
echo ============================================
echo.
echo Created Tasks:
echo - QMT_Trading_Engine (8:40 AM daily)
echo - QMT_Trading_Engine_Stop (9:00 PM daily)
echo.
echo To test the task manually:
echo   schtasks /run /tn "QMT_Trading_Engine"
echo.
echo To view logs:
echo   type "%PROJECT_DIR%\logs\task_execution_trading.log"
echo.
echo To manage tasks:
echo   Open Task Scheduler: taskschd.msc
echo   Or use command line:
echo     Enable:  schtasks /change /tn "QMT_Trading_Engine" /enable
echo     Disable: schtasks /change /tn "QMT_Trading_Engine" /disable
echo     Delete:  schtasks /delete /tn "QMT_Trading_Engine" /f
echo.
echo IMPORTANT:
echo 1. Trading engine starts after the QMT 08:30 auto re-initialization window
echo 2. Check .env file configuration
echo 3. Non-trading days: Service will exit automatically
echo    To force run: Set TRADING_DAY_CHECK_ENABLED=false in .env
echo.
pause
