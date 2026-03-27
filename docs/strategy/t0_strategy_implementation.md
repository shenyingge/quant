# T+0 策略实现逻辑说明

## 1. 文档目的

这份文档不是讲“某一时刻应该买还是卖”，而是定义一套可以同时用于：

- Windows 实盘信号生成
- Linux 平台分钟级回测
- 后续参数调优与策略重构

的统一策略实现方式。

核心要求只有两个：

1. 策略逻辑本身必须与 QMT、飞书、数据库解耦。
2. 策略判断必须尽量写成纯计算过程，便于回测逐 bar 重放。

进一步明确为三个严格隔离的域：

1. 行情与交易数据获取
2. 策略信号产出
3. 下单与订单管理

其中策略层只允许消费标准化后的输入，不允许自己发起数据查询，也不允许自己下单。

当前仓库中，这个分层已经落地为：

- `src/strategy/core/`: 纯策略核心与 typed models
- `src/strategy/`: 实时数据适配、状态仓储、信号编排
- `src/backtest/`: Linux/文件驱动回测加载、重放、CLI
- `main.py`: `t0-strategy`、`t0-daemon`、`t0-sync-position`、`t0-backtest` 四个入口

---

## 2. 当前策略目标

标的默认是 `601138.SH`，目标不是提高交易频率，而是在不破坏底仓结构的前提下降低持仓成本。

当前约束采用：

- 底仓：`2600` 股
- 机动仓：`900` 股
- 总目标仓位上限：`3500` 股
- 单日只允许一个分支完成一轮闭环

这里的“闭环”指：

- `positive_t`: 先卖战术仓，再买回
- `reverse_t`: 先买机动仓，再卖旧仓

这意味着策略的本质不是“发一条买卖信号”，而是“管理一个日内状态机”。

---

## 3. 回测友好的设计原则

### 3.0 严格隔离原则

这是实现时必须遵守的第一原则。

策略模块只负责：

- 读取已经准备好的 bar/window/state
- 计算特征
- 更新状态机
- 输出信号或决策建议

策略模块不负责：

- 从 QMT 拉取实时行情
- 从 Redis、数据库、文件系统直接读取交易状态
- 直接调用券商下单接口
- 直接发送飞书或其他通知
- 直接决定订单是否成交

换句话说，策略层只能看到“数据”，不能看到“数据从哪来”；只能输出“信号”，不能负责“信号怎么执行”。

建议用一句话定义边界：

```text
Strategy in, signal out.
```

### 3.0.1 推荐模块边界

建议把系统拆成下面 5 个模块：

1. `MarketDataProvider`
2. `PortfolioStateProvider`
3. `StrategyEngine`
4. `OrderExecutor`
5. `SignalPublisher`

职责分别是：

- `MarketDataProvider`
  - 提供分钟线、日线、昨收、复权、交易日历
- `PortfolioStateProvider`
  - 提供当前仓位、可用股数、现金、历史已成交动作
- `StrategyEngine`
  - 只接收标准化数据，输出策略信号
- `OrderExecutor`
  - 接收信号后决定是否生成订单、如何报单、如何撤单
- `SignalPublisher`
  - 把信号写到 JSON、数据库、消息队列或通知系统

其中 `StrategyEngine` 必须是平台无关模块。

### 3.0.2 禁止依赖规则

为了确保 Linux 回测和 Windows 实盘共用同一套核心逻辑，策略核心模块必须遵守：

- 不 import `xtquant`
- 不 import 通知模块
- 不 import SQLAlchemy session
- 不 import Redis 客户端
- 不 import 操作系统进程控制逻辑

策略核心模块允许依赖：

- `dataclasses`
- `typing`
- `pandas`
- `numpy`
- 项目内纯数据模型与纯计算模块

如果某个模块必须访问 QMT 或数据库，它就不应放进策略核心目录。

### 3.1 分层

实现上应分成 4 层：

1. 数据层
2. 特征层
3. 策略状态机层
4. 执行/回测层

其中只有第 4 层允许依赖平台。

建议职责如下：

- 数据层：读取分钟线、日线、复权、交易日历
- 特征层：从历史 bar 计算 VWAP、bounce、absorption 等
- 状态机层：根据特征和已有状态输出策略动作
- 执行层：负责实盘落库、通知、下单，或回测成交撮合

这里要特别注意：

- 数据层可以属于实盘适配器，也可以属于回测适配器
- 但它不属于策略核心
- 策略核心只接收数据层已经整理好的对象

### 3.2 纯函数优先

回测最怕隐藏状态。

因此策略主逻辑最好满足：

- 输入明确
- 输出明确
- 不直接读数据库
- 不直接发通知
- 不直接调用券商接口

理想形式：

```python
next_state, decision = strategy.on_bar(bar, context, state)
```

或者更严格地说：

```python
next_state, signal = strategy_engine.evaluate(context, state)
```

然后由外部执行层决定：

- 是只记录信号
- 还是转成订单
- 还是拿去做回测撮合

其中：

- `bar` 是当前 1 分钟 bar
- `context` 是当日和历史上下文
- `state` 是上一时刻策略状态
- `next_state` 是更新后的状态
- `decision` 是当前 bar 的策略动作

### 3.3 显式状态

不要把“今天是否已经做过 T”“是否已经买入过 reverse_t”“是否还允许回补”这种信息放在数据库查询里临时推断。

应显式维护状态对象。

---

## 4. 策略输入输出契约

这一节的目的就是保证“策略层只收输入、只吐输出”，不反向穿透到其他系统。

### 4.1 单个 bar 输入

建议 Linux 回测环境统一使用以下字段：

```python
Bar = {
    "symbol": "601138.SH",
    "timestamp": "2026-03-26 10:24:00",
    "open": 50.80,
    "high": 50.95,
    "low": 50.76,
    "close": 50.91,
    "volume": 125600,
    "amount": 6398120.0,
    "pre_close": 51.72,
}
```

要求：

- 时间统一为 `Asia/Shanghai`
- 分钟线必须按时间升序
- 不允许混入未来数据

### 4.2 上下文输入

```python
StrategyContext = {
    "trade_date": "2026-03-26",
    "regime": "transition",
    "daily_window": daily_df,
    "minute_window": intraday_df_until_now,
    "params": params,
}
```

在当前实现里：

- `regime` 由 `RegimeClassifier` 纯计算，`RegimeIdentifier` 负责缓存/持久化适配
- `minute_window` 来自实时 DataFetcher 或回测 DataLoader，但进入策略核心前都必须标准化
- `params` 来自 `T0StrategyParams.from_settings(settings)`，保证实盘和回测使用同一套参数含义

### 4.3 状态输入

```python
StrategyState = {
    "trade_date": "2026-03-26",
    "active_branch": None,
    "branch_stage": "idle",
    "entry_price": None,
    "entry_volume": 0,
    "entry_time": None,
    "completed_round_trips": 0,
    "position_total": 3500,
    "position_base": 2600,
    "position_tactical": 900,
    "t0_buy_capacity": 0,
    "t0_sell_available": 900,
    "cash_available": 70000,
}
```

### 4.4 决策输出

```python
Decision = {
    "action": "observe|positive_t_sell|positive_t_buyback|reverse_t_buy|reverse_t_sell",
    "price": 50.91,
    "volume": 900,
    "reason": "急跌止跌: 反弹2.5%",
    "branch": "reverse_t",
    "state_transition": "idle -> reverse_t_open",
    "meta": {
        "fake_breakout": 0.3,
        "absorption": 0.6,
        "close_vs_vwap": 0.2,
    },
}
```

当前运行时还会把最终展示对象整理为 `SignalCard`，用于：

- 飞书通知
- `output/live_signal_card.json` 输出
- 兼容现有 JSON 消费方

需要注意：`output/` 下文件是运行时产物，不属于版本化文档或源代码。

---

## 5. 特征计算规范

特征层应只依赖当前 bar 及其之前的数据。

建议保留以下特征：

- `day_open`
- `current_close`
- `high_so_far`
- `low_so_far`
- `latest_bar_time`
- `vwap`
- `close_vs_vwap`
- `distance_from_high`
- `bounce_from_low`
- `fake_breakout_score`
- `absorption_score`

建议再补充两个回测更有用的字段：

- `drop_from_prev_close`
- `bars_since_entry`

说明：

- `close_vs_vwap` 使用百分比表示
- `bounce_from_low` 使用百分比表示
- 所有特征都必须能在单个 bar 时点复现

---

## 6. 状态机设计

这是策略最核心的部分。

建议只保留 5 个状态：

- `idle`
- `positive_t_open`
- `positive_t_closed`
- `reverse_t_open`
- `reverse_t_closed`

其中：

- `idle`: 当天还没开始做 T
- `positive_t_open`: 已卖出战术仓，等待回补
- `positive_t_closed`: 正 T 已完成闭环
- `reverse_t_open`: 已买入机动仓，等待卖旧仓
- `reverse_t_closed`: 反 T 已完成闭环

单日状态迁移只允许：

```text
idle -> positive_t_open -> positive_t_closed
idle -> reverse_t_open -> reverse_t_closed
```

不允许：

- `positive_t_open -> reverse_t_open`
- `reverse_t_open -> positive_t_open`
- 单日第二轮开仓

---

## 7. 时间约束建议

不建议把规则写成“必须上午买、下午卖”这种过硬约束。

更适合回测和实盘统一的约束是：

### 7.1 开新 T 的时间窗

- `09:45` 之前不做新开仓
- `14:40` 之后不做新开仓

### 7.2 平已有 T 的时间窗

- 允许直到 `14:56`

### 7.3 最小持有时间

无论是 `positive_t_sell` 后回补，还是 `reverse_t_buy` 后卖旧仓，都建议加最小持有约束：

- `min_hold_bars = 20`

或者：

- `min_hold_minutes = 20`

这样比“必须分别在上下午”更稳，也更适合 Linux 回测中的参数化搜索。

---

## 8. 分支逻辑定义

### 8.1 positive_t 开仓

动作：`positive_t_sell`

适用逻辑：

- 价格先冲高
- 再回落
- 跌回 VWAP 下方
- 当前存在可卖战术仓

建议条件：

- `rise_from_open >= 1.0`
- `pullback_from_high >= 0.5`
- `close_vs_vwap <= -0.05`
- `t0_sell_available > 0`

成交后状态迁移：

```text
idle -> positive_t_open
```

### 8.2 positive_t 平仓

动作：`positive_t_buyback`

适用逻辑：

- 已处于 `positive_t_open`
- 达到最小持有时间
- 出现急跌后反弹或尾盘回稳
- 有可回补容量和现金

建议条件：

- `bounce_from_low >= 0.4`
- `absorption_score >= 0.6`
- `bars_since_entry >= min_hold_bars`

成交后状态迁移：

```text
positive_t_open -> positive_t_closed
```

### 8.3 reverse_t 开仓

动作：`reverse_t_buy`

适用逻辑：

- 相对昨收明显下探
- 从低点反弹
- 不弱于 VWAP
- 当前有机动仓买入容量

建议条件：

- `drop_from_prev_close <= -1.5`
- `bounce_from_low >= 0.4`
- `close_vs_vwap >= -0.5`
- `absorption_score >= 0.6`
- `t0_buy_capacity > 0`

成交后状态迁移：

```text
idle -> reverse_t_open
```

### 8.4 reverse_t 平仓

动作：`reverse_t_sell`

适用逻辑：

- 已处于 `reverse_t_open`
- 达到最小持有时间
- 当前价格相对买入价已有正收益
- 价格回到 VWAP 附近，避免追高卖旧仓

建议条件：

- `profit_vs_entry >= 1.2`
- `abs(close_vs_vwap) <= 0.5`
- `bars_since_entry >= min_hold_bars`
- `t0_sell_available >= entry_volume`

成交后状态迁移：

```text
reverse_t_open -> reverse_t_closed
```

---

## 9. 仓位与资金约束

回测和实盘必须共享同一套仓位约束计算。

建议统一为：

```python
max_position = base_position + tactical_position
t0_sell_available = min(available_volume, max(total_position - base_position, 0))
t0_buy_capacity = max(max_position - total_position, 0)
```

然后再按交易单位取整：

```python
volume = volume // trade_unit * trade_unit
```

对买入还应额外受现金约束：

```python
cash_limited_volume = int(max_trade_value // price)
```

最终下单量：

```python
buy_volume = min(t0_buy_capacity, tactical_position, cash_limited_volume)
sell_volume = min(t0_sell_available, tactical_position)
```

---

## 10. 建议的代码结构

为了 Linux 回测可复用，建议把核心逻辑抽成一个完全独立的小模块。

建议目录：

```text
src/strategy/core/
  models.py
  params.py
  features.py
  regime.py
  state_machine.py
  strategy.py

src/strategy/adapters/
  market_data_qmt.py
  portfolio_qmt.py
  signal_card_writer.py
  signal_history_store.py

src/backtest/
  data_loader.py
  simulator.py
  broker.py
  metrics.py
```

建议职责：

- `models.py`
  - 定义 `Bar`, `Features`, `StrategyState`, `Decision`
- `params.py`
  - 定义所有可调参数
- `features.py`
  - 纯函数，输入 DataFrame，输出特征
- `regime.py`
  - 纯函数，输入日线窗口，输出 regime
- `state_machine.py`
  - 纯函数，输入 state + features，输出 next_state + decision
- `strategy.py`
  - 串起 regime、features、state_machine

适配层建议职责：

- `market_data_qmt.py`
  - 从 QMT 取实盘分钟线并标准化
- `portfolio_qmt.py`
  - 从 QMT 取持仓和现金并标准化
- `signal_card_writer.py`
  - 把信号写到 `live_signal_card.json`
- `signal_history_store.py`
  - 把信号状态写入数据库

回测层建议职责：

- `data_loader.py`
  - 从 Linux 数据源加载历史分钟线/日线
- `simulator.py`
  - 逐 bar 驱动策略核心
- `broker.py`
  - 回测撮合与成本模型
- `metrics.py`
  - 统计绩效指标

实时系统中的现有模块：

- [src/strategy/strategy_engine.py](src/strategy/strategy_engine.py)
- [src/strategy/signal_generator.py](src/strategy/signal_generator.py)
- [src/strategy/position_syncer.py](src/strategy/position_syncer.py)

应逐步退化为平台适配层，而不是继续承载核心策略判断。

特别是：

- [src/strategy/strategy_engine.py](src/strategy/strategy_engine.py) 应只负责调度和输出
- [src/strategy/signal_generator.py](src/strategy/signal_generator.py) 应继续下沉为纯策略核心
- 行情抓取和仓位同步不应继续混在策略判断过程中

---

## 11. Linux 回测建议接口

建议暴露一个统一类：

```python
class T0Strategy:
    def __init__(self, params):
        self.params = params

  def on_bar(self, minute_window, daily_window, portfolio_state, state):
        regime = identify_regime(daily_window, self.params)
        features = calculate_features(minute_window, self.params)
        next_state, decision = evaluate_state_machine(
            regime=regime,
            features=features,
      portfolio_state=portfolio_state,
            state=state,
            params=self.params,
        )
        return next_state, decision
```

Linux 回测主循环示意：

```python
state = init_state(position_total=3500, base_position=2600, tactical_position=900)

for trade_date, intraday_df in grouped_minute_bars:
    state = reset_for_new_day(state, trade_date)
    daily_window = get_daily_window(trade_date)

    for i in range(len(intraday_df)):
        minute_window = intraday_df.iloc[: i + 1]
        state, decision = strategy.on_bar(minute_window, daily_window, state)
        fill_result = simulator.try_fill(decision, intraday_df.iloc[i])
        state = simulator.apply_fill(state, fill_result)
```

这样设计后，回测环境不需要知道 QMT、Redis、飞书，也不依赖 Windows。

同样，Windows 实盘层也不需要知道策略内部细节，只需要：

1. 准备好标准化分钟数据
2. 准备好标准化仓位状态
3. 调用策略核心
4. 决定是否把信号交给订单执行器

这才是严格隔离后的正确依赖方向。

---

## 12. 回测成交与成本模型

Linux 回测至少应统一以下假设：

- 佣金：单边 `2.5 bps`
- 印花税：卖出 `5.0 bps`
- 滑点：单边 `1.0 bps`
- 成交价：
  - 可先用当前 bar 的 `close`
  - 更稳妥可用 `next_bar_open`

建议至少支持两种撮合模式：

1. `close_fill`
2. `next_open_fill`

如果用 `close_fill`，要明确这是偏乐观假设。

---

## 13. 回测输出建议

建议 Linux 回测最终输出：

- `trades.csv`
- `daily_pnl.csv`
- `signal_log.csv`
- `metrics.json`

关键指标建议包括：

- 总收益
- 做 T 次数
- 每轮平均价差
- 胜率
- 平均持有分钟数
- 单边/往返成本占比
- 最大回撤
- 每日未闭环比例

对这个策略，最重要的不是“收益率最大”，而是：

- 是否稳定降低持仓成本
- 是否避免无效高频来回交易
- 是否在不同 regime 下表现一致

---

## 14. 参数化建议

为了方便 Linux 回测，所有阈值都不应散落在代码里。

建议统一参数化：

```python
params = {
    "base_position": 2600,
    "tactical_position": 900,
    "trade_unit": 100,
    "max_trade_value": 70000,
    "positive_sell_min_rise": 1.0,
    "positive_sell_min_pullback": 0.5,
    "reverse_buy_min_drop": 1.5,
    "reverse_buy_min_bounce": 0.4,
    "reverse_sell_min_profit": 1.2,
    "reverse_sell_max_vwap_distance": 0.5,
    "min_hold_bars": 20,
    "open_start_time": "09:45",
    "open_stop_time": "14:40",
    "close_stop_time": "14:56",
}
```

建议在 Linux 侧使用：

- YAML
- JSON
- TOML

任意一种都可以，但必须和回测输出一起保存，确保实验可复现。

---

## 15. 与当前项目的衔接方式

当前项目里已经具备这些可复用部分：

- [src/strategy/feature_calculator.py](src/strategy/feature_calculator.py)
- [src/strategy/regime_identifier.py](src/strategy/regime_identifier.py)
- [src/strategy/signal_generator.py](src/strategy/signal_generator.py)

但还存在两个明显问题：

1. 实时运行逻辑和策略逻辑仍耦合太紧。
2. 当日信号状态部分依赖数据库历史，不利于纯回测重放。
3. 行情获取、仓位同步、信号判断、信号落盘还在同一执行链条里。

因此建议重构顺序为：

1. 先抽 `models.py` 和 `params.py`
2. 再把 `signal_generator.py` 改成纯状态机，不直接查数据库
3. 抽出 `MarketDataProvider` 和 `PortfolioStateProvider` 接口
4. 让 `strategy_engine.py` 只负责接入实时数据和落地输出
5. 最后在 Linux 平台写独立 `simulator.py`

---

## 16. 一句话结论

这套策略最适合被实现成：

- 一个以分钟 bar 为驱动的纯状态机
- 一个显式维护仓位容量和分支阶段的策略核心
- 两套外层适配器：Windows 实盘适配器和 Linux 回测适配器

只要核心逻辑保持纯计算、纯状态迁移，它就能在两个平台上共用，而不会再被 QMT、通知或数据库绑定住。
