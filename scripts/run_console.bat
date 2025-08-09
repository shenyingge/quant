@echo off
echo Starting QMT Trading Service (Console Mode)...
echo.

REM Switch to project directory
cd /d "%~dp0\.."

echo Current directory: %CD%
echo Current time: %DATE% %TIME%
echo.

echo Checking configuration...
if not exist ".env" (
    echo WARNING: .env configuration file not found, using defaults
    echo RECOMMENDATION: Copy .env.example to .env and configure it
    echo.
)

echo Starting trading service (Console Mode)...
echo Press Ctrl+C to stop the service
echo.

REM Run service directly (non-Windows service mode)
REM Try uv first, fallback to direct python if uv not available
uv --version >nul 2>&1
if %errorLevel% == 0 (
    echo Using uv to run the service...
    uv run python main.py run
) else (
    echo uv not found in PATH, using direct python execution...
    REM Check if python is available
    python --version >nul 2>&1
    if %errorLevel% == 0 (
        python main.py run
    ) else (
        echo ERROR: Neither uv nor python found in PATH
        echo Please ensure Python is installed and accessible
        echo Or install uv: pip install uv
        pause
        exit /b 1
    )
)

echo.
echo Trading service exited
pause