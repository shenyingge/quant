@echo off
echo QMT 分钟行情导出 - 任务配置
echo ===========================
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
echo 项目目录: %PROJECT_DIR%
echo.

REM Ensure logs directory exists
if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"

REM Remove existing task
echo 正在删除已有任务...
schtasks /delete /tn "QMT_Minute_History_Daily" /f >nul 2>&1

REM Create daily export task
echo 正在创建每日下午 03:10 的分钟行情任务...
schtasks /create ^
    /tn "QMT_Minute_History_Daily" ^
    /tr "%PROJECT_DIR%\scripts\task_wrapper_minute_history.bat" ^
    /sc DAILY ^
    /st 15:10 ^
    /f ^
    /rl HIGHEST

if %errorLevel% == 0 (
    echo [OK] 每日分钟行情任务创建成功
) else (
    echo [ERROR] 每日分钟行情任务创建失败
    echo 错误码: %errorLevel%
    pause
    exit /b 1
)

echo.
echo ============================================
echo 配置完成
echo ============================================
echo.
echo 已创建任务:
echo - QMT_Minute_History_Daily（每天下午 03:10）
echo.
echo 手动测试任务:
echo   schtasks /run /tn "QMT_Minute_History_Daily"
echo.
echo 查看日志:
echo   type "%PROJECT_DIR%\logs\task_execution_minute_history.log"
echo.
echo 注意:
echo 1. 请确保 03:10 前 QMT 客户端已启动
echo 2. 请检查 .env 中的 Meta DB 和 NAS 配置
echo 3. 非交易日任务会自动跳过
echo.
pause
