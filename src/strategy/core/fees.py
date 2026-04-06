from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any


BROKER_CENT = Decimal("0.01")


@dataclass(frozen=True)
class TradingFeeSchedule:
    commission_rate: float = 0.0001
    min_commission: float = 5.0
    transfer_fee_rate: float = 0.00001
    stamp_duty_rate: float = 0.0005

    @classmethod
    def from_t0_params(cls, params_obj: Any) -> "TradingFeeSchedule":
        return cls(
            commission_rate=float(
                getattr(params_obj, "t0_commission_rate", cls.commission_rate) or 0.0
            ),
            min_commission=float(
                getattr(params_obj, "t0_min_commission", cls.min_commission) or 0.0
            ),
            transfer_fee_rate=float(
                getattr(params_obj, "t0_transfer_fee_rate", cls.transfer_fee_rate) or 0.0
            ),
            stamp_duty_rate=float(
                getattr(params_obj, "t0_stamp_duty_rate", cls.stamp_duty_rate) or 0.0
            ),
        )

    def estimate_roundtrip(
        self,
        *,
        buy_price: float,
        sell_price: float,
        volume: int,
    ) -> dict[str, float]:
        buy_notional = max(float(buy_price) * int(volume), 0.0)
        sell_notional = max(float(sell_price) * int(volume), 0.0)
        buy_total_fee = self._calculate_leg_total_fee(side="BUY", notional=buy_notional)
        sell_total_fee = self._calculate_leg_total_fee(side="SELL", notional=sell_notional)
        gross_pnl = sell_notional - buy_notional
        net_pnl = (sell_notional - sell_total_fee) - (buy_notional + buy_total_fee)
        return {
            "buy_notional": round(buy_notional, 6),
            "sell_notional": round(sell_notional, 6),
            "buy_total_fee": round(buy_total_fee, 6),
            "sell_total_fee": round(sell_total_fee, 6),
            "total_fee": round(buy_total_fee + sell_total_fee, 6),
            "gross_pnl": round(gross_pnl, 6),
            "net_pnl": round(net_pnl, 6),
        }

    def _calculate_leg_total_fee(self, *, side: str, notional: float) -> float:
        if notional <= 0:
            return 0.0

        commission = max(
            self._round_money(notional * self.commission_rate, rounding=ROUND_HALF_UP),
            round(float(self.min_commission), 2),
        )
        transfer_fee = self._round_money(notional * self.transfer_fee_rate, rounding=ROUND_DOWN)
        stamp_duty = (
            self._round_money(notional * self.stamp_duty_rate, rounding=ROUND_DOWN)
            if side == "SELL"
            else 0.0
        )
        return commission + transfer_fee + stamp_duty

    def _round_money(self, value: float, *, rounding) -> float:
        decimal_value = Decimal(str(value or 0.0))
        return float(decimal_value.quantize(BROKER_CENT, rounding=rounding))
