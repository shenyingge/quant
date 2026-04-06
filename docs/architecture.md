# Architecture

这个文件只描述稳定的项目结构规则，不承载任务流程。

## 1. 分层

- `AI_CONSTITUTION.md`
  - 核心强约束，只放必须长期成立的规则。
- `docs/architecture.md`
  - 结构边界、模块职责、数据流和运行模型。
- `docs/coding-rules.md`
  - 命名、导入、测试、配置、文件布局等编码规则。
- `templates/*.md`
  - 面向具体任务的执行模板，按需使用，不自动加载。

## 2. 代码结构

- `main.py`
  - 唯一 CLI 入口。
- `src/trading/`
  - 交易执行、账户数据、运行时协调。
- `src/strategy/`
  - T+0 策略与策略运行时。
- `src/strategy/core/`
  - 纯策略核心，不依赖 QMT、Redis、数据库会话。
- `src/infrastructure/`
  - 数据库、Redis、通知、调度等基础设施。
- `src/market_data/`
  - 行情采集、流转与导入。
- `src/data_manager/`
  - 导出、校验、批处理型数据工作流。
- `docs/architecture/`
  - 更细粒度的架构专题说明。
- `docs/guides/`
  - 操作手册和开发指南。
- `docs/strategy/`
  - 当前有效的策略说明。
- `docs/archive/`
  - 归档文档，不再作为当前规则来源。

## 3. 运行模型

- `watchdog`
  - 管理长期进程与定时任务。
- `cms-server`
  - 提供健康检查、账户接口和监控入口。
- `trading engine`
  - 处理订单、QMT 回调、持仓同步。
- `strategy engine`
  - 生成 T+0 信号和运行卡片。

## 4. 数据流规则

- QMT
  - 实时券商状态来源。
- Meta DB
  - 持久化业务历史与 broker-synced snapshot。
- Redis
  - 信号与实时行情通道，不作为长期事实来源。
- CMS / account API
  - 默认读 Meta DB，不在请求路径中直接绑定 QMT。

## 5. 边界规则

- 不允许把基础设施依赖直接拉进 `src/strategy/core/`。
- 不允许把临时兼容层重新扩散回 `src/` 根目录。
- 新文档优先放进 `docs/architecture/`、`docs/guides/`、`docs/strategy/`。
- `docs/archive/` 内的内容不作为当前实现依据。
- 旧 `.codex/skills` 和 `.agents/skills` 已被本层和 `templates/` 取代，不再作为项目规范入口。
- src/ 中不允许存在没有归属到文件夹的 Python 文件。要对当前的 src/ 文件结构进行调整，把散落在 src/ 根目录的 Python 文件移动到合适的子目录中，保持 src/ 目录下只有子目录，除了__init__.py。
- 测试文件应遵循现有的测试结构和文件放置约定，具体可以参考 `tests/README.md` 中的说明。
- 不允许生成临时文件，比如一次性的 prompt 文件，只执行一次的脚本,或者不放在 `docs/`。
- 不允许存在临时性没有规划的命名，比如 new_implementation.py、temp_script.py 这类没有明确归属和长期意义的文件。所有新增的代码文件都应该有明确的功能定位，并放在合适的目录中，保持项目结构清晰有序。
- main.py 文件作为唯一入口，不允许过度扩展，不能包含过多的业务逻辑。main.py 应该保持简洁，主要负责启动应用程序和调用其他模块的功能。所有核心业务逻辑应该放在 src/ 目录下的相应模块中，main.py 只负责协调这些模块的调用。main.py 文件长度不能超过300行。
- python 文件内的import 部分要放在顶部并且进行排序，而不是分散在文件的不同位置。所有的 import 语句应该集中在文件的开头，并按照标准库、第三方库、项目内部模块的顺序进行排序。
- 使用项目路径而不是相对路径引入。比如应该使用 `from src.trading.execution.qmt_trader import QMTTrader` 而不是 `from ..execution.qmt_trader import QMTTrader`。
