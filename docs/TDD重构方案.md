# QMT量化交易系统 - 可落地 TDD 重构方案

> 目标不是“一次性推倒重来”，而是在当前版本上，按测试先行、小步迁移、兼容过渡的方式，完成可控的彻底重构。

## 1. 本次重构的明确目标

本轮重构只围绕下面 4 条主线展开，并以它们为最高优先级：

1. `src/strategy` 解耦与重组  
   目标是让策略核心逻辑可以脱离 QMT、Redis、数据库、通知系统，单独抽出来做回测与复用。

2. `src` 目录结构化  
   目标是把目前平铺、职责混杂的模块逐步收敛成清晰的包结构，而不是继续往 `src/` 根目录堆文件。

3. 实盘报单/成交归属重构  
   目标是让每一笔成交都能严谨地归属到唯一的报单记录，并为报单记录、成交记录引入内部唯一 ID。

4. 分钟行情每日 15:10 增量入库  
   目标是在保留现有分钟历史导出能力的同时，新增“从当年开始的一次性回补 + 每日 15:10 增量同步”的数据库入库链路，写入 `gold` schema 的新表。

---

## 2. 当前版本的真实基础

本方案基于当前代码现状重新制定，不再假设项目“从零开始”：

- 已存在纯策略核心雏形：`src/strategy/core/*`
- 已存在文件驱动回测：`src/backtest/*`
- 已存在分钟历史导出 CLI 和 15:10 定时任务包装脚本
- 已存在成交回调归属逻辑与相关测试，但模型仍不够清晰，缺少稳定的内部唯一 ID
- 已存在大量测试文件，但它们混合了：
  - pytest 单元测试
  - 手工脚本式测试
  - 真实 QMT / Redis / Meta DB 依赖测试

因此，本次方案不会再用“先大改目录，再补测试”的方式推进，而是：

- 先建立测试分级和基线
- 再拆高风险业务链路
- 最后做目录迁移和兼容层清理

---

## 3. 重构原则

### 3.1 测试先行，但测试要分层

不是简单追求覆盖率，而是先锁住高风险行为：

- 策略信号行为不漂移
- 成交不会丢、不重、不串单
- 分钟行情入库不重复、不缺行、不跨交易日污染
- CLI 与定时任务在迁移期间不失效

### 3.2 不做 Big Bang 重命名

禁止一开始就把所有模块整体迁到新路径。必须采用：

- 新包落地
- 旧模块保留兼容 wrapper
- 逐步迁移 import
- 最后统一清理

### 3.3 先抽“纯核心”，再移动“运行时”

对策略、成交归属、分钟行情三个方向，都遵守同一套路：

1. 先定义领域模型与边界
2. 再把纯逻辑抽离成无副作用模块
3. 最后让 QMT / Redis / DB / 通知去适配纯逻辑

### 3.4 生产安全优先于代码洁癖

本项目涉及实盘链路，因此：

- 交易下单、成交回调、持仓同步、订单轮询是最高风险区
- 对这些区域的结构调整必须建立回归测试和兼容层
- 不允许为了“目录更整洁”牺牲线上行为稳定性

---

## 4. 目标架构

### 4.1 `src` 的目标结构

目标不是一步到位，而是分阶段收敛到下面的结构：

```text
src/
├── app/                         # CLI、入口、调度编排
│   ├── cli/
│   └── scheduling/
├── trading/                     # 实盘交易域
│   ├── runtime/
│   ├── execution/
│   ├── reconciliation/
│   ├── persistence/
│   └── models/
├── strategy/                    # 策略域
│   ├── t0/
│   │   ├── core/               # 纯策略核心，可单独回测
│   │   ├── runtime/            # 实时运行适配器
│   │   ├── persistence/        # 信号/状态持久化
│   │   └── contracts/          # typed models / DTO
│   └── shared/
├── market_data/                 # 行情数据域
│   ├── ingestion/
│   ├── storage/
│   ├── export/
│   └── models/
├── infrastructure/              # 外部依赖适配层
│   ├── db/
│   ├── redis/
│   ├── notifications/
│   └── qmt/
├── broker/                      # 已有 broker 抽象，继续保留
└── backtest/                    # 回测框架，依赖 strategy core，不依赖实盘运行时
```

### 4.2 本轮只搬迁“会被本次需求触达”的模块

不要求第一阶段把所有 `src/*.py` 都迁完。本轮重点迁移以下高价值模块：

- `src/trader.py`
- `src/trading_engine.py`
- `src/strategy/*`
- `src/minute_history_exporter.py`
- `src/database.py`
- `src/redis_listener.py`
- `src/notifications.py`

### 4.3 兼容迁移策略

迁移期间保留兼容 wrapper，例如：

- `src/trading_service.py` 继续作为 wrapper
- 老路径 `src.strategy.strategy_engine` 保留导出
- 老路径 `src.trader` 在迁移期继续可 import

直到：

- 新路径稳定
- 所有 import 已迁移
- 测试和脚本都切到新路径

才允许删除旧 wrapper

---

## 5. 四条重构主线

## 5.1 主线 A：测试基础设施与分级治理

### 5.1.1 目标

先把“能安全推进重构”的测试体系搭起来。

### 5.1.2 关键问题

当前测试存在几个明显问题：

- pytest 与脚本式测试混杂
- 部分测试直接连接真实 QMT / Redis / Meta DB
- 没有统一 marker，CI 无法安全筛选
- ORM 测试如果继续用 SQLite，很容易和当前 PostgreSQL schema 行为不一致

### 5.1.3 测试分层

统一拆成四层：

1. `unit`
   - 纯 Python
   - 不连接 QMT / Redis / DB
   - 允许 monkeypatch / fake / stub

2. `integration`
   - 允许连接测试数据库、测试 Redis
   - 不下真实单
   - 校验 repository、数据流、入库、归属算法

3. `contract`
   - 校验 CLI、任务包装脚本、导出/入库 payload、typed model 边界

4. `live_qmt`
   - 真实 QMT 或模拟盘依赖
   - 默认不进 CI
   - 只手工触发

### 5.1.4 测试目录目标结构

```text
tests/
├── unit/
│   ├── strategy/
│   ├── trading/
│   ├── market_data/
│   └── infrastructure/
├── integration/
│   ├── trading/
│   ├── market_data/
│   └── strategy/
├── contract/
│   ├── cli/
│   ├── db/
│   └── serialization/
├── live/
│   ├── qmt/
│   └── redis/
└── fixtures/
```

### 5.1.5 测试数据库策略

这里明确修正旧方案：

- 纯 ORM / repository 集成测试不再以 SQLite 作为主方案
- 使用 PostgreSQL 测试库或专用临时测试 schema
- 通过环境变量切换，例如：
  - `META_DB_TEST_HOST`
  - `META_DB_TEST_NAME`
  - `META_DB_TEST_USER`
  - `META_DB_TEST_PASSWORD`
  - `META_DB_TEST_SCHEMA_PREFIX`

SQLite 只允许用于完全不依赖 schema / 方言特性的纯内存测试。

数据库测试执行方式明确为：

1. 测试开始前，由 fixture 生成本次测试专用 schema  
   例如：`trading_test_<timestamp>_<worker_id>`
2. 在该 schema 下动态创建本次测试需要的表
3. 通过 fixture 插入测试数据
4. 执行测试
5. 测试结束后自动清理测试数据
6. drop 测试表
7. drop 测试 schema

推荐分两层 fixture：

- `session` 级 fixture
  - 创建数据库连接
  - 创建临时 schema
  - 根据目标 metadata 建表
  - 用于同一轮测试复用连接资源

- `function` 级 fixture
  - 为单个测试插入 seed 数据
  - 测试结束后回滚或 truncate
  - 保证测试之间相互隔离

建议实现原则：

- repository / ORM 集成测试默认使用“临时 schema + 自动 drop”
- 每个测试只创建需要的表，不做全库建表
- 测试数据通过 fixture 或 factory 显式生成，不复用生产表中的存量数据
- teardown 必须是强制执行的，即使测试失败也要清理
- 并行测试时，schema 名称必须唯一，避免互相污染

这一点作为硬约束：

- 不保留长期存在的测试表
- 不要求人工清库
- 不允许测试数据残留到公共 schema

### 5.1.6 第一批必须补齐的基线测试

#### A. 实盘链路

- 信号字段归一化
- `signal_id` 去重
- 异步下单回调成功/失败
- 成交回调归属
- 未匹配成交回调的 synthetic order 创建
- 订单轮询补全成交与终态

#### B. 策略链路

- `T0StrategyEngine` 核心分支逻辑
- `T0StrategyKernel` 可脱离运行时独立执行
- runtime adapter 对 core 的入参转换正确
- 回测路径与实时路径复用同一核心语义

#### C. 行情入库链路

- 当日分钟数据增量 upsert
- 初始回补与日常增量不会重复
- 非交易日跳过
- 同一 `(symbol, bar_time)` 不产生重复记录

---

## 5.2 主线 B：报单记录 / 成交记录归属重构

### 5.2.1 目标

把“订单”和“成交”从现在偏过程化的处理方式，重构成稳定的领域模型：

- 一个报单记录有唯一内部 ID
- 一笔成交记录有唯一内部 ID
- 多笔成交可以归属于同一报单
- 手工单 / 丢失回调 / broker order id 不完整时，仍能稳定归属

### 5.2.2 目标模型

#### 订单记录：`order_records`

保留现有表，但扩充字段并明确语义：

- `order_uid`
  - 新增
  - 内部唯一 ID，推荐 `UUID/ULID`
  - 作为系统内稳定主引用

- `signal_id`
  - 保留
  - 表示上游交易信号 ID

- `broker_order_id`
  - 新增
  - 表示 QMT 原始委托号
  - 允许为空，因为异步序列号场景和手工单场景可能晚到或缺失

- `submit_request_id`
  - 新增
  - 用于关联一次下单请求，区分“本地下单请求”与“最终 broker order id”

- `order_source`
  - 新增
  - 枚举值建议：`signal_submit` / `manual_trade_callback` / `recovery_backfill`

#### 成交记录：新增 `trade_executions`

新增独立成交表，不再把“成交明细”只塞在 `order_records` 聚合字段里：

- `execution_uid`
  - 内部唯一 ID

- `order_uid`
  - 外键，归属到 `order_records.order_uid`

- `broker_trade_id`
  - broker 侧成交编号

- `broker_order_id`
  - broker 侧委托编号

- `stock_code`
- `direction`
- `filled_volume`
- `filled_price`
- `filled_amount`
- `filled_time`
- `execution_source`
  - `qmt_trade_callback` / `order_polling_backfill` / `manual_recovery`

- `dedupe_key`
  - 用于兜底去重

### 5.2.3 归属算法

成交归属顺序固定为：

1. 通过 `broker_order_id` 精确匹配 `order_records`
2. 通过本地下单上下文映射 `submit_request_id -> order_uid`
3. 通过活动订单缓存和近期候选窗口匹配
4. 若仍无法匹配：
   - 创建 synthetic `order_records`
   - 生成新的 `order_uid`
   - `order_source = manual_trade_callback`
   - 再写入 `trade_executions`

### 5.2.4 聚合策略

`order_records` 继续保留以下聚合字段，作为查询优化层：

- `filled_volume`
- `filled_price`
- `filled_time`
- `order_status`
- `fill_notified`

但这些字段的更新来源必须统一为：

- `trade_executions` 写入后同步更新
- 或通过 repository/service 聚合更新

不允许多个地方各自随意改聚合字段。

### 5.2.5 需要新增/重构的代码模块

```text
src/trading/
├── models/
│   ├── order_ids.py
│   └── execution_models.py
├── persistence/
│   ├── order_repository.py
│   ├── execution_repository.py
│   └── attribution_service.py
├── execution/
│   ├── qmt_trader.py
│   └── qmt_callbacks.py
└── runtime/
    └── engine.py
```

### 5.2.6 测试方案

#### 单元测试

- `submit_request_id -> order_uid` 映射
- `broker_order_id` 精确匹配
- synthetic order 创建
- 多次部分成交归属到同一 `order_uid`
- 相同成交回调去重

#### 集成测试

- 一笔信号 -> 一笔订单 -> 多笔成交 -> 最终订单聚合状态正确
- 手工成交回调 -> synthetic order + execution 写入
- 订单轮询补全不会重复写成交明细

#### 回归测试

- 保留并升级现有 `tests/test_trade_callback_persistence.py`
- 加入 `trade_executions` 断言，不再只断言 `order_records`

---

## 5.3 主线 C：分钟行情每日 15:10 增量入库到 `gold`

### 5.3.1 目标

在当前已有分钟历史导出器基础上，新增数据库入库链路，而不是把“导出 zip/parquet”与“数据库入库”混成一个职责。

### 5.3.2 原则

- 导出能力继续保留
- 入库能力独立实现
- 两者可以复用同一份数据提取与标准化逻辑
- 每日任务默认只同步当日交易日数据
- 首次上线前支持“从当年 1 月 1 日到今天”的一次性回补

### 5.3.3 新表设计

建议新建：

- `gold.stock_minute_bars_1m`

字段建议：

- `symbol`
- `trade_date`
- `bar_time`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `amount`
- `source`
- `ingested_at`
- `updated_at`

约束建议：

- 主唯一键：`(symbol, bar_time)`
- 索引：`(trade_date)`
- 索引：`(symbol, trade_date)`

### 5.3.4 代码结构

```text
src/market_data/
├── ingestion/
│   ├── minute_history_ingestor.py
│   ├── minute_history_service.py
│   └── minute_history_scheduler.py
├── storage/
│   ├── minute_bar_repository.py
│   └── sql_models.py
└── export/
    └── minute_history_exporter.py
```

### 5.3.5 CLI 设计

新增命令，避免一开始就改坏现有导出命令：

- `python main.py ingest-minute-history`
- `python main.py ingest-minute-daily`

现有命令继续保留：

- `python main.py export-minute-history`
- `python main.py export-minute-daily`

迁移后期再评估是否合并或废弃老命令。

### 5.3.6 同步模式

#### 一次性回补

- 起点：当年 `0101`
- 终点：今天
- 用于首次上线前建基线

#### 每日增量

- 执行时间：交易日 15:10
- 范围：仅当天 trade date
- 写库方式：upsert

### 5.3.7 与现有任务脚本的关系

当前已有：

- `scripts/setup_minute_history_task.bat`
- `scripts/task_wrapper_minute_history.bat`
- `main.py export-minute-daily`

本次重构方案要求：

1. 先保留现有任务链路
2. 新增 ingestion 任务链路
3. 完成测试与验收后，再把 15:10 任务切换到新的 DB ingestion 命令

### 5.3.8 测试方案

#### 单元测试

- trade date 解析
- 数据标准化
- 空结果 / 缺字段 / 非交易日跳过
- upsert key 正确

#### 集成测试

- 同一 symbol 同一 bar 重复同步不会重复入库
- 一次性回补后再跑每日增量不会新增重复行
- CLI 能正确切换 `bootstrap` 与 `daily`

#### 合同测试

- `main.py ingest-minute-daily`
- 15:10 wrapper 脚本调用正确

---

## 5.4 主线 D：`src/strategy` 解耦与清晰化

### 5.4.1 目标

让策略具备以下硬约束：

- 纯策略核心可单独 import 和单独回测
- 纯策略核心不依赖：
  - QMT
  - Redis
  - SQLAlchemy Session
  - Feishu 通知
  - 本地文件写入
- 实时运行时只做：
  - 取数
  - 入参适配
  - 调 core
  - 输出/通知/持久化

### 5.4.2 目标结构

```text
src/strategy/
├── t0/
│   ├── core/
│   │   ├── engine.py
│   │   ├── kernel.py
│   │   ├── models.py
│   │   ├── params.py
│   │   └── regime_classifier.py
│   ├── runtime/
│   │   ├── strategy_service.py
│   │   ├── market_data_provider.py
│   │   ├── position_provider.py
│   │   ├── signal_publisher.py
│   │   └── diagnostics.py
│   ├── persistence/
│   │   ├── signal_repository.py
│   │   └── regime_repository.py
│   └── contracts/
│       └── dto.py
└── shared/
```

### 5.4.3 当前文件的迁移建议

| 当前文件 | 目标位置 | 说明 |
| --- | --- | --- |
| `src/strategy/core/*` | `src/strategy/t0/core/*` | 保留纯核心 |
| `src/strategy/strategy_engine.py` | `src/strategy/t0/runtime/strategy_service.py` | 实时入口 |
| `src/strategy/signal_generator.py` | `src/strategy/t0/runtime/signal_adapter.py` 或并入 `strategy_service.py` | 保持薄适配层 |
| `src/strategy/position_syncer.py` | `src/strategy/t0/runtime/position_provider.py` | 运行时依赖 |
| `src/strategy/regime_identifier.py` | `src/strategy/t0/persistence/regime_repository.py` | 缓存/状态持久化 |
| `src/strategy/signal_state_repository.py` | `src/strategy/t0/persistence/signal_repository.py` | 信号历史 |
| `src/strategy/t0_orchestrator.py` | 保留为兼容 wrapper | 迁移期不删 |

### 5.4.4 回测边界

回测必须只依赖：

- `src/strategy/t0/core/*`
- `src/backtest/*`
- 标准化后的分钟 / 日线数据

禁止依赖：

- `src/strategy/t0/runtime/*`
- `src/trader.py`
- `src/notifications.py`
- `src/redis_listener.py`

### 5.4.5 核心入口统一

`T0StrategyKernel` 作为唯一“纯核心可复用入口”：

- 实时路径通过 adapter 调 `kernel`
- 回测路径通过 simulator 调 `kernel`

不再允许“实时一套逻辑、回测一套逻辑”。

### 5.4.6 测试方案

#### 单元测试

- `T0StrategyEngine`
- `T0StrategyKernel`
- typed models
- 参数校验
- 状态机与 branch 约束

#### 合同测试

- runtime adapter -> kernel 入参转换
- `SignalCard` 输出字段
- repository -> `SignalEvent` 历史还原

#### 回归测试

保留并扩展现有：

- `tests/test_t0_core_separation.py`
- `tests/test_t0_strategy_kernel.py`
- `tests/test_t0_backtest_simulator.py`
- `tests/test_t0_backtest_cli.py`
- `tests/test_t0_signal_card_market_time.py`

---

## 6. 分阶段实施方案

## Phase 0：测试基线与安全隔离

### 目标

建立可以安全推动后续重构的工程基础。

### 任务

1. 增加 `pytest`、`pytest-cov`、`pytest-mock`、`freezegun`
2. 建立 `pytest.ini`
3. 定义 markers：
   - `unit`
   - `integration`
   - `contract`
   - `db`
   - `redis`
   - `live_qmt`
   - `manual`
4. 把现有脚本式测试中高风险的测试标记为 `live_qmt` 或迁入 `tests/live`
5. 建立测试数据库 fixture：
   - 自动创建临时 schema
   - 自动建表
   - 自动注入 seed 数据
   - 自动 drop schema / tables
6. 先把成交归属、策略核心、分钟行情入库相关测试纳入默认可跑集合
7. 补充测试数据工厂，避免手写重复 seed SQL

### 验收标准

- `pytest -m "not live_qmt and not manual"` 可稳定运行
- 默认测试不会触发真实下单
- 有明确的 live/manual 测试边界
- 数据库集成测试运行前自动建表和插数
- 数据库集成测试运行后自动删表和删 schema
- 测试失败后也不会留下残余测试数据

---

## Phase 1：成交归属与唯一 ID

### 目标

先解决实盘数据正确性问题。

### 任务

1. 为 `order_records` 增加 `order_uid`
2. 引入 `broker_order_id`
3. 新增 `trade_executions`
4. 把回调归属逻辑收敛到 `AttributionService`
5. 更新 `QMTCallback` 与订单轮询逻辑
6. 保留旧字段兼容读路径
7. 补 migration 与回填脚本

### 验收标准

- 每条成交记录都能定位到唯一 `order_uid`
- 手工成交也能归属
- 部分成交、多次成交、重复回调均正确处理
- 现有通知与查询接口行为不回退

---

## Phase 2：分钟行情 DB 入库

### 目标

落地 `gold.stock_minute_bars_1m` 与每日 15:10 增量同步。

### 任务

1. 新建 ORM / SQL model
2. 实现 `MinuteHistoryIngestor`
3. 实现 bootstrap + daily 两种模式
4. 新增 CLI：
   - `ingest-minute-history`
   - `ingest-minute-daily`
5. 新增任务 wrapper
6. 验证当年回补 + 每日增量链路

### 验收标准

- 当年历史可一次性回补
- 每日 15:10 仅同步当日增量
- 同一 bar 不重复
- 非交易日自动跳过

---

## Phase 3：策略解耦与可单独回测

### 目标

把 `src/strategy` 重构成“纯核心 + 运行时适配器 + 持久化”的清晰结构。

### 任务

1. 固化 `T0StrategyKernel` 为唯一核心入口
2. 清理 runtime 中的策略业务逻辑
3. 将 side effect 迁出 core
4. 迁移 `strategy` 目录到 `t0/core`、`t0/runtime`、`t0/persistence`
5. 保留兼容 wrapper
6. 确保 `src/backtest/*` 只依赖 core

### 验收标准

- `strategy core` 不依赖 QMT / Redis / DB / 通知
- 回测与实时复用同一核心
- `src/strategy` 目录边界清晰

---

## Phase 4：`src` 根目录结构化迁移

### 目标

开始把零散高频模块迁入明确域包。

### 任务

1. `src/trader.py` -> `src/trading/execution/qmt_trader.py`
2. `src/trading_engine.py` -> `src/trading/runtime/engine.py`
3. `src/redis_listener.py` -> `src/infrastructure/redis/signal_listener.py`
4. `src/notifications.py` -> `src/infrastructure/notifications/feishu.py`
5. `src/minute_history_exporter.py` -> `src/market_data/export/minute_history_exporter.py`
6. `src/database.py` 拆成：
   - session
   - models
   - repositories

### 验收标准

- 新代码不再新增到 `src/` 根目录
- 旧入口仍可工作
- wrapper 数量逐步减少

---

## Phase 5：清理、CI、文档收口

### 目标

完成最终工程化收尾。

### 任务

1. 删除确认不再使用的 wrapper
2. 更新 README / docs / scripts
3. 建立 CI 默认测试矩阵
4. 增加 coverage 报告与最低门槛
5. 对 live/manual 测试形成单独操作文档

### 验收标准

- 默认 CI 绿色
- 关键 live/manual 测试有明确执行指引
- 文档与现状一致

---

## 7. 关键设计决策

### 7.1 为什么先做“成交归属”而不是先大搬目录

因为它直接影响生产数据正确性，是最高风险需求；而目录迁移更多是工程清晰度问题。

### 7.2 为什么分钟行情入库要独立于导出器

因为：

- 导出器的目标是文件产物和 NAS
- 入库器的目标是可查询、可增量更新的数据库表

这两者可以共享底层提取/标准化代码，但不应混成一个命令。

### 7.3 为什么策略目录迁移要保留兼容层

因为当前 `main.py`、测试、诊断脚本、回测 CLI 已经依赖现有 import 路径，直接 rename 风险过高。

### 7.4 为什么不把 ORM 集成测试建立在 SQLite 上

因为当前数据库使用 PostgreSQL schema 与 Meta DB 约束，SQLite 会掩盖真实问题。

---

## 8. 成功标准

### 8.1 架构成功标准

- `src/strategy` 结构清晰，可单独回测
- `src` 根目录不再持续膨胀
- 实盘链路的归属逻辑集中化
- 分钟行情 DB 入库链路独立、可观测、可重跑

### 8.2 数据成功标准

- 每笔成交存在唯一 `execution_uid`
- 每个报单存在唯一 `order_uid`
- 每笔成交归属到唯一 `order_uid`
- `gold.stock_minute_bars_1m` 能支撑按 symbol / trade_date 查询

### 8.3 工程成功标准

- 默认测试集稳定
- 高风险 live 测试被隔离
- 文档、命令、脚本、表结构保持一致

---

## 9. 本方案的明确非目标

以下事项不在本轮第一优先级内：

- 一次性重写所有 broker 抽象
- 一次性迁移全部 `src/*.py`
- 一次性替换所有 CLI 命令名
- 把所有历史测试在第一周全部改造完毕

这些工作只有在前述四条主线完成后再继续推进。

---

## 10. 执行建议

实际执行顺序建议固定为：

1. 先做 Phase 0
2. 再做 Phase 1
3. 然后做 Phase 2
4. 再做 Phase 3
5. 最后做 Phase 4 和 Phase 5

也就是说：

- 先锁住测试和生产数据正确性
- 再补分钟行情 DB 能力
- 最后再做大范围目录结构清理

这样才能最大程度保证重构过程可控。
