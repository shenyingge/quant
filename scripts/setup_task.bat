@echo off
echo QMT Trading Service - Final Task Setup
echo =======================================
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
echo Current directory: %CD%
echo.

REM Get the current directory path (convert backslashes to forward slashes for MSYS2)
set PROJECT_DIR=%CD%
set UNIX_PATH=%PROJECT_DIR:\=/%

REM Detect MSYS2 installation
set MSYS2_BASH=
if exist "C:\msys64\usr\bin\bash.exe" (
    set MSYS2_BASH=C:\msys64\usr\bin\bash.exe
) else if exist "C:\msys2\usr\bin\bash.exe" (
    set MSYS2_BASH=C:\msys2\usr\bin\bash.exe
) else (
    echo ERROR: MSYS2 bash not found
    echo Please install MSYS2 from: https://www.msys2.org/
    pause
    exit /b 1
)

echo Found MSYS2 at: %MSYS2_BASH%
echo Unix path: %UNIX_PATH%
echo.

REM Ensure logs directory exists
if not exist "logs" mkdir logs

REM Remove any existing tasks
echo Cleaning up existing tasks...
schtasks /delete /tn "QMT Trading Service" /f >nul 2>&1
schtasks /delete /tn "QMT Trading Service Stop" /f >nul 2>&1
echo.

echo Creating optimized scheduled tasks...
echo.

REM Create START task with proper MSYS2 environment
echo Creating START task...
schtasks /create ^
    /tn "QMT Trading Service" ^
    /tr "\"%MSYS2_BASH%\" --login -c \"cd '%UNIX_PATH%' && ./scripts/run_console.sh > logs/task_output.log 2>&1\"" ^
    /sc DAILY ^
    /st 08:00 ^
    /f ^
    /rl HIGHEST

if %errorLevel% == 0 (
    echo ✓ START task created successfully
) else (
    echo ✗ START task creation failed
    pause
    exit /b 1
)

REM Create STOP task
echo Creating STOP task...
schtasks /create ^
    /tn "QMT Trading Service Stop" ^
    /tr "taskkill /f /im python.exe" ^
    /sc DAILY ^
    /st 21:00 ^
    /f ^
    /rl HIGHEST

if %errorLevel% == 0 (
    echo ✓ STOP task created successfully
) else (
    echo ✗ STOP task creation failed
    pause
    exit /b 1
)

echo.
echo ============================================
echo Setup Complete!
echo ============================================
echo.

echo Created Tasks:
echo • QMT Trading Service (8:00 AM daily)
echo • QMT Trading Service Stop (9:00 PM daily)
echo.

echo Testing:
echo • Manual test: schtasks /run /tn "QMT Trading Service"
echo • Check logs: logs\task_output.log
echo • Service logs: logs\trading_service.log
echo.

echo Important Notes:
echo 1. Make sure QMT client is running before 8:00 AM
echo 2. Configure .env file with correct QMT Session ID
echo 3. Monitor logs for any connection issues
echo 4. The task runs with HIGHEST privileges
echo.

echo Task Management:
echo • View tasks: taskschd.msc
echo • Enable: schtasks /change /tn "QMT Trading Service" /enable
echo • Disable: schtasks /change /tn "QMT Trading Service" /disable
echo.

pause