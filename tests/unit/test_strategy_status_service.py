import json

import numpy as np

from src.strategy.core.models import FeatureSnapshot, PortfolioState
from src.strategy.core.params import T0StrategyParams
from src.strategy.strategies.t0.strategy_status_service import StrategyStatusService


class FakeDataFetcher:
    def fetch_minute_data(self, stock_code, trade_date, realtime=True):
        return {"stock_code": stock_code, "trade_date": trade_date.isoformat(), "realtime": realtime}

    def fetch_daily_data(self, stock_code, days=100):
        return {"stock_code": stock_code, "days": days}


class FakeRegimeIdentifier:
    def identify_regime(self, daily_data, trade_date):
        return "downtrend"


class FakeFeatureCalculator:
    def calculate_snapshot(self, minute_data):
        return FeatureSnapshot(
            day_open=np.float64(10.0),
            current_close=np.float64(9.85),
            high_so_far=np.float64(10.5),
            low_so_far=np.float64(9.7),
            latest_bar_time="2026-04-07 10:30:00",
            vwap=np.float64(10.1),
            close_vs_vwap=np.float64(-2.48),
            distance_from_high=np.float64(-6.19),
            bounce_from_low=np.float64(1.55),
            fake_breakout_score=np.float64(0.8),
            absorption_score=np.float64(0.65),
        )


class FakePositionSyncer:
    def load_portfolio_state(self):
        return PortfolioState(
            total_position=4000,
            available_volume=2000,
            cost_price=10.2,
            base_position=3100,
            tactical_position=900,
            max_position=4000,
            t0_sell_available=900,
            t0_buy_capacity=100,
            cash_available=10000.0,
            position_version=3,
        )


def _build_service() -> StrategyStatusService:
    service = StrategyStatusService.__new__(StrategyStatusService)
    service.stock_code = "000001.SZ"
    service.params = T0StrategyParams()
    service.data_fetcher = FakeDataFetcher()
    service.regime_identifier = FakeRegimeIdentifier()
    service.feature_calculator = FakeFeatureCalculator()
    service.position_syncer = FakePositionSyncer()
    return service


def test_get_strategy_status_returns_json_serializable_payload():
    service = _build_service()

    result = service.get_strategy_status()
    payload = json.dumps(result, ensure_ascii=False)

    assert isinstance(result["features"]["day_open"], float)
    assert isinstance(result["conditions"]["positive_t_sell"]["checks"][1]["passed"], bool)
    assert isinstance(result["conditions"]["reverse_t_buy"]["all_passed"], bool)
    assert json.loads(payload)["status"] == "ok"
