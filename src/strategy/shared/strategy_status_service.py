"""T0 strategy status service for CMS and runtime diagnostics."""

from datetime import date, datetime
from typing import Any, Dict

from src.infrastructure.config import settings
from src.infrastructure.logger_config import logger
from src.strategy.core.params import T0StrategyParams
from src.strategy.strategies.t0.data_fetcher import DataFetcher
from src.strategy.strategies.t0.feature_calculator import FeatureCalculator
from src.strategy.strategies.t0.position_syncer import PositionSyncer
from src.strategy.strategies.t0.regime_identifier import RegimeIdentifier


class StrategyStatusService:
    """Provide structured runtime status for the T0 strategy."""

    def __init__(self):
        self.stock_code = settings.t0_stock_code
        self.params = T0StrategyParams.from_settings(settings)
        self.data_fetcher = DataFetcher()
        self.regime_identifier = RegimeIdentifier()
        self.feature_calculator = FeatureCalculator()
        self.position_syncer = PositionSyncer()

    def get_strategy_status(self) -> Dict:
        """Build a strategy status snapshot for API consumers."""
        try:
            trade_date = date.today()
            current_time = datetime.now().time()
            as_of_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            minute_data = self.data_fetcher.fetch_minute_data(
                self.stock_code, trade_date, realtime=True
            )
            if minute_data is None:
                return self._error_response("分钟数据获取失败", as_of_time)

            daily_data = self.data_fetcher.fetch_daily_data(self.stock_code, days=100)
            if daily_data is None:
                return self._error_response("日线数据获取失败", as_of_time)

            regime = self.regime_identifier.identify_regime(daily_data, trade_date)
            branch_priority = self._get_branch_priority(regime)

            features = self.feature_calculator.calculate_snapshot(minute_data)
            if features is None:
                return self._error_response("特征计算失败", as_of_time)

            feature_dict = features.to_dict() if hasattr(features, "to_dict") else dict(features)
            position = self.position_syncer.load_portfolio_state()
            position_dict = position.to_dict() if hasattr(position, "to_dict") else dict(position)
            time_windows = self._check_time_windows(current_time)
            conditions = self._check_strategy_conditions(feature_dict, position_dict, time_windows)

            return self._to_json_safe(
                {
                    "status": "ok",
                    "as_of_time": as_of_time,
                    "stock_code": self.stock_code,
                    "market": {
                        "regime": regime,
                        "branch_priority": branch_priority,
                    },
                    "features": {
                        "day_open": feature_dict.get("day_open", 0),
                        "prev_close": feature_dict.get("prev_close", 0),
                        "open_gap_pct": feature_dict.get("open_gap_pct", 0),
                        "current_close": feature_dict.get("current_close", 0),
                        "high_so_far": feature_dict.get("high_so_far", 0),
                        "low_so_far": feature_dict.get("low_so_far", 0),
                        "vwap": feature_dict.get("vwap", 0),
                        "rise_pct": self._calculate_rise_pct(feature_dict),
                        "pullback_pct": self._calculate_pullback_pct(feature_dict),
                        "bounce_pct": feature_dict.get("bounce_from_low", 0),
                        "close_vs_vwap_pct": feature_dict.get("close_vs_vwap", 0),
                        "fake_breakout_score": feature_dict.get("fake_breakout_score", 0),
                        "absorption_score": feature_dict.get("absorption_score", 0),
                    },
                    "position": {
                        "total": position_dict.get("total_position", 0),
                        "available": position_dict.get("available_volume", 0),
                        "cost_price": position_dict.get("cost_price", 0),
                        "base": position_dict.get("base_position", self.params.t0_base_position),
                        "tactical": position_dict.get(
                            "tactical_position", self.params.t0_tactical_position
                        ),
                        "max": position_dict.get(
                            "max_position",
                            self.params.t0_base_position + self.params.t0_tactical_position,
                        ),
                        "t0_sell_available": position_dict.get("t0_sell_available", 0),
                        "t0_buy_capacity": position_dict.get("t0_buy_capacity", 0),
                        "position_version": position_dict.get("position_version", 0),
                    },
                    "time_windows": time_windows,
                    "conditions": conditions,
                }
            )

        except Exception as e:
            logger.error(f"获取策略状态失败: {e}", exc_info=True)
            return self._error_response(
                f"系统异常: {str(e)}", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

    def _check_time_windows(self, current_time) -> Dict:
        return {
            "current_time": current_time.strftime("%H:%M:%S"),
            "positive_sell": {
                "window": f"{self.params.t0_positive_sell_start_time}-{self.params.t0_positive_sell_end_time}",
                "active": self._within_window(
                    current_time,
                    self.params.t0_positive_sell_start_time,
                    self.params.t0_positive_sell_end_time,
                ),
            },
            "positive_buyback": {
                "window": f"{self.params.t0_positive_buyback_start_time}-{self.params.t0_positive_buyback_end_time}",
                "active": self._within_window(
                    current_time,
                    self.params.t0_positive_buyback_start_time,
                    self.params.t0_positive_buyback_end_time,
                ),
            },
            "reverse_buy": {
                "window": f"{self.params.t0_reverse_buy_start_time}-{self.params.t0_reverse_buy_end_time}",
                "active": self._within_window(
                    current_time,
                    self.params.t0_reverse_buy_start_time,
                    self.params.t0_reverse_buy_end_time,
                ),
            },
            "reverse_sell": {
                "window": f"{self.params.t0_reverse_sell_start_time}-{self.params.t0_reverse_sell_end_time}",
                "active": self._within_window(
                    current_time,
                    self.params.t0_reverse_sell_start_time,
                    self.params.t0_reverse_sell_end_time,
                ),
            },
        }

    def _check_strategy_conditions(
        self, features: Dict, position: Dict, time_windows: Dict
    ) -> Dict:
        day_open = features.get("day_open", 0)
        prev_close = features.get("prev_close", day_open)
        open_gap_pct = features.get("open_gap_pct", self._calculate_open_gap_pct(features))
        current_close = features.get("current_close", 0)
        high_so_far = features.get("high_so_far", 0)
        vwap = features.get("vwap", 0)
        bounce = features.get("bounce_from_low", 0)
        close_vs_vwap = features.get("close_vs_vwap", 0)
        absorption = features.get("absorption_score", 0)
        rise_reference = max(day_open, prev_close) if prev_close > 0 else day_open

        rise = ((high_so_far - rise_reference) / rise_reference * 100) if rise_reference > 0 else 0
        pullback = ((high_so_far - current_close) / high_so_far * 100) if high_so_far > 0 else 0

        t0_sell_available = position.get("t0_sell_available", 0)
        t0_buy_capacity = position.get("t0_buy_capacity", 0)
        gap_down_limit = self.params.t0_positive_sell_gap_down_limit
        gap_check = {
            "name": "开盘缺口过滤未启用",
            "passed": True,
            "value": round(open_gap_pct, 2),
        }
        gap_check_passed = True
        if gap_down_limit is not None:
            gap_check = {
                "name": f"开盘缺口 > {gap_down_limit}%",
                "passed": open_gap_pct > gap_down_limit,
                "value": round(open_gap_pct, 2),
            }
            gap_check_passed = gap_check["passed"]

        return {
            "positive_t_sell": {
                "checks": [
                    {
                        "name": "时间窗口",
                        "passed": time_windows["positive_sell"]["active"],
                        "value": time_windows["current_time"],
                    },
                    {
                        "name": f"涨幅 >= {self.params.t0_positive_sell_min_rise}%",
                        "passed": rise >= self.params.t0_positive_sell_min_rise,
                        "value": round(rise, 2),
                    },
                    gap_check,
                    {
                        "name": f"回撤 >= {self.params.t0_positive_sell_min_pullback}%",
                        "passed": pullback >= self.params.t0_positive_sell_min_pullback,
                        "value": round(pullback, 2),
                    },
                    {
                        "name": "价格 < VWAP",
                        "passed": current_close < vwap,
                        "value": f"{current_close:.2f} vs {vwap:.2f}",
                    },
                    {
                        "name": "T+0可卖 > 0",
                        "passed": t0_sell_available > 0,
                        "value": t0_sell_available,
                    },
                ],
                "all_passed": all(
                    [
                        time_windows["positive_sell"]["active"],
                        rise >= self.params.t0_positive_sell_min_rise,
                        gap_check_passed,
                        pullback >= self.params.t0_positive_sell_min_pullback,
                        current_close < vwap,
                        t0_sell_available > 0,
                    ]
                ),
            },
            "reverse_t_buy": {
                "checks": [
                    {
                        "name": "时间窗口",
                        "passed": time_windows["reverse_buy"]["active"],
                        "value": time_windows["current_time"],
                    },
                    {
                        "name": f"反弹 >= {self.params.t0_reverse_buy_min_bounce}%",
                        "passed": bounce >= self.params.t0_reverse_buy_min_bounce,
                        "value": round(bounce, 2),
                    },
                    {
                        "name": "价格 vs VWAP >= -0.5%",
                        "passed": close_vs_vwap >= -0.5,
                        "value": round(close_vs_vwap, 2),
                    },
                    {
                        "name": "吸收分数 >= 0.6",
                        "passed": absorption >= 0.6,
                        "value": round(absorption, 2),
                    },
                    {
                        "name": "T+0可买 > 0",
                        "passed": t0_buy_capacity > 0,
                        "value": t0_buy_capacity,
                    },
                ],
                "all_passed": all(
                    [
                        time_windows["reverse_buy"]["active"],
                        bounce >= self.params.t0_reverse_buy_min_bounce,
                        close_vs_vwap >= -0.5,
                        absorption >= 0.6,
                        t0_buy_capacity > 0,
                    ]
                ),
            },
        }

    def _calculate_rise_pct(self, features: Dict) -> float:
        day_open = features.get("day_open", 0)
        prev_close = features.get("prev_close", day_open)
        high_so_far = features.get("high_so_far", 0)
        rise_reference = max(day_open, prev_close) if prev_close > 0 else day_open
        if rise_reference > 0:
            return round((high_so_far - rise_reference) / rise_reference * 100, 2)
        return 0.0

    def _calculate_pullback_pct(self, features: Dict) -> float:
        high_so_far = features.get("high_so_far", 0)
        current_close = features.get("current_close", 0)
        if high_so_far > 0:
            return round((high_so_far - current_close) / high_so_far * 100, 2)
        return 0.0

    def _calculate_open_gap_pct(self, features: Dict) -> float:
        day_open = features.get("day_open", 0)
        prev_close = features.get("prev_close", day_open)
        if prev_close > 0:
            return round((day_open - prev_close) / prev_close * 100, 2)
        return 0.0

    def _within_window(self, current_time, start: str, end: str) -> bool:
        return self.params.parse_time(start) <= current_time <= self.params.parse_time(end)

    def _get_branch_priority(self, regime: str) -> list:
        if regime == "downtrend":
            return ["positive_t", "reverse_t"]
        if regime == "uptrend":
            return ["reverse_t"]
        return ["reverse_t", "positive_t"]

    def _error_response(self, error_msg: str, as_of_time: str) -> Dict:
        return {
            "status": "error",
            "error": error_msg,
            "as_of_time": as_of_time,
        }

    def _to_json_safe(self, value: Any) -> Any:
        """Normalize numpy/pandas scalars into native JSON-safe values."""
        item = getattr(value, "item", None)
        if callable(item):
            return item()
        if isinstance(value, dict):
            return {key: self._to_json_safe(val) for key, val in value.items()}
        if isinstance(value, list):
            return [self._to_json_safe(val) for val in value]
        if isinstance(value, tuple):
            return [self._to_json_safe(val) for val in value]
        return value
