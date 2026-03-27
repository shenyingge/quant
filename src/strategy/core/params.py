"""平台无关的策略参数。"""

from dataclasses import dataclass
from datetime import datetime, time


@dataclass(frozen=True)
class T0StrategyParams:
    t0_base_position: int = 2600
    t0_tactical_position: int = 900
    t0_trade_unit: int = 100
    t0_max_trade_value: float = 70000
    t0_intraday_bar_period: str = "1m"
    t0_commission_rate: float = 0.0
    t0_min_commission: float = 0.0
    t0_transfer_fee_rate: float = 0.0
    t0_stamp_duty_rate: float = 0.0
    t0_min_hold_minutes: int = 20
    t0_positive_sell_start_time: str = "09:45"
    t0_positive_sell_end_time: str = "11:20"
    t0_positive_buyback_start_time: str = "13:30"
    t0_positive_buyback_end_time: str = "14:56"
    t0_reverse_buy_start_time: str = "09:50"
    t0_reverse_buy_end_time: str = "13:20"
    t0_reverse_sell_start_time: str = "13:20"
    t0_reverse_sell_end_time: str = "14:56"
    t0_positive_sell_min_rise: float = 1.0
    t0_positive_sell_min_pullback: float = 0.5
    t0_reverse_buy_min_drop: float = 1.5
    t0_reverse_buy_min_bounce: float = 0.4
    t0_reverse_sell_min_profit: float = 1.2
    t0_reverse_sell_max_vwap_distance: float = 0.5

    @classmethod
    def from_settings(cls, settings_obj):
        return cls(
            t0_base_position=settings_obj.t0_base_position,
            t0_tactical_position=settings_obj.t0_tactical_position,
            t0_trade_unit=settings_obj.t0_trade_unit,
            t0_max_trade_value=settings_obj.t0_max_trade_value,
            t0_intraday_bar_period=getattr(settings_obj, "t0_intraday_bar_period", "1m"),
            t0_commission_rate=getattr(settings_obj, "t0_commission_rate", 0.0),
            t0_min_commission=getattr(settings_obj, "t0_min_commission", 0.0),
            t0_transfer_fee_rate=getattr(settings_obj, "t0_transfer_fee_rate", 0.0),
            t0_stamp_duty_rate=getattr(settings_obj, "t0_stamp_duty_rate", 0.0),
            t0_min_hold_minutes=settings_obj.t0_min_hold_minutes,
            t0_positive_sell_start_time=settings_obj.t0_positive_sell_start_time,
            t0_positive_sell_end_time=settings_obj.t0_positive_sell_end_time,
            t0_positive_buyback_start_time=settings_obj.t0_positive_buyback_start_time,
            t0_positive_buyback_end_time=settings_obj.t0_positive_buyback_end_time,
            t0_reverse_buy_start_time=settings_obj.t0_reverse_buy_start_time,
            t0_reverse_buy_end_time=settings_obj.t0_reverse_buy_end_time,
            t0_reverse_sell_start_time=settings_obj.t0_reverse_sell_start_time,
            t0_reverse_sell_end_time=settings_obj.t0_reverse_sell_end_time,
            t0_positive_sell_min_rise=settings_obj.t0_positive_sell_min_rise,
            t0_positive_sell_min_pullback=settings_obj.t0_positive_sell_min_pullback,
            t0_reverse_buy_min_drop=settings_obj.t0_reverse_buy_min_drop,
            t0_reverse_buy_min_bounce=settings_obj.t0_reverse_buy_min_bounce,
            t0_reverse_sell_min_profit=settings_obj.t0_reverse_sell_min_profit,
            t0_reverse_sell_max_vwap_distance=settings_obj.t0_reverse_sell_max_vwap_distance,
        )

    def parse_time(self, value: str) -> time:
        return datetime.strptime(value, "%H:%M").time()
