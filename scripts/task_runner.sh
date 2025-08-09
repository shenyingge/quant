#!/bin/bash
# QMT Trading Service Task Runner for MINGW64 - Simple Version
# Only reads from .env, no modifications, no overrides

# Set up MINGW64 environment
export MSYSTEM=MINGW64
export PATH="/mingw64/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export PATH="/c/Users/shen/.local/bin:$PATH"
export LANG=zh_CN.UTF-8
export LC_ALL=zh_CN.UTF-8

# Change to project directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
PROJECT_DIR="$(pwd)"

# Load environment variables from .env file
ENV_FILE="$PROJECT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    # Source the helper script
    source "$SCRIPT_DIR/load_env.sh"
    load_env_file "$ENV_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Loaded environment variables from .env" >> logs/task_execution.log
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: .env file not found at $ENV_FILE" >> logs/task_execution.log
    exit 1
fi

# Create logs directory if not exists
mkdir -p logs

# Log file
LOG_FILE="logs/task_execution.log"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Start logging
echo "=========================================" >> "$LOG_FILE"
log_message "Task started (MINGW64 Simple Version)"
log_message "Working directory: $PROJECT_DIR"
log_message "Shell: $SHELL"
log_message "MSYSTEM: $MSYSTEM"
log_message "User: $(whoami)"

# Log environment variables from .env
log_message "Environment variables from .env:"
log_message "  REDIS_HOST: ${REDIS_HOST:-not set}"
log_message "  REDIS_PORT: ${REDIS_PORT:-not set}"
log_message "  QMT_SESSION_ID: ${QMT_SESSION_ID:-not set}"
log_message "  QMT_PATH: ${QMT_PATH:-not set}"
log_message "  QMT_ACCOUNT_ID: ${QMT_ACCOUNT_ID:-not set}"
log_message "  PYTHONPATH: ${PYTHONPATH:-not set}"

# Check if QMT is running
if ! tasklist 2>/dev/null | grep -q "XtMiniQmt.exe"; then
    log_message "ERROR: QMT is not running"
    log_message "Please start QMT client before running this task"
    exit 1
fi

log_message "QMT is running"

# Check Python availability
if command -v python >/dev/null 2>&1; then
    PYTHON_VERSION=$(python --version 2>&1)
    log_message "Python found: $PYTHON_VERSION"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    log_message "Python3 found: $PYTHON_VERSION"
else
    log_message "ERROR: Python not found in PATH"
    exit 1
fi

# Check uv availability
if ! command -v uv >/dev/null 2>&1; then
    log_message "ERROR: uv not found"
    exit 1
fi

UV_VERSION=$(uv --version 2>&1)
log_message "uv found: $UV_VERSION"

# Sync dependencies
log_message "Syncing dependencies with uv..."
uv sync >> "$LOG_FILE" 2>&1

# Run the trading service directly with .env configuration
log_message "Starting trading service with configuration from .env"
log_message "Using Session ID: $QMT_SESSION_ID"

# 设置Python编码环境变量
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

# 运行服务需要 run 参数
uv run python main.py run >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

log_message "Trading service exited with code: $EXIT_CODE"
log_message "Task ended"
echo "=========================================" >> "$LOG_FILE"

exit $EXIT_CODE