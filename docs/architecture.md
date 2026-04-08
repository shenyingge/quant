# Architecture

这个文件只描述当前稳定的项目结构、运行模型和边界规则。

## 1. 当前项目边界

- 项目当前只做交易引擎。
- 只保留两条主链路：
  - `QMT 行情 -> Redis 发布`
  - `Redis 下单信号 -> QMT 下单执行`
- 当前文档范围仅覆盖交易引擎、行情发布、健康检查和运维支撑。

## 2. 代码结构

- `main.py`
  - 唯一 CLI 入口。
- `src/trading/`
  - 交易执行、账户数据、运行时协调。
- `src/infrastructure/`
  - 数据库、Redis、通知、调度、CMS、watchdog。
- `src/market_data/`
  - 行情采集、流转与导入。
- `src/data_manager/`
  - 导出、校验、批处理型数据工作流。
- `docs/architecture/`
  - 当前有效的架构专题说明。
- `docs/guides/`
  - 使用手册和操作指南，不自动作为架构约束来源。
- `docs/archive/`
  - 归档文档，不作为当前实现依据。

## 3. 运行模型

- `watchdog`
  - 默认生产入口，管理长期进程与定时任务。
- `cms-server`
  - 提供 `/health` 与账户相关接口。
- `trading engine`
  - 处理 Redis 信号、QMT 下单、QMT 回调、持仓同步。
- `minute history jobs`
  - 负责分钟行情导出与按日入库。

默认运行约束：

- 默认操作入口是 `make`
- `make` 默认启动 `watchdog`
- `make watchdog-bg` 是默认后台入口
- `make trading-engine` / `python main.py run` 仅是手动直启入口

## 4. 数据流规则

- QMT
  - 实时券商连接、回调和行情来源。
- Meta DB
  - 持久化业务历史与 broker-synced snapshot。
- Redis
  - 下单信号与实时行情通道，不作为长期事实来源。
- CMS / account API
  - 默认读 Meta DB，不在请求路径中直接绑定 QMT。

## 5. 边界规则

- 不允许把超出交易引擎职责边界的运行时能力重新写回当前运行模型。
- 不允许把临时兼容层重新扩散回 `src/` 根目录。
- 新文档优先放进 `docs/architecture/`、`docs/guides/`、`docs/archive/`。
- `docs/archive/` 内的内容不作为当前实现依据。
- `main.py` 保持为唯一入口，不承载过多业务逻辑。
- 使用项目绝对导入，例如 `from src.trading.execution.qmt_trader import QMTTrader`。
