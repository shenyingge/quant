"""Pure T0 strategy implementation compatible with backtrader-style callbacks."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from typing import Optional

import pandas as pd

from src.strategy.core.engine import T0StrategyEngine
from src.strategy.core.feature_calculator import FeatureCalculator
from src.strategy.core.fees import TradingFeeSchedule
from src.strategy.core.models import PortfolioState, SignalEvent
from src.strategy.core.params import T0StrategyParams
from src.strategy.core.regime_classifier import RegimeClassifier
from src.strategy.shared.strategy_contracts import BarData, StrategyBase, StrategyParams, TickData, TradeData


class T0Strategy(StrategyBase):
    """Pure T0 strategy that can run in backtrader without any xtquant dependency."""

    def __init__(
        self,
        params: StrategyParams,
        *,
        t0_params: Optional[T0StrategyParams] = None,
        daily_data: Optional[pd.DataFrame] = None,
        initial_position: Optional[PortfolioState] = None,
    ):
        super().__init__(params)
        self.t0_params = t0_params or T0StrategyParams()
        self.feature_calculator = FeatureCalculator()
        self.regime_classifier = RegimeClassifier()
        self.engine = T0StrategyEngine(self.t0_params)
        self.fee_schedule = TradingFeeSchedule.from_t0_params(self.t0_params)
        self.daily_data = daily_data.copy() if daily_data is not None else pd.DataFrame()
        self.position = initial_position or self._build_default_position()
        self._current_trade_date: Optional[date] = None
        self._day_bars: list[dict] = []
        self._feature_state = self._initialize_feature_state()
        self._signal_history: list[SignalEvent] = []
        self._pending_signals: list[dict] = []
        self._cached_daily_slice: Optional[pd.DataFrame] = None
        self._cached_regime: Optional[str] = None

    def set_daily_data(self, daily_data: pd.DataFrame) -> None:
        self.daily_data = daily_data.copy() if daily_data is not None else pd.DataFrame()

    def set_position(self, position: PortfolioState) -> None:
        self.position = position

    @property
    def signal_history(self) -> list[SignalEvent]:
        return list(self._signal_history)

    def on_bar(self, bar: BarData) -> list[dict] | None:
        current_datetime = pd.Timestamp(bar.bar_time).to_pydatetime()
        trade_date = current_datetime.date()
        self._advance_trade_day(trade_date)
        bar_payload = {
            "datetime": current_datetime,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": int(bar.volume),
            "amount": float(bar.amount) if bar.amount is not None else None,
        }

        features = self._calculate_feature_snapshot(
            bar_payload=bar_payload,
            current_datetime=current_datetime,
        )
        if features is None:
            return None

        regime = self._get_cached_regime(trade_date)
        signal = self.engine.generate_signal(
            regime=regime,
            features=features.to_dict(),
            position=self.position.to_dict(),
            current_time=current_datetime.time(),
            current_datetime=current_datetime,
            signal_history=list(self._signal_history),
        )
        if signal["action"] == "observe":
            return None

        order_type = self._signal_to_order_type(signal["action"])
        if order_type is None:
            return None

        self._pending_signals.append(
            {
                "direction": order_type,
                "signal_action": signal["action"],
                "branch": signal.get("branch"),
                "signal_time": current_datetime,
            }
        )
        return [
            {
                "type": order_type,
                "volume": int(signal["volume"]),
                "price": float(signal["price"]),
                "reason": signal["reason"],
                "signal_action": signal["action"],
                "branch": signal.get("branch"),
            }
        ]

    def on_tick(self, tick: TickData) -> list[dict] | None:
        return None

    def on_trade(self, trade: TradeData) -> None:
        direction = str(trade.direction or "").upper()
        if direction not in {"BUY", "SELL"}:
            return

        signal_meta = self._pop_pending_signal(direction)
        signal_action = self._resolve_signal_action(direction, signal_meta)
        filled_time = pd.Timestamp(trade.filled_time).to_pydatetime()

        self.position = self._apply_fill(
            self.position,
            signal_action,
            float(trade.filled_price),
            int(trade.filled_volume),
        )
        self._signal_history.append(
            SignalEvent(
                action=signal_action,
                branch=signal_meta.get("branch") if signal_meta else self._infer_branch(signal_action),
                price=float(trade.filled_price),
                volume=int(trade.filled_volume),
                signal_time=filled_time,
            )
        )

    def reset(self) -> None:
        self._current_trade_date = None
        self._day_bars = []
        self._feature_state = self._initialize_feature_state()
        self._signal_history = []
        self._pending_signals = []
        self._cached_daily_slice = None
        self._cached_regime = None

    def _advance_trade_day(self, trade_date: date) -> None:
        if self._current_trade_date is None:
            self._current_trade_date = trade_date
            self._cached_daily_slice = None
            self._cached_regime = None
            return
        if self._current_trade_date == trade_date:
            return

        self.position = self._roll_position_to_next_trade_day(self.position)
        self._signal_history = self._next_day_signal_history(self._signal_history)
        self._pending_signals = []
        self._day_bars = []
        self._feature_state = self._initialize_feature_state()
        self._current_trade_date = trade_date
        self._cached_daily_slice = None
        self._cached_regime = None

    @property
    def current_regime(self) -> Optional[str]:
        return self._cached_regime

    def _get_cached_regime(self, trade_date: date) -> str:
        if self._cached_regime is not None:
            return self._cached_regime
        daily_slice = self._get_cached_daily_slice(trade_date)
        self._cached_regime = self.regime_classifier.calculate(daily_slice)
        return self._cached_regime

    def _get_cached_daily_slice(self, trade_date: date) -> pd.DataFrame:
        if self._cached_daily_slice is not None:
            return self._cached_daily_slice
        self._cached_daily_slice = self._daily_slice_before(trade_date)
        return self._cached_daily_slice

    def _initialize_feature_state(self):
        if hasattr(self.feature_calculator, "initialize_intraday_state"):
            return self.feature_calculator.initialize_intraday_state()
        return None

    def _calculate_feature_snapshot(
        self,
        *,
        bar_payload: dict,
        current_datetime: datetime,
    ):
        if hasattr(self.feature_calculator, "update_snapshot_from_bar"):
            return self.feature_calculator.update_snapshot_from_bar(
                self._feature_state,
                bar=bar_payload,
                latest_bar_time=current_datetime,
            )

        self._day_bars.append(bar_payload)
        day_df = self._build_day_frame()
        return self.feature_calculator.calculate_snapshot(day_df)

    def _build_day_frame(self) -> pd.DataFrame:
        if not self._day_bars:
            return pd.DataFrame()
        frame = pd.DataFrame(self._day_bars)
        frame["datetime"] = pd.to_datetime(frame["datetime"])
        return frame.set_index("datetime").sort_index()

    def _daily_slice_before(self, trade_date: date) -> pd.DataFrame:
        if self.daily_data is None or self.daily_data.empty:
            return pd.DataFrame()

        working = self.daily_data.copy()
        if isinstance(working.index, pd.DatetimeIndex):
            sliced = working.loc[working.index.date < trade_date]
            if not sliced.empty:
                return sliced

        if "datetime" in working.columns:
            datetimes = pd.to_datetime(working["datetime"])
            sliced = working.loc[datetimes.dt.date < trade_date]
            if not sliced.empty:
                return sliced

        return working

    def _signal_to_order_type(self, action: str) -> Optional[str]:
        if action.endswith("buy") or action.endswith("buyback"):
            return "BUY"
        if action.endswith("sell"):
            return "SELL"
        return None

    def _pop_pending_signal(self, direction: str) -> Optional[dict]:
        for idx, signal in enumerate(self._pending_signals):
            if signal.get("direction") == direction:
                return self._pending_signals.pop(idx)
        return None

    def _resolve_signal_action(self, direction: str, signal_meta: Optional[dict]) -> str:
        if signal_meta and signal_meta.get("signal_action"):
            return str(signal_meta["signal_action"])

        if self._signal_history:
            branch_state = self.engine._build_branch_state(self._signal_history)
            if not branch_state.completed:
                if branch_state.branch == "positive_t" and direction == "BUY":
                    return "positive_t_buyback"
                if branch_state.branch == "reverse_t" and direction == "SELL":
                    return "reverse_t_sell"

        return "reverse_t_buy" if direction == "BUY" else "positive_t_sell"

    def _infer_branch(self, action: str) -> Optional[str]:
        if action.startswith("positive_t"):
            return "positive_t"
        if action.startswith("reverse_t"):
            return "reverse_t"
        return None

    def _build_default_position(self) -> PortfolioState:
        base_position = int(self.t0_params.t0_base_position)
        tactical_position = int(self.t0_params.t0_tactical_position)
        max_position = base_position + tactical_position
        return PortfolioState(
            total_position=base_position,
            available_volume=base_position,
            cost_price=0.0,
            base_position=base_position,
            tactical_position=tactical_position,
            max_position=max_position,
            t0_sell_available=0,
            t0_buy_capacity=tactical_position,
            cash_available=float(self.t0_params.t0_max_trade_value),
        )

    def _roll_position_to_next_trade_day(self, position: PortfolioState) -> PortfolioState:
        total_position = max(int(position.total_position), 0)
        available_volume = total_position
        max_position = position.base_position + position.tactical_position
        trade_unit = max(int(self.t0_params.t0_trade_unit), 1)

        def round_down_lot(raw_volume: int) -> int:
            return max(int(raw_volume) // trade_unit * trade_unit, 0)

        normalized_sell = round_down_lot(
            min(available_volume, max(total_position - position.base_position, 0))
        )
        normalized_buy = round_down_lot(max(max_position - total_position, 0))
        return PortfolioState(
            total_position=total_position,
            available_volume=available_volume,
            cost_price=position.cost_price,
            base_position=position.base_position,
            tactical_position=position.tactical_position,
            max_position=max_position,
            t0_sell_available=normalized_sell,
            t0_buy_capacity=normalized_buy,
            cash_available=position.cash_available,
        )

    def _next_day_signal_history(self, signal_history: list[SignalEvent]) -> list[SignalEvent]:
        if not signal_history:
            return []

        branch_state = self.engine._build_branch_state(signal_history)
        if branch_state.completed:
            return []

        return [
            replace(event, carry_trading_days=max(int(event.carry_trading_days), 0) + 1)
            for event in signal_history
        ]

    def _apply_fill(self, position: PortfolioState, action: str, price: float, volume: int) -> PortfolioState:
        total_position = int(position.total_position)
        available_volume = int(position.available_volume)
        cash_available = float(position.cash_available)
        total_fee = self._calculate_total_fee(action=action, price=price, volume=volume)

        if action in {"positive_t_sell", "reverse_t_sell"}:
            total_position -= volume
            available_volume = max(available_volume - volume, 0)
            cash_available += price * volume - total_fee
        elif action in {"positive_t_buyback", "reverse_t_buy"}:
            total_position += volume
            cash_available -= price * volume + total_fee

        max_position = position.base_position + position.tactical_position
        trade_unit = max(int(self.t0_params.t0_trade_unit), 1)

        def round_down_lot(raw_volume: int) -> int:
            return max(int(raw_volume) // trade_unit * trade_unit, 0)

        normalized_sell = round_down_lot(
            min(available_volume, max(total_position - position.base_position, 0))
        )
        normalized_buy = round_down_lot(max(max_position - total_position, 0))
        return PortfolioState(
            total_position=total_position,
            available_volume=available_volume,
            cost_price=position.cost_price,
            base_position=position.base_position,
            tactical_position=position.tactical_position,
            max_position=max_position,
            t0_sell_available=normalized_sell,
            t0_buy_capacity=normalized_buy,
            cash_available=cash_available,
        )

    def _calculate_total_fee(self, *, action: str, price: float, volume: int) -> float:
        notional = max(float(price) * int(volume), 0.0)
        if notional <= 0:
            return 0.0
        side = "BUY" if action.endswith("buy") or action.endswith("buyback") else "SELL"
        return float(self.fee_schedule._calculate_leg_total_fee(side=side, notional=notional))
