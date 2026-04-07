from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

import src.strategy.strategies.t0.strategy_engine as strategy_engine_module
from src.strategy.core.models import FeatureSnapshot, PortfolioState, StrategyDecision


class _FakeRedisClient:
    def ping(self) -> None:
        return None

    def setex(self, key: str, ttl: int, value: str) -> None:
        return None


def _patch_engine_dependencies(monkeypatch, data_fetcher_cls) -> None:
    monkeypatch.setattr(strategy_engine_module, "DataFetcher", data_fetcher_cls)
    monkeypatch.setattr(
        strategy_engine_module,
        "T0StrategyParams",
        SimpleNamespace(from_settings=lambda _: object()),
    )
    monkeypatch.setattr(strategy_engine_module, "T0StrategyKernel", lambda params: object())
    monkeypatch.setattr(strategy_engine_module, "PositionSyncer", lambda: object())
    monkeypatch.setattr(strategy_engine_module, "StrategySignalRepository", lambda: object())

    notifier = MagicMock()
    monkeypatch.setattr(strategy_engine_module, "FeishuNotifier", lambda: notifier)

    monkeypatch.setattr(strategy_engine_module.redis, "Redis", lambda **kwargs: _FakeRedisClient())


def test_build_market_data_provider_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(
        strategy_engine_module,
        "settings",
        SimpleNamespace(t0_market_data_provider_enabled=False),
    )
    monkeypatch.setattr(strategy_engine_module, "xtdata", object(), raising=False)

    provider = strategy_engine_module.build_market_data_provider()

    assert provider is None


def test_build_market_data_provider_returns_none_when_xtdata_unavailable(monkeypatch):
    monkeypatch.setattr(
        strategy_engine_module,
        "settings",
        SimpleNamespace(t0_market_data_provider_enabled=True),
    )
    monkeypatch.setattr(strategy_engine_module, "xtdata", None, raising=False)

    provider = strategy_engine_module.build_market_data_provider()

    assert provider is None


def test_strategy_engine_injects_provider_into_data_fetcher_and_subscribes(monkeypatch):
    fake_provider = MagicMock()
    monkeypatch.setattr(
        strategy_engine_module,
        "build_market_data_provider",
        lambda xtdata_client=None: fake_provider,
    )

    captured_provider = {}

    class FakeDataFetcher:
        def __init__(
            self,
            cache_dir: str = "./cache",
            intraday_period=None,
            market_data_provider=None,
            market_data_gateway=None,
        ):
            captured_provider["provider"] = market_data_provider

    _patch_engine_dependencies(monkeypatch, FakeDataFetcher)

    monkeypatch.setattr(
        strategy_engine_module,
        "settings",
        SimpleNamespace(
            t0_stock_code="601138.SH",
            t0_output_dir="./output",
            t0_market_data_snapshot_interval_seconds=10,
            redis_host="localhost",
            redis_port=6379,
            redis_password=None,
        ),
    )

    strategy_engine_module.StrategyEngine()

    assert captured_provider["provider"] is fake_provider
    fake_provider.subscribe_snapshot.assert_called_once()

    _, kwargs = fake_provider.subscribe_snapshot.call_args
    assert kwargs["stock_codes"] == ["601138.SH"]
    assert kwargs["interval_seconds"] == 3
    assert callable(kwargs["callback"])


def test_strategy_engine_without_provider_still_initializes_data_fetcher(monkeypatch):
    monkeypatch.setattr(
        strategy_engine_module,
        "build_market_data_provider",
        lambda xtdata_client=None: None,
    )

    captured_provider = {}

    class FakeDataFetcher:
        def __init__(
            self,
            cache_dir: str = "./cache",
            intraday_period=None,
            market_data_provider=None,
            market_data_gateway=None,
        ):
            captured_provider["provider"] = market_data_provider

    _patch_engine_dependencies(monkeypatch, FakeDataFetcher)

    monkeypatch.setattr(
        strategy_engine_module,
        "settings",
        SimpleNamespace(
            t0_stock_code="601138.SH",
            t0_output_dir="./output",
            t0_market_data_snapshot_interval_seconds=2,
            redis_host="localhost",
            redis_port=6379,
            redis_password=None,
        ),
    )

    strategy_engine_module.StrategyEngine()

    assert captured_provider["provider"] is None


def test_strategy_engine_run_once_delegates_strategy_logic_to_kernel(monkeypatch):
    minute_data = pd.DataFrame(
        {
            "open": [10.0, 10.1],
            "high": [10.2, 10.4],
            "low": [9.9, 10.0],
            "close": [10.1, 10.3],
            "volume": [1000, 1200],
            "pre_close": [9.8, 9.8],
        },
        index=pd.to_datetime(["2026-03-26 09:30:00", "2026-03-26 09:31:00"]),
    )
    daily_data = pd.DataFrame(
        {"close": [9.5, 9.7, 9.8]},
        index=pd.to_datetime(["2026-03-21", "2026-03-24", "2026-03-25"]),
    )
    features = FeatureSnapshot(
        latest_bar_time="2026-03-26 09:31:00",
        current_close=10.3,
        vwap=10.15,
        high_so_far=10.4,
        low_so_far=9.9,
        fake_breakout_score=0.1,
        absorption_score=0.7,
        day_open=10.0,
        close_vs_vwap=1.48,
        distance_from_high=-0.96,
        bounce_from_low=4.04,
        prev_close=9.8,
        open_gap_pct=2.04,
    )
    position = PortfolioState(
        total_position=3500,
        available_volume=3500,
        cost_price=72.68,
        base_position=2600,
        tactical_position=900,
        max_position=3500,
        t0_sell_available=900,
        t0_buy_capacity=0,
    )
    signal = StrategyDecision(
        action="reverse_t_sell",
        reason="测试信号",
        price=10.3,
        volume=900,
        branch="reverse_t",
    )
    evaluate_calls = {}
    saved_signal = {}

    class FakeDataFetcher:
        def __init__(self, cache_dir: str = "./cache", intraday_period=None, market_data_provider=None, market_data_gateway=None):
            self.market_data_provider = market_data_provider
            self.market_data_gateway = market_data_gateway

        def fetch_minute_data(self, stock_code: str, trade_date: date, retry: int = 3, realtime: bool = False, snapshot=None):
            return minute_data

        def fetch_daily_data(self, stock_code: str, days: int = 100):
            return daily_data

        def fetch_realtime_snapshot(self, stock_code: str):
            return {"time": "2026-03-26 09:31:30", "price": 10.35, "high": 10.4, "low": 9.9}

    class FakeKernel:
        def evaluate(self, **kwargs):
            evaluate_calls.update(kwargs)
            return {
                "regime": "transition",
                "features": features,
                "position": position,
                "signal": signal,
            }

    class FakePositionSyncer:
        def publish_pending_events(self, limit: int) -> None:
            return None

        def load_position(self):
            return {"total_position": 3500}

        def to_portfolio_state(self, position_state):
            return position

    class FakeRepository:
        def load_today_history(self, trade_date: date):
            return []

        def save_signal(self, **kwargs):
            saved_signal.update(kwargs)

    notifier = MagicMock()

    monkeypatch.setattr(strategy_engine_module, "build_market_data_provider", lambda xt=None: None)
    monkeypatch.setattr(strategy_engine_module, "build_xtdata_client", lambda: None)
    monkeypatch.setattr(strategy_engine_module, "DataFetcher", FakeDataFetcher)
    monkeypatch.setattr(
        strategy_engine_module,
        "T0StrategyParams",
        SimpleNamespace(from_settings=lambda _: object()),
    )
    monkeypatch.setattr(strategy_engine_module, "T0StrategyKernel", lambda params: FakeKernel())
    monkeypatch.setattr(strategy_engine_module, "PositionSyncer", lambda: FakePositionSyncer())
    monkeypatch.setattr(strategy_engine_module, "StrategySignalRepository", lambda: FakeRepository())
    monkeypatch.setattr(strategy_engine_module, "FeishuNotifier", lambda: notifier)
    monkeypatch.setattr(strategy_engine_module.redis, "Redis", lambda **kwargs: _FakeRedisClient())
    monkeypatch.setattr(
        strategy_engine_module,
        "settings",
        SimpleNamespace(
            t0_stock_code="601138.SH",
            t0_output_dir="./output",
            t0_market_data_snapshot_interval_seconds=2,
            redis_t0_signal_key="t0_signal",
            redis_t0_signal_ttl=60,
            t0_save_signal_card=False,
            t0_base_position=2600,
            t0_tactical_position=900,
        ),
    )

    engine = strategy_engine_module.StrategyEngine()
    signal_card = engine.run_once()

    assert evaluate_calls["minute_data"] is minute_data
    assert evaluate_calls["daily_data"] is daily_data
    assert evaluate_calls["position"] == position
    assert evaluate_calls["signal_history"] == []
    assert signal_card["regime"] == "transition"
    assert signal_card["signal"]["action"] == "reverse_t_sell"
    assert signal_card["market"]["time"] == "2026-03-26 09:31:30"
    assert saved_signal["signal"] == signal
    notifier.notify_t0_signal.assert_called_once()
