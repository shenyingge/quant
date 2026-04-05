# 仓库结构收口设计

## 目标

在不引入过度设计、不改业务行为的前提下，完成一次仓库结构收口，让代码、测试、文档和迁移脚本的目录结构与当前架构一致。

本次设计覆盖四块：

1. `src` 收口
2. `tests` 收口
3. `docs` 收口
4. `migrations` 命名规范统一

执行顺序固定为：`src` -> `tests` -> `docs` -> `migrations`。

## 总体原则

- 先收口，再优化：先解决文件归属混乱，再考虑进一步重构。
- 能移动不重写：优先通过迁移文件、调整 import、更新引用完成整理。
- 不新增新的兼容层：已有 compat wrapper 允许过渡存在，但不得继续新增同类模式。
- 目录服务于当前架构：目录结构应反映 `trading / strategy / market_data / infrastructure` 的真实边界。
- migration 以未来一致为主：避免为了历史文件“看起来整齐”而冒险破坏 Alembic 链。

## src 收口规则

### 保留在 `src` 根目录的内容

只保留以下类型：

- 全局配置与日志模块，如 `config.py`、`logger_config.py`
- 顶层服务入口，如 `watchdog_service.py`、`cms_server.py`
- 少量真正跨域的公共工具，如 `process_utils.py`、`uid.py`

### 必须下沉的内容

- 交易执行、交易运行时、归因、回调相关模块归入 `src/trading/`
- Redis、通知、数据库会话/模型、定时调度归入 `src/infrastructure/`
- 分钟行情、实时行情、导出相关模块归入 `src/market_data/` 或 `src/infrastructure/scheduling/`
- T+0、策略状态、信号生成、策略编排归入 `src/strategy/`
- broker 抽象及实现保留在 `src/broker/`

### wrapper 策略

- `src/database.py`、`src/notifications.py`、`src/redis_listener.py`、`src/trader.py`、`src/trading_engine.py`、`src/trading_service.py` 视为过渡层
- 过渡层不再新增
- 新代码不得再 import 这些 wrapper
- 实施时先迁移调用方，最后再决定是否删除 wrapper

## tests 收口规则

目标是让测试结构对应代码结构，而不是保留历史堆积。

- `tests/` 顶层仅保留少量公共文件：`conftest.py`、`README.md`、`fixtures/`、必要的入口测试
- 测试主体按类型归入已有目录：`unit/`、`integration/`、`contract/`、`live/`
- 平铺在根目录的 `test_*.py` 逐步迁入对应目录
- 只有少量确属跨模块入口验证的测试可以继续留在顶层
- `tests/README.md` 必须与最终结构一致，不再描述旧的运行方式和旧的测试布局

## docs 收口规则

目标是区分“当前有效文档”和“历史过程文档”。

- `docs/` 根目录只保留当前有效的架构、运维、功能说明
- 设计稿、计划、执行记录统一放入 `docs/superpowers/`
- 与当前目录结构不一致的文档，要么更新，要么移入历史区域，不继续放在根层误导使用者
- 文档更新跟随代码最终落位进行，不提前单独大规模改写

## migrations 规则

目标是统一规则，但不破坏已有迁移链。

- 从本次收口之后开始，新 migration 统一使用时间戳前缀命名
- 历史 migration 默认不改 revision id
- 历史文件名只有在确认不会影响 Alembic 使用和团队流程时才允许重命名
- 如果历史文件最终不重命名，则在文档中明确：命名规范从某个时间点开始统一生效

## 实施边界

本次只处理结构与归属，不主动做以下事情：

- 不改交易、通知、回测等业务规则
- 不顺带重写大模块内部逻辑
- 不为了“更优雅”引入新的抽象层
- 不批量重命名 public API，除非它只是 compat wrapper 的过渡引用

## 验收标准

- `src` 根目录只剩少量稳定入口和公共模块
- `tests` 以分层目录为主，顶层平铺测试显著减少
- `docs` 根目录只保留当前有效文档，`docs/superpowers/` 承接历史设计与执行记录
- 新旧 migration 规则边界清楚，后续新增文件遵循统一命名
- 仓库整理过程不引入新的业务行为变更

## 推荐执行方式

1. 先列出 `src` 根目录文件的三分类清单：保留、下沉、wrapper
2. 按代码归属迁移 `tests`
3. 根据最终代码结构更新和归档 `docs`
4. 最后补齐 migration 命名规则与说明

该设计刻意保持最小化，不追求一次性“完美架构”，只解决当前最明显的目录混乱问题。