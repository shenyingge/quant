# T+0 Core And Runtime

## Scope

This skill covers the T+0 strategy path for one stock, including:

- typed strategy models
- pure signal generation
- realtime orchestration
- signal-card output
- database-backed signal history adaptation

It does not cover the main Redis trading-service loop unless the task explicitly crosses into `TradingService`.

## Current Layering

The intended dependency direction is:

```text
data adapters / repositories
    -> strategy core
    -> output / notification / persistence adapters
```

### Pure core

Files:

- `src/strategy/core/models.py`
- `src/strategy/core/params.py`
- `src/strategy/core/regime_classifier.py`
- `src/strategy/core/engine.py`

Responsibilities:

- define typed inputs and outputs
- evaluate regime
- enforce T+0 branch rules
- enforce time windows and minimum hold time
- remain usable in Linux backtests without QMT or DB access

### Realtime adapters

Files:

- `src/strategy/feature_calculator.py`
- `src/strategy/position_syncer.py`
- `src/strategy/signal_generator.py`
- `src/strategy/regime_identifier.py`
- `src/strategy/signal_state_repository.py`
- `src/strategy/t0_orchestrator.py`

Responsibilities:

- load/normalize realtime data
- bridge from dict/DataFrame data into typed models
- load signal history from the DB and translate it into `SignalEvent`
- persist signals after the decision has been made
- write `output/live_signal_card.json`
- send T+0 notifications

Runtime artifacts:

- `output/live_signal_card.json` is a generated snapshot for operators and debugging
- `output/position_state.json` is generated state, not source of truth for strategy logic changes
- `output/` should be treated as local runtime output rather than committed project content

### Entry points

Files:

- `main.py`

Commands:

- `t0-strategy`: run once
- `t0-daemon`: poll every minute
- `t0-sync-position`: sync QMT position into the T+0 state file
- `t0-backtest`: file-driven Linux/Windows backtest entry

## Typed Models

Important models in `src/strategy/core/models.py`:

- `FeatureSnapshot`
- `PortfolioState`
- `SignalEvent`
- `BranchState`
- `StrategyDecision`
- `MarketSnapshot`
- `PositionSnapshot`
- `SignalCard`

Design intent:

- adapters may still accept dicts for compatibility
- strategy-facing code should prefer typed objects
- final JSON output is produced from `SignalCard.to_dict()`

## Signal Flow

Realtime path:

```text
minute data
 -> FeatureCalculator.calculate_snapshot()
 -> SignalGenerator.generate_signal()
 -> T0StrategyEngine.generate_signal()
 -> StrategyDecision
 -> T0Orchestrator._build_signal_card()
 -> SignalCard
 -> JSON / notifier / repository
```

History path:

```text
StrategySignalRepository.load_today_history()
 -> SignalEvent[]
 -> T0StrategyEngine.generate_signal(..., signal_history=...)
```

## Invariants

- `SignalGenerator` should stay thin.
- `T0StrategyEngine` is the only place for branch-state logic.
- `RegimeClassifier` should remain pure.
- `RegimeIdentifier` is allowed to cache/save regime state, but not to redefine regime logic.
- Realtime code may use dict compatibility, but new logic should prefer typed-model paths.

## High-Risk Edit Points

- `src/strategy/core/engine.py`: changes user-visible signal behavior
- `src/strategy/core/params.py`: changes defaults used by both realtime and backtest
- `src/strategy/t0_orchestrator.py`: changes live output and notification path
- `src/strategy/signal_state_repository.py`: changes branch continuity across one trading day
- `src/notifications.py`: changes message formatting and observe-signal behavior

## Existing Tests To Keep In Sync

- `tests/test_t0_position_and_state_machine.py`
- `tests/test_t0_core_separation.py`
- `tests/test_t0_signal_card_market_time.py`
- `tests/test_t0_notifier_typed_models.py`
- `tests/test_t0_backtest_simulator.py`
- `tests/test_t0_backtest_cli.py`
