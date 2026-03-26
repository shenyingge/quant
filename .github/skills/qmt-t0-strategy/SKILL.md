---
name: qmt-t0-strategy
description: "Understand, extend, or debug the T+0 strategy, typed strategy models, signal-card output, and Linux-friendly backtesting flow in this repository. Use when working on src/strategy, src/strategy/core, src/backtest, output/live_signal_card.json, or T+0 position and branch-state rules."
---

# QMT T+0 Strategy

Use this skill for T+0 strategy work rather than trading-service operations.

## Start Here

- `src/strategy/core/models.py`
- `src/strategy/core/engine.py`
- `src/strategy/core/params.py`
- `src/strategy/regime_identifier.py`
- `src/strategy/signal_generator.py`
- `src/strategy/t0_orchestrator.py`
- `src/backtest/data_loader.py`
- `src/backtest/simulator.py`
- `src/backtest/cli.py`
- `docs/strategy/t0_strategy_implementation.md`

## Working Rules

- Keep `src/strategy/core/` pure and platform-neutral.
- Prefer typed models over new unstructured dict contracts.
- Keep branch-state logic in the core engine, not in the orchestrator or notifier.
- When changing signal output, keep notifier formatting, persistence, tests, and `output/live_signal_card.json` expectations aligned.
- Keep backtests file-driven and reusable on Linux.
