# QMT 交易引擎

这是一个收敛为单一职责的 QMT 交易引擎项目，只保留两条主链路：

1. `QMT 行情 -> Redis 发布`
2. `Redis 下单信号 -> QMT 下单执行`

项目边界已收敛为纯交易引擎，现行文档只覆盖行情发布、下单执行、健康检查和相关运维能力。

## 功能特性

- Redis 信号监听与 QMT 自动下单
- QMT 实时行情发布到 Redis 频道与 latest key
- 订单、信号、持仓、成交记录落库到 Meta DB
- CMS 健康检查与 watchdog 守护
- 飞书运行时通知与异常告警
- 分钟行情导出、入库与相关运维工具

## 系统要求

- Python 3.12.3
- Windows 10/11 或 Windows Server 2016+
- QMT 客户端
- Redis
- Meta DB
- MSYS2 / MINGW64 环境

## 核心约束

- QMT 是外部依赖，不由项目自动启动。
- Redis 是信号与行情通道，不作为长期事实来源。
- Meta DB 是运行时事实持久层。
- 默认运行入口是 `watchdog`，默认操作命令是 `make`。
- `python main.py run` / `make trading-engine` 仅用于手动直启交易引擎，不是默认生产入口。

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

创建并编辑 `.env`：

```env
REDIS_HOST=localhost
REDIS_PORT=30102
REDIS_SIGNAL_CHANNEL=trading_signals

QMT_SESSION_ID=666
QMT_SESSION_ID_TRADING_SERVICE=666
QMT_PATH=C:/国金QMT交易端/userdata_mini
QMT_ACCOUNT_ID=your_account_id

META_DB_HOST=127.0.0.1
META_DB_PORT=15432
META_DB_NAME=quant_meta
META_DB_USER=quant
META_DB_PASSWORD=change_me

CMS_SERVER_HOST=127.0.0.1
CMS_SERVER_PORT=8780

WATCHDOG_ENABLED=true
WATCHDOG_ENABLE_TRADING_SERVICE=true

COMMISSION_RATE=0.0001
MIN_COMMISSION=5
TRANSFER_FEE_RATE=0.00001
STAMP_DUTY_RATE=0.0005
```

### 3. 检查系统连接

```bash
make cms-check
uv run python main.py test
```

### 4. 运行服务

默认生产入口：

```bash
make
```

后台运行：

```bash
make watchdog-bg
```

说明：

- `make` 默认启动 `watchdog`
- `make watchdog` / `make watchdog-bg` 会先检查是否已有 watchdog 进程，避免重复启动
- watchdog 负责管理 `cms-server`、`trading_engine`、`minute_history_ingest_daily`

手动直启：

```bash
make trading-engine
make trading-engine-bg
make trading-engine-test
make cms-server
make cms-check
```

底层 CLI 入口仍然可用：

```bash
uv run python main.py run
uv run python main.py test-run
uv run python main.py cms-server
uv run python main.py cms-check
uv run python main.py watchdog
uv run python main.py sync-account-positions
uv run python main.py export-minute-history --trade-date today --listed-only
uv run python main.py export-minute-daily
uv run python main.py ingest-minute-history
uv run python main.py ingest-minute-daily
```

## 交易信号格式

默认通过 Redis 发送 JSON 信号：

```json
{
  "signal_id": "SIGNAL_20250809_001",
  "stock_code": "000001.SZ",
  "direction": "BUY",
  "volume": 100,
  "price": 10.50,
  "order_type": 23
}
```

字段说明：

- `signal_id`: 唯一信号标识
- `stock_code`: 股票代码
- `direction`: `BUY` 或 `SELL`
- `volume`: 股数
- `price`: 可选价格
- `order_type`: 可选订单类型

## 监控与健康检查

CMS `/health` 当前关注：

- 交易日状态
- 数据库连接
- Redis 连接
- QMT 客户端进程
- 交易引擎进程
- watchdog 进程

常用日志：

- `logs/current/trading_engine.log`
- `logs/current/cms_server.log`
- `logs/current/watchdog.log`
- `logs/current/make-watchdog.out`

## 开发与测试

运行测试：

```bash
uv run pytest
uv run pytest --cov=src --cov-report=term-missing
```

当前集成测试约束：

- 允许“真实 Redis + 真实数据库 + mock QMT”的半实物链路验证
- 典型示例见 `tests/integration/test_trading_engine_signal_flow.py`

## 文档约束

当前有效约束来源：

- `README.md`
- `CLAUDE.md`
- `docs/README.md`
- `docs/architecture.md`
- `docs/architecture/*.md`
- `docs/coding-rules.md`

历史专题文档已移出当前约束来源，后续以这里列出的文档为准。
