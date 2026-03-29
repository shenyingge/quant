@echo off
echo SQLite -> Meta DB 同步任务配置
echo ==============================
echo.

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

if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"

echo 正在删除已有任务...
schtasks /delete /tn "QMT_Meta_DB_Sync" /f >nul 2>&1

echo 正在创建每日下午 03:10 的 SQLite -> Meta DB 同步任务...
schtasks /create ^
    /tn "QMT_Meta_DB_Sync" ^
    /tr "%PROJECT_DIR%\scripts\task_wrapper_meta_db_sync.bat" ^
    /sc DAILY ^
    /st 15:10 ^
    /f ^
    /rl HIGHEST

if %errorLevel% == 0 (
    echo [OK] Meta DB 同步任务创建成功
) else (
    echo [ERROR] Meta DB 同步任务创建失败
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
echo - QMT_Meta_DB_Sync（每天下午 03:10）
echo.
echo 手动测试任务:
echo   schtasks /run /tn "QMT_Meta_DB_Sync"
echo.
echo 查看日志:
echo   type "%PROJECT_DIR%\logs\task_execution_meta_db_sync.log"
echo.
echo 注意:
echo 1. 该任务不依赖 QMT 是否启动
echo 2. 请确保 .env 中的 Meta DB 配置正确
echo 3. 该任务会用 SQLite 全量覆盖 Meta DB 中 trading schema 的交易表
echo.
pause
