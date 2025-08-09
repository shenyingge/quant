@echo off
echo QMT Trading Service - Task Setup (Simplified)
echo ==============================================
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

REM Detect MSYS2 installation
set MSYS2_PATH=
if exist "C:\msys64" (
    set MSYS2_PATH=C:\msys64
) else if exist "C:\msys2" (
    set MSYS2_PATH=C:\msys2
) else (
    echo ERROR: MSYS2 not found in C:\msys64 or C:\msys2
    echo Please install MSYS2 from: https://www.msys2.org/
    pause
    exit /b 1
)

echo Found MSYS2 at: %MSYS2_PATH%
echo.

REM Ensure logs directory exists
if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"

REM Create a batch file wrapper for the task
echo Creating task wrapper...
(
echo @echo off
echo cd /d "%PROJECT_DIR%"
echo "%MSYS2_PATH%\usr\bin\bash.exe" -l -c "cd /c/Users/shen/quant && ./scripts/task_runner.sh"
) > "%PROJECT_DIR%\scripts\task_wrapper.bat"

echo Task wrapper created: %PROJECT_DIR%\scripts\task_wrapper.bat
echo.

REM Remove existing tasks
echo Removing existing tasks...
schtasks /delete /tn "QMT_Trading_Service" /f >nul 2>&1
schtasks /delete /tn "QMT_Trading_Service_Stop" /f >nul 2>&1

REM Create START task
echo Creating START task (8:00 AM daily)...
schtasks /create ^
    /tn "QMT_Trading_Service" ^
    /tr "%PROJECT_DIR%\scripts\task_wrapper.bat" ^
    /sc DAILY ^
    /st 08:00 ^
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
    /tn "QMT_Trading_Service_Stop" ^
    /tr "taskkill /f /im python.exe" ^
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
echo - QMT_Trading_Service (8:00 AM daily)
echo - QMT_Trading_Service_Stop (9:00 PM daily)
echo.
echo To test the task manually:
echo   schtasks /run /tn "QMT_Trading_Service"
echo.
echo To view logs:
echo   type "%PROJECT_DIR%\logs\task_execution.log"
echo.
echo To manage tasks:
echo   Open Task Scheduler: taskschd.msc
echo   Or use command line:
echo     Enable:  schtasks /change /tn "QMT_Trading_Service" /enable
echo     Disable: schtasks /change /tn "QMT_Trading_Service" /disable
echo     Delete:  schtasks /delete /tn "QMT_Trading_Service" /f
echo.
echo IMPORTANT:
echo 1. Make sure QMT client is running before 8:00 AM
echo 2. Check .env file configuration
echo 3. Non-trading days: Service will exit automatically
echo    To force run: Set TRADING_DAY_CHECK_ENABLED=false in .env
echo.
pause