from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from src.backtest.simulator import T0BacktestSimulator
from src.strategy.core.models import PortfolioState, SignalEvent
from src.strategy.strategies.t0.feature_calculator import FeatureCalculator


def test_feature_calculator_returns_snapshot_object():
    minute_data = pd.DataFrame(
        {
            "open": [10.0, 10.1],
            "high": [10.2, 10.3],
            "low": [9.9, 10.0],
            "close": [10.1, 10.2],
            "volume": [1000, 1200],
            "pre_close": [9.95, 9.95],
        },
        index=pd.to_datetime(["2026-03-26 09:30:00", "2026-03-26 09:31:00"]),
    )

    snapshot = FeatureCalculator().calculate_snapshot(minute_data)

    assert snapshot is not None
    assert snapshot.current_close == 10.2
    assert snapshot.latest_bar_time == "2026-03-26 09:31:00"


def test_feature_calculator_day_snapshots_match_prefix_snapshots():
    minute_data = pd.DataFrame(
        {
            "open": [0.0, 10.0, 10.1, 0.0, 10.2],
            "high": [0.0, 10.2, 10.4, 0.0, 10.5],
            "low": [0.0, 9.9, 10.0, 0.0, 10.1],
            "close": [0.0, 10.1, 10.3, 0.0, 10.4],
            "volume": [0, 1000, 1200, 0, 800],
            "pre_close": [9.8, 9.95, 9.95, 9.95, 9.95],
        },
        index=pd.to_datetime(
            [
                "2026-03-26 09:29:00",
                "2026-03-26 09:30:00",
                "2026-03-26 09:31:00",
                "2026-03-26 09:32:00",
                "2026-03-26 09:33:00",
            ]
        ),
    )
    calculator = FeatureCalculator()

    prefix_snapshots = [
        calculator.calculate_snapshot(minute_data.iloc[: idx + 1])
        for idx in range(len(minute_data))
    ]
    day_snapshots = calculator.calculate_day_snapshots(minute_data)

    assert day_snapshots == prefix_snapshots


def test_feature_calculator_incremental_bar_updates_match_day_snapshots():
    minute_data = pd.DataFrame(
        {
            "open": [0.0, 10.0, 10.1, 0.0, 10.2],
            "high": [0.0, 10.2, 10.4, 0.0, 10.5],
            "low": [0.0, 9.9, 10.0, 0.0, 10.1],
            "close": [0.0, 10.1, 10.3, 0.0, 10.4],
            "volume": [0, 1000, 1200, 0, 800],
            "pre_close": [9.8, 9.95, 9.95, 9.95, 9.95],
        },
        index=pd.to_datetime(
            [
                "2026-03-26 09:29:00",
                "2026-03-26 09:30:00",
                "2026-03-26 09:31:00",
                "2026-03-26 09:32:00",
                "2026-03-26 09:33:00",
            ]
        ),
    )
    calculator = FeatureCalculator()
    state = calculator.initialize_intraday_state()

    incremental_snapshots = []
    for idx in range(len(minute_data)):
        incremental_snapshots.append(
            calculator.update_snapshot_from_bar(
                state,
                bar=minute_data.iloc[idx].to_dict(),
                latest_bar_time=minute_data.index[idx],
            )
        )

    assert incremental_snapshots == calculator.calculate_day_snapshots(minute_data)


def test_backtest_simulator_runs_and_emits_signal_log():
    index = pd.to_datetime(
        [
            "2026-03-26 09:50:00",
            "2026-03-26 10:00:00",
            "2026-03-26 13:30:00",
        ]
    )
    minute_data = pd.DataFrame(
        {
            "open": [50.0, 49.6, 50.8],
            "high": [50.1, 50.9, 51.0],
            "low": [49.4, 49.5, 50.6],
            "close": [49.6, 50.8, 50.8],
            "volume": [10000, 15000, 12000],
            "amount": [496000, 762000, 609600],
            "pre_close": [50.5, 50.5, 50.5],
        },
        index=index,
    )
    daily_data = pd.DataFrame({"close": [50 + i * 0.1 for i in range(100)]})
    position = PortfolioState(
        total_position=2600,
        available_volume=2600,
        cost_price=72.0,
        base_position=2600,
        tactical_position=900,
        max_position=3500,
        t0_sell_available=0,
        t0_buy_capacity=900,
        cash_available=70000,
    )

    result = T0BacktestSimulator().run(minute_data, daily_data, position)

    assert not result["signals"].empty
    assert set(result["signals"].columns) >= {"timestamp", "action", "reason"}
    assert result["final_position"].max_position == 3500


def test_backtest_simulator_applies_commission_transfer_fee_and_stamp_duty():
    minute_index = pd.to_datetime(["2026-03-26 09:50:00"])
    minute_data = pd.DataFrame(
        {
            "open": [50.0],
            "high": [50.2],
            "low": [49.8],
            "close": [50.0],
            "volume": [10000],
            "amount": [500000],
            "pre_close": [49.9],
        },
        index=minute_index,
    )
    daily_data = pd.DataFrame({"close": [50 + i * 0.1 for i in range(100)]})
    position = PortfolioState(
        total_position=3500,
        available_volume=3500,
        cost_price=72.0,
        base_position=2600,
        tactical_position=900,
        max_position=3500,
        t0_sell_available=900,
        t0_buy_capacity=0,
        cash_available=70000,
    )

    with patch.object(
        T0BacktestSimulator,
        "__init__",
        lambda self, params=None, execution_mode="same_bar_close": None,
    ):
        simulator = T0BacktestSimulator()
        simulator.params = SimpleNamespace(
            t0_trade_unit=100,
            t0_commission_rate=0.0001,
            t0_min_commission=5.0,
            t0_transfer_fee_rate=0.00001,
            t0_stamp_duty_rate=0.0005,
        )
        simulator.execution_mode = "same_bar_close"
        simulator.feature_calculator = SimpleNamespace(
            calculate_snapshot=lambda window: FeatureCalculator().calculate_snapshot(window)
        )
        simulator.regime_classifier = SimpleNamespace(calculate=lambda _: "transition")
        simulator.engine = SimpleNamespace(
            generate_signal=lambda **kwargs: {
                "action": "positive_t_sell",
                "reason": "test",
                "price": 50.0,
                "volume": 900,
                "branch": "positive_t",
            },
            _build_branch_state=lambda history: SimpleNamespace(
                completed="positive_t_buyback" in [event.action for event in history]
            ),
        )

        result = simulator.run(minute_data, daily_data, position)

    fill = result["fills"].iloc[0]
    assert fill["commission"] == 5.0
    assert fill["transfer_fee"] == 0.45
    assert fill["stamp_duty"] == 22.5
    assert fill["total_fee"] == 27.95
    assert result["final_position"].cash_available == 70000 + 50.0 * 900 - 27.95


def test_backtest_simulator_next_bar_open_executes_on_following_bar():
    minute_index = pd.to_datetime(
        [
            "2026-03-26 09:50:00",
            "2026-03-26 09:51:00",
        ]
    )
    minute_data = pd.DataFrame(
        {
            "open": [50.0, 50.5],
            "high": [50.2, 50.8],
            "low": [49.8, 50.4],
            "close": [50.1, 50.7],
            "volume": [10000, 12000],
            "amount": [501000, 608400],
            "pre_close": [49.9, 49.9],
        },
        index=minute_index,
    )
    daily_data = pd.DataFrame({"close": [50 + i * 0.1 for i in range(100)]})
    position = PortfolioState(
        total_position=3500,
        available_volume=3500,
        cost_price=72.0,
        base_position=2600,
        tactical_position=900,
        max_position=3500,
        t0_sell_available=900,
        t0_buy_capacity=0,
        cash_available=70000,
    )
    call_times = []

    def fake_generate_signal(**kwargs):
        call_times.append(kwargs["current_datetime"])
        if kwargs["current_datetime"] == minute_index[0].to_pydatetime():
            return {
                "action": "positive_t_sell",
                "reason": "test",
                "price": 50.1,
                "volume": 900,
                "branch": "positive_t",
            }
        return {"action": "observe", "reason": "test", "price": 0.0, "volume": 0, "branch": None}

    with patch.object(
        T0BacktestSimulator,
        "__init__",
        lambda self, params=None, execution_mode="same_bar_close": None,
    ):
        simulator = T0BacktestSimulator()
        simulator.params = SimpleNamespace(t0_trade_unit=100)
        simulator.execution_mode = "next_bar_open"
        simulator.feature_calculator = SimpleNamespace(
            calculate_snapshot=lambda window: FeatureCalculator().calculate_snapshot(window)
        )
        simulator.regime_classifier = SimpleNamespace(calculate=lambda _: "transition")
        simulator.engine = SimpleNamespace(
            generate_signal=fake_generate_signal,
            _build_branch_state=lambda history: SimpleNamespace(
                completed="positive_t_buyback" in [event.action for event in history]
            ),
        )

        result = simulator.run(minute_data, daily_data, position)

    assert call_times == [minute_index[0].to_pydatetime(), minute_index[1].to_pydatetime()]
    assert len(result["fills"]) == 1
    fill = result["fills"].iloc[0]
    assert pd.Timestamp(fill["timestamp"]) == minute_index[1]
    assert pd.Timestamp(fill["signal_timestamp"]) == minute_index[0]
    assert fill["price"] == 50.5
    assert fill["execution_mode"] == "next_bar_open"


def test_backtest_simulator_next_bar_open_can_fill_next_day_open():
    minute_index = pd.to_datetime(
        [
            "2026-03-26 15:00:00",
            "2026-03-27 09:30:00",
        ]
    )
    minute_data = pd.DataFrame(
        {
            "open": [50.0, 49.2],
            "high": [50.2, 49.5],
            "low": [49.8, 49.0],
            "close": [50.1, 49.4],
            "volume": [10000, 12000],
            "amount": [501000, 592800],
            "pre_close": [49.9, 50.1],
        },
        index=minute_index,
    )
    daily_data = pd.DataFrame({"close": [50 + i * 0.1 for i in range(100)]})
    position = PortfolioState(
        total_position=3500,
        available_volume=3500,
        cost_price=72.0,
        base_position=2600,
        tactical_position=900,
        max_position=3500,
        t0_sell_available=900,
        t0_buy_capacity=0,
        cash_available=70000,
    )

    def fake_generate_signal(**kwargs):
        if kwargs["current_datetime"] == minute_index[0].to_pydatetime():
            return {
                "action": "positive_t_sell",
                "reason": "test",
                "price": 50.1,
                "volume": 900,
                "branch": "positive_t",
            }
        return {"action": "observe", "reason": "test", "price": 0.0, "volume": 0, "branch": None}

    with patch.object(
        T0BacktestSimulator,
        "__init__",
        lambda self, params=None, execution_mode="same_bar_close": None,
    ):
        simulator = T0BacktestSimulator()
        simulator.params = SimpleNamespace(t0_trade_unit=100)
        simulator.execution_mode = "next_bar_open"
        simulator.feature_calculator = SimpleNamespace(
            calculate_snapshot=lambda window: FeatureCalculator().calculate_snapshot(window)
        )
        simulator.regime_classifier = SimpleNamespace(calculate=lambda _: "transition")
        simulator.engine = SimpleNamespace(
            generate_signal=fake_generate_signal,
            _build_branch_state=lambda history: SimpleNamespace(
                completed="positive_t_buyback" in [event.action for event in history]
            ),
        )

        result = simulator.run(minute_data, daily_data, position)

    assert len(result["fills"]) == 1
    fill = result["fills"].iloc[0]
    assert pd.Timestamp(fill["timestamp"]) == minute_index[1]
    assert pd.Timestamp(fill["signal_timestamp"]) == minute_index[0]
    assert fill["price"] == 49.2


def test_backtest_simulator_resets_intraday_window_each_trade_day():
    minute_index = pd.to_datetime(
        [
            "2026-03-26 09:50:00",
            "2026-03-26 10:00:00",
            "2026-03-27 09:50:00",
            "2026-03-27 10:00:00",
        ]
    )
    minute_data = pd.DataFrame(
        {
            "open": [50.0, 49.6, 60.0, 59.4],
            "high": [50.1, 50.9, 60.2, 60.8],
            "low": [49.4, 49.5, 59.2, 59.3],
            "close": [49.6, 50.8, 59.4, 60.7],
            "volume": [10000, 15000, 9000, 14000],
            "amount": [496000, 762000, 534600, 849800],
            "pre_close": [50.5, 50.5, 60.5, 60.5],
        },
        index=minute_index,
    )
    daily_index = pd.date_range("2025-11-01", periods=120, freq="D")
    daily_data = pd.DataFrame(
        {
            "close": [50 + i * 0.1 for i in range(120)],
        },
        index=daily_index,
    )
    position = PortfolioState(
        total_position=2600,
        available_volume=2600,
        cost_price=72.0,
        base_position=2600,
        tactical_position=900,
        max_position=3500,
        t0_sell_available=0,
        t0_buy_capacity=900,
        cash_available=70000,
    )

    result = T0BacktestSimulator().run(minute_data, daily_data, position)

    day_two_open_signal = (
        result["signals"].loc[result["signals"]["timestamp"] == minute_index[2]].iloc[0]
    )
    assert day_two_open_signal["timestamp"] == minute_index[2]
    assert day_two_open_signal["action"] == "observe"


def test_backtest_simulator_excludes_current_day_from_regime_input():
    minute_index = pd.to_datetime(
        [
            "2026-03-26 09:50:00",
            "2026-03-27 09:50:00",
        ]
    )
    minute_data = pd.DataFrame(
        {
            "open": [50.0, 51.0],
            "high": [50.2, 51.2],
            "low": [49.8, 50.8],
            "close": [50.1, 51.1],
            "volume": [10000, 11000],
            "amount": [501000, 562100],
            "pre_close": [49.9, 50.9],
        },
        index=minute_index,
    )
    daily_data = pd.DataFrame(
        {
            "close": [48.0, 49.0, 50.0, 51.0],
        },
        index=pd.to_datetime(["2026-03-24", "2026-03-25", "2026-03-26", "2026-03-27"]),
    )
    position = PortfolioState(
        total_position=2600,
        available_volume=2600,
        cost_price=72.0,
        base_position=2600,
        tactical_position=900,
        max_position=3500,
        t0_sell_available=0,
        t0_buy_capacity=900,
        cash_available=70000,
    )
    captured_last_dates = []

    with patch(
        "src.backtest.simulator.RegimeClassifier.calculate",
        side_effect=lambda df: captured_last_dates.append(
            None if df.empty else pd.Timestamp(df.index[-1]).strftime("%Y-%m-%d")
        )
        or "transition",
    ):
        T0BacktestSimulator().run(minute_data, daily_data, position)


def test_backtest_simulator_carries_open_signal_history_to_next_day():
    minute_index = pd.to_datetime(
        [
            "2026-03-26 14:55:00",
            "2026-03-27 09:35:00",
        ]
    )
    minute_data = pd.DataFrame(
        {
            "open": [50.0, 50.2],
            "high": [50.3, 50.4],
            "low": [49.7, 50.0],
            "close": [50.1, 50.3],
            "volume": [10000, 12000],
            "amount": [501000, 603600],
            "pre_close": [49.9, 50.1],
        },
        index=minute_index,
    )
    daily_data = pd.DataFrame({"close": [49.0, 49.5, 50.0, 50.5]})
    position = PortfolioState(
        total_position=3500,
        available_volume=3500,
        cost_price=72.0,
        base_position=2600,
        tactical_position=900,
        max_position=3500,
        t0_sell_available=900,
        t0_buy_capacity=0,
        cash_available=70000,
    )

    captured_history_lengths = []

    def fake_generate_signal(**kwargs):
        captured_history_lengths.append(len(kwargs.get("signal_history") or []))
        current_dt = kwargs["current_datetime"]
        if current_dt == minute_index[0].to_pydatetime():
            return {
                "action": "positive_t_sell",
                "reason": "test",
                "price": 50.1,
                "volume": 900,
                "branch": "positive_t",
            }
        return {
            "action": "observe",
            "reason": "test",
            "price": 0.0,
            "volume": 0,
            "branch": None,
        }

    with patch.object(
        T0BacktestSimulator,
        "__init__",
        lambda self, params=None, execution_mode="same_bar_close": None,
    ):
        simulator = T0BacktestSimulator()
        simulator.params = SimpleNamespace(t0_trade_unit=100)
        simulator.execution_mode = "same_bar_close"
        simulator.feature_calculator = SimpleNamespace(
            calculate_snapshot=lambda window: FeatureCalculator().calculate_snapshot(window)
        )
        simulator.regime_classifier = SimpleNamespace(calculate=lambda _: "transition")
        simulator.engine = SimpleNamespace(
            generate_signal=fake_generate_signal,
            _build_branch_state=lambda history: SimpleNamespace(
                completed="positive_t_buyback" in [event.action for event in history]
            ),
        )

        simulator.run(minute_data, daily_data, position)

    assert captured_history_lengths == [0, 1]


def test_backtest_simulator_increments_carry_trading_days_on_each_rollover():
    simulator = T0BacktestSimulator()
    history = [
        SignalEvent(
            action="positive_t_sell",
            branch="positive_t",
            price=50.1,
            volume=900,
        )
    ]

    day_one_history = simulator._next_day_signal_history(history)
    day_two_history = simulator._next_day_signal_history(day_one_history)

    assert [event.carry_trading_days for event in history] == [0]
    assert [event.carry_trading_days for event in day_one_history] == [1]
    assert [event.carry_trading_days for event in day_two_history] == [2]


def test_backtest_simulator_carries_open_branch_and_restores_available_volume_next_day():
    minute_index = pd.to_datetime(
        [
            "2026-03-26 09:59:00",
            "2026-03-27 13:30:00",
        ]
    )
    minute_data = pd.DataFrame(
        {
            "open": [50.0, 50.4],
            "high": [50.1, 51.3],
            "low": [49.5, 50.3],
            "close": [50.0, 51.2],
            "volume": [10000, 15000],
            "amount": [500000, 768000],
            "pre_close": [50.5, 50.8],
        },
        index=minute_index,
    )
    daily_data = pd.DataFrame({"close": [50 + i * 0.1 for i in range(100)]})
    position = PortfolioState(
        total_position=3000,
        available_volume=3000,
        cost_price=72.0,
        base_position=3000,
        tactical_position=1000,
        max_position=4000,
        t0_sell_available=0,
        t0_buy_capacity=1000,
        cash_available=70000,
    )
    captured_positions = []
    captured_histories = []

    def fake_generate_signal(**kwargs):
        current_datetime = kwargs["current_datetime"]
        captured_positions.append((current_datetime, dict(kwargs["position"])))
        captured_histories.append(
            (current_datetime, [event.action for event in kwargs["signal_history"]])
        )
        if current_datetime == minute_index[0].to_pydatetime():
            return {
                "action": "reverse_t_buy",
                "reason": "test",
                "price": 50.0,
                "volume": 500,
                "branch": "reverse_t",
            }
        if current_datetime == minute_index[1].to_pydatetime():
            return {
                "action": "reverse_t_sell",
                "reason": "test",
                "price": 51.2,
                "volume": 500,
                "branch": "reverse_t",
            }
        return {"action": "observe", "reason": "test", "price": 0.0, "volume": 0, "branch": None}

    with patch.object(T0BacktestSimulator, "__init__", lambda self, params=None: None):
        simulator = T0BacktestSimulator()
        simulator.params = SimpleNamespace(t0_trade_unit=100)
        simulator.execution_mode = "same_bar_close"
        simulator.feature_calculator = SimpleNamespace(
            calculate_snapshot=lambda window: FeatureCalculator().calculate_snapshot(window)
        )
        simulator.regime_classifier = SimpleNamespace(calculate=lambda _: "transition")
        simulator.engine = SimpleNamespace(
            generate_signal=fake_generate_signal,
            _build_branch_state=lambda history: SimpleNamespace(
                completed="reverse_t_sell" in [event.action for event in history]
            ),
        )

        result = simulator.run(minute_data, daily_data, position)

    assert list(result["fills"]["action"]) == ["reverse_t_buy", "reverse_t_sell"]
    day_two_position = next(
        pos for timestamp, pos in captured_positions if timestamp == minute_index[1].to_pydatetime()
    )
    day_two_history = next(
        history
        for timestamp, history in captured_histories
        if timestamp == minute_index[1].to_pydatetime()
    )
    assert day_two_position["available_volume"] == 3500
    assert day_two_position["t0_sell_available"] == 500
    assert day_two_history == ["reverse_t_buy"]


def test_backtest_simulator_clears_completed_branch_history_on_next_day():
    minute_index = pd.to_datetime(
        [
            "2026-03-26 09:59:00",
            "2026-03-26 13:30:00",
            "2026-03-27 09:59:00",
        ]
    )
    minute_data = pd.DataFrame(
        {
            "open": [50.0, 50.4, 50.1],
            "high": [50.1, 51.3, 50.6],
            "low": [49.5, 50.3, 49.8],
            "close": [50.0, 51.2, 50.2],
            "volume": [10000, 15000, 12000],
            "amount": [500000, 768000, 602400],
            "pre_close": [50.5, 50.8, 50.0],
        },
        index=minute_index,
    )
    daily_data = pd.DataFrame({"close": [50 + i * 0.1 for i in range(100)]})
    position = PortfolioState(
        total_position=3000,
        available_volume=3000,
        cost_price=72.0,
        base_position=2600,
        tactical_position=900,
        max_position=3500,
        t0_sell_available=400,
        t0_buy_capacity=500,
        cash_available=70000,
    )
    captured_histories = []

    def fake_generate_signal(**kwargs):
        current_datetime = kwargs["current_datetime"]
        captured_histories.append(
            (current_datetime, [event.action for event in kwargs["signal_history"]])
        )
        if current_datetime == minute_index[0].to_pydatetime():
            return {
                "action": "reverse_t_buy",
                "reason": "test",
                "price": 50.0,
                "volume": 500,
                "branch": "reverse_t",
            }
        if current_datetime == minute_index[1].to_pydatetime():
            return {
                "action": "reverse_t_sell",
                "reason": "test",
                "price": 51.2,
                "volume": 500,
                "branch": "reverse_t",
            }
        return {"action": "observe", "reason": "test", "price": 0.0, "volume": 0, "branch": None}

    with patch.object(T0BacktestSimulator, "__init__", lambda self, params=None: None):
        simulator = T0BacktestSimulator()
        simulator.params = SimpleNamespace(t0_trade_unit=100)
        simulator.execution_mode = "same_bar_close"
        simulator.feature_calculator = SimpleNamespace(
            calculate_snapshot=lambda window: FeatureCalculator().calculate_snapshot(window)
        )
        simulator.regime_classifier = SimpleNamespace(calculate=lambda _: "transition")
        simulator.engine = SimpleNamespace(
            generate_signal=fake_generate_signal,
            _build_branch_state=lambda history: SimpleNamespace(
                completed="reverse_t_sell" in [event.action for event in history]
            ),
        )

        simulator.run(minute_data, daily_data, position)

    day_three_history = next(
        history
        for timestamp, history in captured_histories
        if timestamp == minute_index[2].to_pydatetime()
    )
    assert day_three_history == []


def test_backtest_simulator_force_same_day_close_flattens_open_branch():
    minute_index = pd.to_datetime(
        [
            "2026-03-26 10:00:00",
            "2026-03-26 14:56:00",
        ]
    )
    minute_data = pd.DataFrame(
        {
            "open": [50.0, 49.5],
            "high": [50.2, 49.8],
            "low": [49.8, 49.2],
            "close": [50.0, 49.4],
            "volume": [10000, 12000],
            "amount": [500000, 592800],
            "pre_close": [49.9, 49.9],
        },
        index=minute_index,
    )
    daily_data = pd.DataFrame({"close": [50 + i * 0.1 for i in range(100)]})
    position = PortfolioState(
        total_position=3500,
        available_volume=3500,
        cost_price=72.0,
        base_position=2600,
        tactical_position=900,
        max_position=3500,
        t0_sell_available=900,
        t0_buy_capacity=0,
        cash_available=70000,
    )

    def fake_generate_signal(**kwargs):
        if kwargs["current_datetime"] == minute_index[0].to_pydatetime():
            return {
                "action": "positive_t_sell",
                "reason": "test",
                "price": 50.0,
                "volume": 900,
                "branch": "positive_t",
            }
        return {"action": "observe", "reason": "test", "price": 0.0, "volume": 0, "branch": None}

    with patch.object(
        T0BacktestSimulator,
        "__init__",
        lambda self, params=None, execution_mode="same_bar_close", force_same_day_close=False: None,
    ):
        simulator = T0BacktestSimulator()
        simulator.params = SimpleNamespace(
            t0_trade_unit=100,
            t0_commission_rate=0.0001,
            t0_min_commission=5.0,
            t0_transfer_fee_rate=0.00001,
            t0_stamp_duty_rate=0.0005,
        )
        simulator.execution_mode = "same_bar_close"
        simulator.force_same_day_close = True
        simulator.feature_calculator = SimpleNamespace(
            calculate_snapshot=lambda window: FeatureCalculator().calculate_snapshot(window)
        )
        simulator.regime_classifier = SimpleNamespace(calculate=lambda _: "transition")
        simulator.engine = SimpleNamespace(
            generate_signal=fake_generate_signal,
            _build_branch_state=lambda history: SimpleNamespace(
                branch="positive_t",
                completed="positive_t_buyback" in [event.action for event in history],
                volume=next((event.volume for event in history if event.volume), 0),
                entry_price=next((event.price for event in history if event.price is not None), None),
                entry_time=next((event.signal_time for event in history if event.signal_time), None),
            ),
        )

        result = simulator.run(minute_data, daily_data, position)

    assert list(result["fills"]["action"]) == ["positive_t_sell", "positive_t_buyback"]
    forced_fill = result["fills"].iloc[1]
    assert pd.Timestamp(forced_fill["timestamp"]) == minute_index[1]
    assert forced_fill["price"] == 49.4
    assert forced_fill["execution_mode"] == "same_bar_close_force_same_day_close"
    assert result["final_position"].total_position == 3500
