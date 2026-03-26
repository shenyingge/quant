# Brokers

## Core Contract

- `src/broker/base_broker.py` defines the stable abstraction:
  `connect`, `disconnect`, `submit_order`, `cancel_order`, `get_order`, `get_orders`, `get_position`, `get_positions`, `get_account_info`, `get_current_price`.
- Convenience helpers `buy`, `sell`, `close_position`, `get_cash`, `get_position_size`, and context-manager support sit on top of that contract.
- Shared dataclasses:
  `OrderInfo`, `PositionInfo`, `AccountInfo`.
- Shared enums:
  `OrderType`, `OrderSide`, `OrderStatus`, `PositionSide`.

## Implementations

- `BackTraderBroker`: backtest environment.
- `MiniQMTSimBroker`: QMT simulation environment.
- `MiniQMTLiveBroker`: QMT live trading environment.
- `BrokerFactory` and helper constructors are the intended creation path.

## Design Expectations

- Strategy code should depend on the abstraction, not a concrete broker.
- New implementations should match the semantics of existing dataclasses and enums.
- Keep symbol handling consistent across environments. The repo uses A-share style codes like `000001.SZ` and `600519.SH` in broker/data docs.
- If a live or sim implementation cannot support a method exactly, preserve the same method surface and document the limitation close to the implementation.

## Where To Read Next

- `src/broker/broker_factory.py` for registration and creation behavior.
- `docs/unified_broker_guide.md` for intended consumer usage.
- Implementation files for environment-specific details:
  `src/broker/backtrader_broker.py`,
  `src/broker/miniqmt_sim_broker.py`,
  `src/broker/miniqmt_live_broker.py`.

## Typical Change Patterns

- Add broker capability:
  update `base_broker.py`, then each implementation, then factory/helpers, then docs/tests.
- Fix one implementation bug:
  verify the abstract contract still holds before making a localized change.
- Add a broker type:
  follow the existing factory pattern instead of adding direct `if/else` creation in callers.
