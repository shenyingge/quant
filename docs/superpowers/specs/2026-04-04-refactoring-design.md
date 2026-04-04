# QMT 交易系统重构设计规范

**Goal:** 在不中断生产的前提下，分阶段将 QMT 交易系统重构为职责清晰、可测试、可扩展的架构。

**Architecture:** 领域驱动分层结构（trading / strategy / market_data / infrastructure），策略核心与运行时完全解耦，成交记录独立表存储，支持多策略并行与 backtrader 兼容。

**Tech Stack:** Python 3.11+, SQLAlchemy 2.x, PostgreSQL, Redis, xtquant SDK, pytest, backtrader

---

## 1. 重构目标

本轮重构围绕以下主线，严格按阶段顺序执行：

1. **Phase 0** — 测试基础设施与安全隔离
2. **Phase 1** — 成交记录归属重构（修复漏单 bug，新增 trade_executions / order_cancellations 表）
3. **Phase 2** — 高频行情接入（tick 级或 3 秒快照，替代分钟级）
4. **Phase 3** — 策略解耦与多策略并行（backtrader 兼容）
5. **Phase 4** — src 目录结构化迁移
6. **Phase 5** — 清理、文档、skills 整理

**生产安全原则：** 交易下单、成交回调、持仓同步是最高风险区，所有改动必须先建回归测试再动代码。

---

## 2. 目标目录结构

```text
src/
├── app/                         # CLI 入口、调度编排
│   └── cli/
├── trading/                     # 实盘交易域
│   ├── execution/               # qmt_trader, qmt_callbacks
│   ├── persistence/             # order_repository, execution_repository, attribution_service
│   ├── runtime/                 # engine (原 trading_engine.py)
│   └── models/                  # order_ids, execution_models
├── strategy/
│   ├── t0/
│   │   ├── core/                # 纯策略核心，无副作用
│   │   ├── runtime/             # 实时适配器
│   │   └── persistence/         # 信号/状态持久化
│   └── shared/                  # StrategyManager, SignalRouter, PositionAllocator
├── market_data/
│   ├── ingestion/               # tick/3s 快照接入
│   ├── storage/
│   └── export/
├── infrastructure/
│   ├── db/
│   ├── redis/
│   ├── notifications/
│   └── qmt/
├── broker/                      # 已有 broker 抽象，保留
└── backtest/                    # 只依赖 strategy/t0/core
```

---

## 3. 数据库模型设计

### 3.1 order_records（报单表，提交后不可变）

```python
class OrderRecord(Base):
    __tablename__ = "order_records"
    id              = Column(Integer, primary_key=True)
    order_uid       = Column(String(50), unique=True, index=True)   # 内部唯一 ID (ULID)
    broker_order_id = Column(String(50), index=True, nullable=True) # QMT 委托号，可能晚到
    signal_id       = Column(String(50), index=True, nullable=True)
    order_source    = Column(String(50), default="signal_submit")   # signal_submit / manual_trade_callback / recovery_backfill
    stock_code      = Column(String(20), nullable=False)
    direction       = Column(String(10), nullable=False)            # BUY / SELL
    volume          = Column(Integer, nullable=False)
    price           = Column(Float, nullable=True)
    submit_request_id = Column(String(50), index=True, nullable=True)      # 本地下单请求 ID，用于归属
    order_type      = Column(String(50), nullable=False, default="LIMIT")  # LIMIT / MARKET / MARKET_SH_BEST_5_CANCEL / MARKET_SZ_INSTANT_CANCEL 等
    order_time      = Column(DateTime, default=datetime.utcnow)
    order_status    = Column(String(20), default="PENDING")         # 派生状态，由 trade_executions 更新
    error_message   = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

**关键约束：** 报单提交后，除 `order_status` / `broker_order_id` / `error_message` 外，其余字段不可修改。不再在报单表维护 `filled_volume` / `filled_price` / `commission` 等聚合字段。

### 3.2 trade_executions（成交表，每笔成交一行，不可变）

```python
class TradeExecution(Base):
    __tablename__ = "trade_executions"
    id               = Column(Integer, primary_key=True)
    execution_uid    = Column(String(50), unique=True, index=True)  # 内部唯一 ID (ULID)
    order_uid        = Column(String(50), index=True, nullable=True) # 归属报单
    broker_trade_id  = Column(String(50), index=True, nullable=True) # QMT 成交编号
    broker_order_id  = Column(String(50), index=True, nullable=True)
    stock_code       = Column(String(20), nullable=False)
    direction        = Column(String(10), nullable=False)
    filled_volume    = Column(Integer, nullable=False)
    filled_price     = Column(Float, nullable=False)
    filled_amount    = Column(Float, nullable=False)
    filled_time      = Column(DateTime, nullable=False)
    commission       = Column(Float, nullable=True)
    transfer_fee     = Column(Float, nullable=True)
    stamp_duty       = Column(Float, nullable=True)
    total_fee        = Column(Float, nullable=True)
    execution_source = Column(String(50), default="qmt_trade_callback")  # qmt_trade_callback / order_polling_backfill / manual_recovery
    dedupe_key       = Column(String(100), unique=True, index=True)      # 兜底去重
    created_at       = Column(DateTime, default=datetime.utcnow)
```

### 3.3 order_cancellations（撤单表，每次撤单一行）

```python
class OrderCancellation(Base):
    __tablename__ = "order_cancellations"
    id               = Column(Integer, primary_key=True)
    order_uid        = Column(String(50), index=True, nullable=False)
    broker_order_id  = Column(String(50), index=True, nullable=True)
    stock_code       = Column(String(20), nullable=False)
    cancelled_volume = Column(Integer, nullable=False)
    cancel_time      = Column(DateTime, nullable=False)
    cancel_reason    = Column(String(100), nullable=True)  # timeout / manual / risk_control
    created_at       = Column(DateTime, default=datetime.utcnow)
```

### 3.4 成交归属算法

成交回调到达时，按以下顺序归属：

1. 通过 `broker_order_id` 精确匹配 `order_records`
2. 通过本地下单上下文映射 `submit_request_id -> order_uid`
3. 通过活动订单缓存和近期候选窗口匹配
4. 若仍无法匹配：创建 synthetic `order_records`（`order_source=manual_trade_callback`），再写 `trade_executions`

---

## 4. 高频行情接入

### 4.1 数据频率

实盘行情频率：**tick 级或至少 3 秒快照**，不再使用分钟级。

### 4.2 接口设计

```python
class MarketDataProvider(Protocol):
    def subscribe_tick(self, stock_codes: list[str], callback: Callable) -> None: ...
    def subscribe_snapshot(self, stock_codes: list[str], interval_seconds: int, callback: Callable) -> None: ...
    def get_latest_snapshot(self, stock_code: str) -> MarketSnapshot | None: ...
    def get_minute_bars(self, stock_code: str, count: int) -> list[MinuteBar]: ...
```

### 4.3 实现

- `QMTTickProvider`：通过 xtquant `subscribe_quote` 接收 tick 推送
- `QMTSnapshotProvider`：通过 xtquant `get_full_tick` 定时拉取 3 秒快照
- 策略 core 只依赖 `MarketDataProvider` 协议，不直接依赖 QMT

---

## 5. 多策略并行架构

### 5.1 组件

```text
StrategyManager
├── 管理多个 StrategyRunner 实例
├── 统一订阅行情，分发给各策略
└── 汇总信号，交给 SignalRouter

SignalRouter
├── 根据策略配置路由信号
└── 防止同一标的多策略冲突

PositionAllocator
├── 按策略分配持仓上限
└── 防止超仓
```

### 5.2 策略接口

```python
class StrategyBase(ABC):
    """所有策略的基类，兼容 backtrader 风格"""
    
    @abstractmethod
    def on_bar(self, bar: BarData) -> list[Signal]: ...
    
    @abstractmethod
    def on_tick(self, tick: TickData) -> list[Signal]: ...
    
    @abstractmethod
    def on_trade(self, trade: TradeData) -> None: ...
    
    @property
    @abstractmethod
    def params(self) -> StrategyParams: ...
```

### 5.3 backtrader 兼容

- `BacktraderAdapter`：将 `StrategyBase` 包装为 backtrader `Strategy` 子类
- `QMTDataFeed`：将 QMT 行情适配为 backtrader `DataFeed`
- `QMTBrokerInterface`：将 QMT 下单接口适配为 backtrader `Broker`
- 策略逻辑写在 `StrategyBase` 中，可直接在 backtrader 回测框架运行

---

## 6. 分阶段实施

### Phase 0：测试基础设施

**目标：** 建立安全推进重构的工程基础。

**任务：**
- 安装 pytest, pytest-cov, pytest-mock, freezegun
- 建立 `pytest.ini`，定义 markers：`unit`, `integration`, `contract`, `db`, `redis`, `live_qmt`, `manual`
- 建立 PostgreSQL 测试 fixture（临时 schema，自动建表/清理）
- 把现有脚本式测试标记为 `live_qmt` 或迁入 `tests/live/`
- 测试目录结构：`tests/unit/`, `tests/integration/`, `tests/contract/`, `tests/live/`, `tests/fixtures/`

**验收：** `pytest -m "not live_qmt and not manual"` 稳定通过，不触发真实下单。

---

### Phase 1：成交归属重构

**目标：** 修复漏单 bug，建立正确的成交数据模型。

**任务：**
- 新增 `order_uid` 字段到 `order_records`（ULID）
- 新建 `trade_executions` 表
- 新建 `order_cancellations` 表
- 新增 `order_type` 字段（LIMIT / MARKET / MARKET_SH_BEST_5_CANCEL / MARKET_SZ_INSTANT_CANCEL 等）
- 实现 `AttributionService`（成交归属算法）
- 修复 `on_stock_trade` 回调（从覆写改为 append 到 `trade_executions`）
- 删除 `order_records` 中的聚合字段（`filled_volume`, `filled_price`, `commission` 等）
- 数据迁移脚本：将现有 `trade_breakdown` JSON 迁移到 `trade_executions` 行
- 更新 `trading_engine.py` 中引用聚合字段的代码

**验收：** 每笔成交有唯一 `execution_uid`，归属到唯一 `order_uid`，部分成交/重复回调均正确处理。

---

### Phase 2：高频行情接入

**目标：** 将实盘行情从分钟级升级为 tick 级或 3 秒快照。

**任务：**
- 定义 `MarketDataProvider` 协议
- 实现 `QMTTickProvider` 和 `QMTSnapshotProvider`
- 更新 T0 策略 runtime 使用新行情接口
- 保留分钟行情作为回测数据源

**验收：** 实盘策略以 ≤3 秒频率接收行情，策略 core 不直接依赖 QMT。

---

### Phase 3：策略解耦与多策略并行

**目标：** 策略核心与运行时完全解耦，支持多策略并行，兼容 backtrader。

**任务：**
- 固化 `T0StrategyKernel` 为唯一核心入口
- 将 `src/strategy/core/*` 迁移到 `src/strategy/t0/core/`
- 实现 `StrategyBase` 抽象基类
- 实现 `StrategyManager`, `SignalRouter`, `PositionAllocator`
- 实现 `BacktraderAdapter`, `QMTDataFeed`, `QMTBrokerInterface`
- 保留兼容 wrapper（`src/strategy/t0_orchestrator.py` 等）
- 确保 `src/backtest/*` 只依赖 `strategy/t0/core`

**验收：** 策略 core 不依赖 QMT/Redis/DB/通知，回测与实时复用同一核心，策略可在 backtrader 中运行。

---

### Phase 4：src 目录结构化迁移

**目标：** 将零散模块迁入明确域包。

**任务：**
- `src/trader.py` → `src/trading/execution/qmt_trader.py`
- `src/trading_engine.py` → `src/trading/runtime/engine.py`
- `src/redis_listener.py` → `src/infrastructure/redis/signal_listener.py`
- `src/notifications.py` → `src/infrastructure/notifications/feishu.py`
- `src/database.py` 拆分为 session / models / repositories
- 保留旧路径兼容 wrapper 直到所有 import 迁移完成

**验收：** 新代码不再新增到 `src/` 根目录，旧入口仍可工作。

---

### Phase 5：清理、文档、skills 整理

**目标：** 工程化收尾，整理 superpowers skills。

**任务：**

**代码清理：**
- 删除确认不再使用的兼容 wrapper
- 更新 README 与 CLAUDE.md
- 建立 CI 默认测试矩阵（`pytest -m "not live_qmt and not manual"`）
- 增加 coverage 报告（目标：核心链路 ≥80%）

**Skills 整理（`C:\Users\sai\.claude\plugins\`）：**
- 审查现有 skills，删除过时或重复的
- 确保每个 skill 描述准确反映当前行为
- 精简 skill 内容，去除冗余说明
- 验证 skill 触发条件与实际使用场景匹配

**验收：** CI 绿色，文档与现状一致，skills 简洁准确。

---

## 7. 关键设计决策

| 决策 | 原因 |
|------|------|
| 报单表不维护聚合字段 | 单一数据源原则；聚合字段由 trade_executions 派生，避免多处更新导致不一致 |
| 每笔成交独立一行 | 修复分笔成交漏单 bug；支持精确手续费归属 |
| 策略 core 无副作用 | 使回测与实时复用同一逻辑；便于单元测试 |
| 行情升级到 tick/3s | 实盘 T0 策略需要更高频的价格信号 |
| 多策略通过 StrategyManager 管理 | 防止多策略对同一标的产生冲突信号；统一持仓分配 |
| backtrader 兼容通过 Adapter 实现 | 不侵入策略核心逻辑；保持 backtrader 生态工具可用 |
| PostgreSQL 测试用临时 schema | SQLite 无法复现 PostgreSQL 方言行为；临时 schema 保证测试隔离 |

---

## 8. 非目标

以下不在本轮范围内：

- 一次性重写所有 broker 抽象
- 一次性迁移全部 `src/*.py`
- 替换所有 CLI 命令名
- 分钟行情 DB 入库（gold schema）— 已在旧方案中，本轮暂不执行

