import ast
from pathlib import Path
from types import SimpleNamespace

import backtrader as bt
import pandas as pd

from src.strategy.adapters.backtrader_adapter import BacktraderStrategyWrapper
from src.strategy.core.models import PortfolioState
from src.strategy.shared.strategy_contracts import BarData, StrategyParams, TradeData
from src.strategy.strategies.t0.strategy import T0Strategy


def _build_position() -> PortfolioState:
    return PortfolioState(
        total_position=2600,
        available_volume=2600,
        cost_price=72.0,
        base_position=2600,
        tactical_position=900,
        max_position=3500,
        t0_sell_available=0,
        t0_buy_capacity=900,
        cash_available=70000.0,
    )


def test_t0_strategy_returns_backtrader_compatible_buy_signal():
    strategy = T0Strategy(
        StrategyParams(name="t0_backtest", stock_code="601138.SH", max_position=3500),
        daily_data=pd.DataFrame({"close": [10.0, 10.1, 10.2]}, index=pd.date_range("2026-03-20", periods=3)),
        initial_position=_build_position(),
    )
    strategy.feature_calculator = SimpleNamespace(
        calculate_snapshot=lambda _: SimpleNamespace(
            to_dict=lambda: {
                "day_open": 10.0,
                "current_close": 10.1,
                "high_so_far": 10.2,
                "low_so_far": 9.9,
                "latest_bar_time": "2026-03-26 09:30:00",
                "vwap": 10.0,
                "close_vs_vwap": 1.0,
                "distance_from_high": -1.0,
                "bounce_from_low": 2.0,
                "fake_breakout_score": 0.0,
                "absorption_score": 0.8,
                "prev_close": 9.9,
                "open_gap_pct": 1.0,
            }
        )
    )
    strategy.regime_classifier = SimpleNamespace(calculate=lambda _: "transition")
    strategy.engine = SimpleNamespace(
        generate_signal=lambda **kwargs: {
            "action": "reverse_t_buy",
            "reason": "test buy",
            "price": 10.1,
            "volume": 900,
            "branch": "reverse_t",
        },
        _build_branch_state=lambda history: SimpleNamespace(completed=False, branch="reverse_t"),
    )

    signals = strategy.on_bar(
        BarData(
            stock_code="601138.SH",
            bar_time="2026-03-26 09:30:00",
            open=10.0,
            high=10.2,
            low=9.9,
            close=10.1,
            volume=1000,
        )
    )

    assert signals == [
        {
            "type": "BUY",
            "volume": 900,
            "price": 10.1,
            "reason": "test buy",
            "signal_action": "reverse_t_buy",
            "branch": "reverse_t",
        }
    ]


def test_t0_strategy_updates_state_from_trade_callback():
    strategy = T0Strategy(
        StrategyParams(name="t0_backtest", stock_code="601138.SH", max_position=3500),
        initial_position=_build_position(),
    )
    strategy._pending_signals.append(
        {
            "direction": "BUY",
            "signal_action": "reverse_t_buy",
            "branch": "reverse_t",
        }
    )

    strategy.on_trade(
        TradeData(
            order_id="1",
            stock_code="601138.SH",
            direction="BUY",
            filled_price=10.0,
            filled_volume=900,
            filled_time="2026-03-26 09:31:00",
        )
    )

    assert strategy.position.total_position == 3500
    assert strategy.position.t0_buy_capacity == 0
    assert len(strategy.signal_history) == 1
    assert strategy.signal_history[0].action == "reverse_t_buy"


def test_t0_strategy_uses_incremental_feature_updates_when_available():
    class FakeFeatureCalculator:
        def __init__(self):
            self.calls = []

        def initialize_intraday_state(self):
            return {}

        def update_snapshot_from_bar(self, state, *, bar, latest_bar_time):
            self.calls.append((state, bar, latest_bar_time))
            return SimpleNamespace(
                to_dict=lambda: {
                    "day_open": 10.0,
                    "current_close": 10.1,
                    "high_so_far": 10.2,
                    "low_so_far": 9.9,
                    "latest_bar_time": "2026-03-26 09:30:00",
                    "vwap": 10.0,
                    "close_vs_vwap": 1.0,
                    "distance_from_high": -1.0,
                    "bounce_from_low": 2.0,
                    "fake_breakout_score": 0.0,
                    "absorption_score": 0.8,
                    "prev_close": 9.9,
                    "open_gap_pct": 1.0,
                }
            )

        def calculate_snapshot(self, minute_data):
            raise AssertionError("incremental path should avoid rebuilding DataFrame")

    strategy = T0Strategy(
        StrategyParams(name="t0_backtest", stock_code="601138.SH", max_position=3500),
        daily_data=pd.DataFrame({"close": [10.0, 10.1, 10.2]}, index=pd.date_range("2026-03-20", periods=3)),
        initial_position=_build_position(),
    )
    strategy.feature_calculator = FakeFeatureCalculator()
    strategy._feature_state = strategy.feature_calculator.initialize_intraday_state()
    strategy.regime_classifier = SimpleNamespace(calculate=lambda _: "transition")
    strategy.engine = SimpleNamespace(
        generate_signal=lambda **kwargs: {
            "action": "reverse_t_buy",
            "reason": "test buy",
            "price": 10.1,
            "volume": 900,
            "branch": "reverse_t",
        },
        _build_branch_state=lambda history: SimpleNamespace(completed=False, branch="reverse_t"),
    )

    signals = strategy.on_bar(
        BarData(
            stock_code="601138.SH",
            bar_time="2026-03-26 09:30:00",
            open=10.0,
            high=10.2,
            low=9.9,
            close=10.1,
            volume=1000,
        )
    )

    assert len(strategy.feature_calculator.calls) == 1
    assert signals[0]["signal_action"] == "reverse_t_buy"


def test_backtrader_wrapper_forwards_completed_order_to_strategy():
    trades = []
    wrapper = BacktraderStrategyWrapper.__new__(BacktraderStrategyWrapper)
    wrapper.strategy = SimpleNamespace(
        stock_code="601138.SH",
        on_trade=lambda trade: trades.append(trade),
    )
    wrapper.data = SimpleNamespace(datetime=SimpleNamespace(datetime=lambda _: pd.Timestamp("2026-03-26 09:31:00").to_pydatetime()))

    order = SimpleNamespace(
        status=bt.Order.Completed,
        ref=7,
        executed=SimpleNamespace(price=10.2, size=900),
        isbuy=lambda: True,
    )

    wrapper.notify_order(order)

    assert len(trades) == 1
    assert trades[0].direction == "BUY"
    assert trades[0].filled_volume == 900


def test_backtest_side_has_no_xtquant_and_live_runtime_has_no_backtrader():
    checks = {
        Path("src/backtest/simulator.py"): {"xtquant"},
        Path("src/backtest/cli.py"): {"xtquant"},
        Path("src/strategy/strategies/t0/strategy.py"): {"xtquant", "backtrader"},
        Path("src/strategy/strategies/t0/strategy_engine.py"): {"backtrader"},
    }

    for file_path, forbidden_modules in checks.items():
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module] if node.module else []
            else:
                continue

            for module_name in modules:
                for forbidden in forbidden_modules:
                    assert forbidden not in module_name, f"{file_path}: imports {forbidden}"
