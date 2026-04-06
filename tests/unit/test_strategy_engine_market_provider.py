from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import src.strategy.strategies.t0.strategy_engine as strategy_engine_module


class _FakeRedisClient:
    def ping(self) -> None:
        return None


def _patch_engine_dependencies(monkeypatch, data_fetcher_cls) -> None:
    monkeypatch.setattr(strategy_engine_module, "DataFetcher", data_fetcher_cls)
    monkeypatch.setattr(strategy_engine_module, "RegimeIdentifier", lambda: object())
    monkeypatch.setattr(strategy_engine_module, "FeatureCalculator", lambda: object())
    monkeypatch.setattr(strategy_engine_module, "SignalGenerator", lambda: object())
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
    monkeypatch.setattr(strategy_engine_module, "build_market_data_provider", lambda: fake_provider)

    captured_provider = {}

    class FakeDataFetcher:
        def __init__(self, cache_dir: str = "./cache", intraday_period=None, market_data_provider=None):
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
    monkeypatch.setattr(strategy_engine_module, "build_market_data_provider", lambda: None)

    captured_provider = {}

    class FakeDataFetcher:
        def __init__(self, cache_dir: str = "./cache", intraday_period=None, market_data_provider=None):
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
