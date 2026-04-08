# QMT 交易引擎

这是一个收敛为单一职责的 QMT 交易引擎项目，只保留两条主链路：

1. `QMT 行情 -> Redis 发布`
2. `Redis 下单信号 -> QMT 下单执行`

## 功能特性

- Redis 信号监听与 QMT 自动下单
- QMT 实时行情发布到 Redis 频道与 latest key
- 订单、信号、持仓、成交记录落库
- 飞书运行时通知与异常告警
- CMS 健康检查与 watchdog 守护
- 分钟行情导出、入库与收盘导出工具

## 系统要求

- Python 3.12.3
- Windows 10/11 或 Windows Server 2016+
- QMT客户端（国金证券版本）
- Redis服务器
- MSYS2/MINGW64环境（推荐）

## 项目结构

```
quant/
├── main.py                # 主程序入口
├── pyproject.toml         # 项目配置和依赖（使用uv管理）
├── pytest.ini             # 测试配置（默认排除 live_qmt / manual）
├── .env                   # 环境配置文件
├── src/                   # 核心源代码
│   ├── infrastructure/    # 基础设施层
│   │   ├── config/        # 配置管理（Pydantic Settings）
│   │   ├── runtime/       # CMS / watchdog / 进程工具
│   │   ├── db/            # SQLAlchemy 模型与会话
│   │   ├── notifications/ # 飞书通知实现
│   │   ├── redis/         # Redis 信号监听器
│   │   └── scheduling/    # 分钟行情定时采集
│   ├── trading/           # 交易领域层
│   │   ├── execution/     # QMT 下单执行器
│   │   └── runtime/       # 交易引擎运行时
│   ├── broker/            # Broker 抽象层
│   ├── data_manager/      # 市场数据下载/标准化/校验
│   ├── market_data/       # 高频实时行情摄入
├── scripts/               # 脚本文件
│   ├── README.md          # 脚本使用说明
│   ├── register_watchdog_service_task.ps1 # 注册单入口 watchdog 开机任务
│   ├── run_console.bat    # 手动运行脚本
│   └── setup_minute_history_task.bat # 分钟行情导出任务安装器
├── logs/                  # 日志文件目录
│   ├── task_execution_trading.log # 交易服务计划任务日志
│   ├── current/          # 当前活跃日志
│   └── archive/          # 滚动压缩归档日志
├── backups/               # 数据备份目录
├── tests/                 # 测试文件
│   ├── unit/              # 单元测试
│   ├── integration/       # 集成测试
│   ├── live/              # 依赖外部环境的测试
│   └── fixtures/          # 共享测试数据与桩
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
REDIS_HOST=localhost
REDIS_PORT=30102
REDIS_SIGNAL_CHANNEL=trading_signals

# QMT配置
QMT_SESSION_ID=666  # 会话ID（自动检测可用）
QMT_PATH=C:/国金QMT交易端模拟/userdata_mini
QMT_ACCOUNT_ID=39266820
QMT_SESSION_ID_TRADING_SERVICE=666

# 飞书通知配置
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook

# 日志配置
LOG_LEVEL=INFO
LOG_DIR=./logs/current
LOG_ARCHIVE_DIR=./logs/archive
LOG_FILE=./logs/current/app.log
LOG_ROTATION=20 MB
LOG_RETENTION=30 days
LOG_COMPRESSION=zip

# 备份配置
BACKUP_ENABLED=true
BACKUP_TIME=15:05
BACKUP_DIR=backups

# 交易成本配置
COMMISSION_RATE=0.0001
MIN_COMMISSION=5
TRANSFER_FEE_RATE=0.00001
STAMP_DUTY_RATE=0.0005
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

#### 方式二：watchdog 守护（生产环境）

以管理员身份运行：

```powershell
# 注册单入口开机任务
.\scripts\register_watchdog_service_task.ps1
```

这会创建单一开机计划任务：
- `Quant_Watchdog_Service` 随系统启动
- `cms-server` 24x7 保持在线
- 交易日内由 watchdog 自动管理交易引擎与分钟行情入库任务
- 非交易时间按 watchdog 时间窗自动停止交易引擎

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

# 管理股票信息缓存
uv run python main.py stock-info

# 管理交易日历
uv run python main.py calendar

# 导出每日持仓和成交
uv run python main.py export-daily

# 启动 CMS 服务
uv run python main.py cms-server

# 启动 watchdog
uv run python main.py watchdog

# 导出分钟行情
uv run python main.py export-minute-history --trade-date today --listed-only

# 分钟行情入库
uv run python main.py ingest-minute-daily

```

## 监控和维护

### 日志文件

- `logs/task_execution_trading.log` - 交易服务计划任务日志（包含启动、停止、错误信息）
- `logs/current/trading_engine.log` - 交易引擎详细日志
- `logs/current/cms_server.log` - CMS 服务详细日志
- `logs/current/watchdog.log` - watchdog 详细日志
- `logs/archive/<role>/` - 滚动后的压缩归档日志
- `logs/task_debug.log` - 调试日志（如有）

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
# 运行所有 CI 测试（自动排除 live_qmt / manual）
uv run pytest

# 运行特定测试文件
uv run pytest tests/live/test_redis_integration.py

# 运行并生成覆盖率报告（目标：核心链路 ≥80%）
uv run pytest --cov=src --cov-report=term-missing

# 强制包含所有标记（包括需要 live QMT 的测试，慎用）
uv run pytest -m ""
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

## Linux 回测说明

当前项目已经移除策略与回测子系统，因此不再提供 Linux 回测命令。Linux 环境下可运行的是分钟行情工具、测试命令和文档中列出的非 QMT 任务；真实下单链路仍以 Windows + QMT 为前提。

```cmd
scripts\setup_minute_history_task.bat
```

这会创建 `QMT_Minute_History_Daily`，每天 `15:20` 运行，
日志写入 `logs/task_execution_minute_history.log`。
