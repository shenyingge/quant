# QMT自动交易服务

基于QMT（迅投量化交易系统）的自动交易服务，通过Redis监听交易信号并自动执行订单。

## 功能特性

- 🔄 **实时监听**: 监听Redis频道接收交易信号
- 📈 **自动交易**: 接收信号后自动执行买卖操作
- 💾 **数据记录**: 将交易信号和订单信息存储到本地数据库
- 📱 **飞书通知**: 实时推送交易状态到飞书群聊
- ⏰ **计划任务**: 支持通过Windows任务计划程序自动运行
- 📊 **订单监控**: 实时监控订单状态和成交情况
- 🔧 **自动备份**: 每日自动备份交易数据
- 📅 **交易日历**: 使用akshare获取准确的交易日历，非交易日自动跳过
- ♻️ **T+0信号引擎**: 支持单次运行、守护轮询、仓位同步与纯文件回测
- 📤 **收盘导出**: 支持每日持仓与成交记录导出并上传到远端主机

## 系统要求

- Python 3.11+
- Windows 10/11 或 Windows Server 2016+
- QMT客户端（国金证券版本）
- Redis服务器
- MSYS2/MINGW64环境（推荐）

## 项目结构

```
quant/
├── main.py                # 主程序入口
├── pyproject.toml         # 项目配置和依赖（使用uv管理）
├── .env                   # 环境配置文件
├── src/                   # 核心源代码
│   ├── config.py          # 配置管理
│   ├── database.py        # 数据库模型（SQLAlchemy）
│   ├── logger_config.py   # 统一日志配置
│   ├── redis_listener.py  # Redis信号监听器
│   ├── redis_client.py    # Redis客户端管理
│   ├── trader.py          # QMT交易执行器
│   ├── notifications.py   # 飞书通知服务
│   ├── trading_service.py # 核心交易服务
│   ├── backup_service.py  # 数据备份服务
│   ├── stock_info.py      # 股票信息缓存
│   ├── trading_calendar_manager.py # 交易日历管理
│   ├── trading_day_checker.py # 交易日检查
│   ├── daily_exporter.py  # 每日持仓与成交导出
│   ├── data_manager/      # 市场数据下载/标准化/校验
│   ├── strategy/          # T+0 实时适配器与纯策略核心
│   └── backtest/          # Linux/文件驱动回测组件
├── scripts/               # 脚本文件
│   ├── README.md          # 脚本使用说明
│   ├── setup_task_simple.bat # 设置计划任务（推荐）
│   ├── setup_t0_tasks.bat # 设置 T+0 计划任务
│   ├── task_runner.ps1    # Windows 定时任务执行脚本
│   ├── task_runner.sh     # 旧版 shell 定时任务执行脚本
│   ├── run_console.bat    # 手动运行脚本
│   └── load_env.sh        # 环境变量加载
├── logs/                  # 日志文件目录
│   ├── task_execution_trading.log # 交易服务计划任务日志
│   ├── task_execution_t0_daemon.log # T+0 守护进程任务日志
│   ├── task_execution_t0_sync.log # T+0 仓位同步任务日志
│   └── trading_service.log # 交易服务日志
├── backups/               # 数据备份目录
├── tests/                 # 测试文件
│   └── test_*.py          # 各种测试脚本
└── xtquant/               # QMT官方SDK（不要修改）
```

## 快速开始

### 1. 安装依赖

项目使用 [uv](https://github.com/astral-sh/uv) 管理依赖：

```bash
# 安装uv（如果未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 同步项目依赖
uv sync
```

### 2. 配置环境变量

创建并编辑 `.env` 文件：

```env
# Redis配置
REDIS_HOST=10.0.12.2
REDIS_PORT=30102
REDIS_SIGNAL_CHANNEL=trading_signals

# QMT配置
QMT_SESSION_ID=666  # 会话ID（自动检测可用）
QMT_PATH=C:/国金QMT交易端模拟/userdata_mini
QMT_ACCOUNT_ID=39266820
QMT_SESSION_ID_TRADING_SERVICE=666
QMT_SESSION_ID_T0_DAEMON=667
QMT_SESSION_ID_T0_SYNC=668

# 飞书通知配置
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook
FEISHU_SECRET=your-secret-key

# T+0 配置
T0_STOCK_CODE=601138.SH
T0_BASE_POSITION=2600
T0_TACTICAL_POSITION=900
T0_NOTIFY_OBSERVE_SIGNALS=false

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=logs/trading_service.log

# 备份配置
BACKUP_ENABLED=true
BACKUP_TIME=15:05
BACKUP_DIR=backups
```

### 3. 测试系统连接

```bash
# 测试所有组件连接
uv run python main.py test
```

### 4. 运行服务

#### 方式一：手动运行（开发测试）

```bash
# 直接运行
uv run python main.py run

# 或使用批处理脚本
scripts\run_console.bat

# 强制运行（忽略交易日检查）
set TRADING_DAY_CHECK_ENABLED=false
uv run python main.py run
```

#### 方式二：定时任务（生产环境）

以管理员身份运行：

```batch
# 设置每日自动运行的计划任务
scripts\setup_task_simple.bat
```

这会创建Windows计划任务：
- 每天 8:00 AM 自动启动交易服务
- 每天 9:00 PM 自动停止服务
- 非交易日自动跳过
- 日志输出到 `logs/task_execution_trading.log`

## 交易信号格式

向Redis频道发送JSON格式的交易信号：

```json
{
    "signal_id": "SIGNAL_20250809_001",
    "stock_code": "000001",
    "direction": "BUY",
    "volume": 100,
    "price": 10.50,
    "order_type": 23
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| signal_id | string | 是 | 唯一信号标识符 |
| stock_code | string | 是 | 股票代码（6位） |
| direction | string | 是 | 交易方向：BUY（买入）或 SELL（卖出） |
| volume | integer | 是 | 交易数量（股） |
| price | float | 否 | 交易价格（不填为市价单） |
| order_type | integer | 否 | 订单类型（默认23为限价单） |

## 命令行使用

```bash
# 运行交易服务
uv run python main.py run

# 测试系统连接
uv run python main.py test

# 手动备份数据
uv run python main.py backup

# 查看备份配置
uv run python main.py backup-config

# 管理股票信息缓存
uv run python main.py stock-info

# 管理交易日历
uv run python main.py calendar

# 手动发送当日盈亏汇总
uv run python main.py pnl-summary

# 导出每日持仓和成交
uv run python main.py export-daily

# 运行一次 T+0 信号生成
uv run python main.py t0-strategy

# 启动 T+0 守护进程
uv run python main.py t0-daemon

# 从 QMT 同步 T+0 仓位
uv run python main.py t0-sync-position

# 运行 T+0 文件回测
uv run python main.py t0-backtest --minute-data minute.csv --daily-data daily.csv
```

### T+0 文件回测

可在 Linux 或 Windows 上直接使用 csv/parquet 文件运行分钟级回测：

```bash
uv run python main.py t0-backtest \
   --minute-data ./data/minute_601138.parquet \
   --daily-data ./data/daily_601138.parquet \
   --symbol 601138.SH \
   --output-dir ./output/backtest
```

输出文件：

- `signals.csv`
- `fills.csv`
- `summary.json`

### T+0 运行产物

实时 T+0 会在 `output/` 目录写入运行态文件，例如：

- `live_signal_card.json`
- `position_state.json`

这些文件属于本地运行产物，当前已加入 Git 忽略规则，不再纳入版本控制。

## 监控和维护

### 日志文件

- `logs/task_execution_trading.log` - 交易服务计划任务日志（包含启动、停止、错误信息）
- `logs/trading_service.log` - 交易服务详细日志
- `logs/task_debug.log` - 调试日志（如有）
- `logs/task_execution_t0_daemon.log` - T+0 守护进程任务日志
- `logs/task_execution_t0_sync.log` - T+0 仓位同步任务日志

### 数据备份

系统支持自动备份交易数据：

- 默认每日15:05自动备份
- 备份文件保存在 `backups/` 目录
- 格式：`trading_backup_YYYYMMDD_HHMMSS.json.gz`

### 飞书通知

系统会在以下情况发送飞书通知：

- ✅ 服务启动/停止
- 📈 收到交易信号
- 💰 订单成交
- ❌ 订单失败或错误
- ⚠️ 系统异常

## 故障排查

### 常见问题

1. **QMT连接失败**
   - 确保QMT客户端已启动并登录
   - 检查Session ID是否正确
   - 尝试重新启动QMT客户端

2. **Redis连接失败**
   - 检查Redis服务是否运行
   - 验证Redis配置（主机、端口）
   - 检查网络连接

3. **中文日志乱码**
   - 确保使用MINGW64环境运行
   - 检查环境变量 `PYTHONIOENCODING=utf-8`

4. **计划任务不执行**
   - 检查Windows任务计划程序中的任务状态
   - 查看 `logs/task_execution_trading.log` 中的错误信息
   - 确保以管理员权限创建任务

## 开发和测试

### 运行测试

```bash
# 运行所有测试
uv run pytest tests/

# 运行特定测试
uv run python tests/test_redis_integration.py
uv run python tests/test_passorder.py
```

### 代码结构

- 使用SQLAlchemy ORM管理数据库
- 使用loguru进行统一日志管理
- 使用redis-py作为Redis客户端
- 使用xtquant SDK与QMT交互

## 安全提示

⚠️ **重要安全提醒**：

1. **不要**将 `.env` 文件提交到版本控制
2. **定期**更换飞书webhook密钥
3. **限制**Redis访问权限
4. **使用**测试账户进行开发测试
5. **备份**重要的交易数据

## 许可证

本项目仅供学习和研究使用，请遵守相关法律法规。使用本系统进行实际交易产生的任何损失，作者不承担责任。

## 联系方式

如有问题或建议，请提交Issue或联系开发者。
## 分钟行情任务

```bash
# 导出自定义分钟历史行情包
uv run python main.py export-minute-history --trade-date today --listed-only

# 按日任务默认参数拉取当日分钟行情
uv run python main.py export-minute-daily
```

Windows 计划任务配置：

```cmd
scripts\setup_minute_history_task.bat
```

这会创建 `QMT_Minute_History_Daily`，每天 `15:20` 运行，
日志写入 `logs/task_execution_minute_history.log`。
