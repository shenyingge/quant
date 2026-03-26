---
name: qmt-broker-data
description: Understand, extend, or debug the broker abstraction and data/export workflows in this repository. Use when working on `src/broker/*`, `docs/unified_broker_guide.md`, `src/data_manager/*`, `docs/market_data_format.md`, `src/daily_exporter.py`, or changes involving backtests, simulated or live QMT brokers, market data normalization, holdings/trades export, and strategy-facing data contracts.
---

# QMT Broker Data

Use this skill when the task is not about the main service loop but about the broker abstraction, strategy-facing market data, or daily holdings/trades export.

Start with [references/brokers.md](references/brokers.md) for the broker contract and [references/data-and-export.md](references/data-and-export.md) for market-data and export behavior.

## Workflow

1. Decide whether the task is about broker API shape, broker implementation, market-data format, or export/output format.
2. Trace the abstraction first:
   `src/broker/base_broker.py` -> broker implementation -> factory/consumer code.
3. Preserve cross-environment compatibility. Backtest, QMT sim, and QMT live should expose the same high-level operations where possible.
4. For data-format tasks, keep symbol format, timestamp handling, and DataFrame column names consistent with the existing docs and code.
5. For export changes, verify both CSV output and Redis payload shape.

## Safety Rules

- Do not assume broker work is isolated from real trading. `MiniQMTLiveBroker` and `DailyExporter` both rely on live QMT connectivity.
- Avoid changing enum values or dataclass field names in `base_broker.py` unless all implementations and consumers are updated together.
- Preserve factory-based creation. New broker types should integrate through the existing factory pattern, not direct branching across the codebase.
- Keep Redis export failures non-fatal unless the user explicitly wants stricter behavior; current export logic still writes CSV when Redis is down.

## Editing Guidance

- Use `BaseBroker`, dataclasses, and enums as the stable contract for strategy-side code.
- Keep market-data normalization explicit; this repo documents a standard pandas DataFrame shape for strategy inputs.
- When editing export fields, confirm names and rounding rules in both CSV and Redis payload construction.
- Treat broker and data docs as design intent, but verify against source before changing behavior.

## References

- `references/brokers.md`: broker abstraction, factory usage, live/sim/backtest split, extension rules.
- `references/data-and-export.md`: standard market-data format, daily export payloads, Redis keys, and practical invariants.
