@echo off
echo Creating QMT Trading Service Scheduled Tasks
echo ============================================
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

REM Get the current directory path
set PROJECT_DIR=%CD%

echo Creating scheduled tasks...
echo.

REM Create START task - runs every day at 8:00 AM using MINGW64 bash
echo Creating QMT Trading Service START task...
powershell -Command "schtasks /create /tn 'QMT Trading Service' /tr 'C:\msys64\usr\bin\bash.exe -l -c \"cd /c/Users/shen/quant && ./scripts/run_console.sh\"' /sc DAILY /st 08:00 /f /rl HIGHEST"

if %errorLevel% == 0 (
    echo ✓ START task created successfully
) else (
    echo ✗ Failed to create START task
    pause
    exit /b 1
)

REM Create STOP task - runs every day at 9:00 PM
echo Creating QMT Trading Service STOP task...
powershell -Command "schtasks /create /tn 'QMT Trading Service Stop' /tr 'taskkill /f /im python.exe /fi \"WINDOWTITLE eq QMT Trading Service*\"' /sc DAILY /st 21:00 /f /rl HIGHEST"

if %errorLevel% == 0 (
    echo ✓ STOP task created successfully
) else (
    echo ✗ Failed to create STOP task
    pause
    exit /b 1
)

echo.
echo ============================================
echo Scheduled Tasks Created Successfully!
echo ============================================
echo.

echo Task Summary:
echo • START Task: "QMT Trading Service"
echo   - Runs daily at 8:00 AM
echo   - Executes: run_console.sh via MINGW64 bash
echo.
echo • STOP Task: "QMT Trading Service Stop"  
echo   - Runs daily at 9:00 PM
echo   - Kills running trading service processes
echo.

echo Next Steps:
echo 1. Test the task manually:
echo    schtasks /run /tn "QMT Trading Service"
echo.
echo 2. Monitor task execution:
echo    Open Task Scheduler (taskschd.msc)
echo    Check: Task Scheduler Library ^> QMT Trading Service
echo.
echo 3. View logs:
echo    %PROJECT_DIR%\logs\trading_service.log
echo.

echo Management Commands:
echo • Enable tasks:  schtasks /change /tn "QMT Trading Service" /enable
echo • Disable tasks: schtasks /change /tn "QMT Trading Service" /disable  
echo • Delete tasks:  schtasks /delete /tn "QMT Trading Service" /f
echo.

pause