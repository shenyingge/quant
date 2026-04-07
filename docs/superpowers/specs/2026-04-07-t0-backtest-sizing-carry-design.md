# T0 Backtest Sizing And Carry Design

**Goal:** 调整 T0 回测默认仓位与收益口径，使默认参数改为固定股数优先、金额仅作可选上限，同时允许未闭环分支跨日延续，并把“做 T 净收益”作为独立主指标。

## Confirmed Decisions

- 默认仓位语义保持 `base_position + tactical_position`。
- 默认底仓改为 `3000` 股，机动仓改为 `1000` 股，总持仓上限为 `4000` 股。
- 交易单位保持 `100` 股。
- `max_trade_value` 改为 `250000`，仅在买入侧作为现金上限约束，不替代固定股数。
- 允许 `positive_t` 与 `reverse_t` 未闭环分支跨交易日延续。
- 回测主指标为已闭环做 T 的已实现净收益。
- 未闭环分支的浮动盈亏单独展示，不并入“做 T 净收益”。

## Architecture Impact

- `src/strategy/core/params.py`
  - 调整默认参数值，保持参数模型不变。
- `src/backtest/simulator.py`
  - 保留跨日未闭环分支历史，不再把它当作错误行为。
- `src/backtest/metrics.py`
  - 明确区分账户权益、已实现做 T 净收益、未闭环浮动盈亏。
- `src/backtest/cli.py`
  - 输出摘要中展示新的默认参数与主指标。

## Data And Metric Semantics

- `equity_pnl`
  - 继续表示账户视角的权益变化，会混入底仓与未闭环分支的价格波动。
- `net_realized_t_pnl`
  - 作为做 T 主指标，只统计已闭环 roundtrip 的净收益。
- `open_legs`
  - 保留未闭环分支明细。
- `open_legs_mtm_pnl`
  - 汇总未闭环分支的浮动盈亏，作为补充指标。

## Testing Strategy

- 更新单元测试，确认跨日未闭环分支会保留并在次日继续执行。
- 更新单元测试，确认默认参数为 `3000/1000/250000`。
- 更新单元测试，确认摘要把已实现做 T 净收益与未闭环浮盈亏分开。
- 用工业富联近一年分钟数据重新回测，并以 `summary.json` 验证结果。
