"""分钟级 T+0 策略重放器。"""

from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from src.strategy.core.engine import T0StrategyEngine
from src.strategy.core.models import PortfolioState, SignalEvent
from src.strategy.core.params import T0StrategyParams
from src.strategy.core.regime_classifier import RegimeClassifier
from src.strategy.feature_calculator import FeatureCalculator


class T0BacktestSimulator:
    """使用纯策略核心逐 bar 重放分钟数据。"""

    def __init__(
        self,
        params: Optional[T0StrategyParams] = None,
        execution_mode: str = "same_bar_close",
    ):
        self.params = params or T0StrategyParams()
        self.feature_calculator = FeatureCalculator()
        self.regime_classifier = RegimeClassifier()
        self.engine = T0StrategyEngine(self.params)
        if execution_mode not in {"same_bar_close", "next_bar_open"}:
            raise ValueError(f"Unsupported execution_mode: {execution_mode}")
        self.execution_mode = execution_mode

    def run(
        self,
        minute_data: pd.DataFrame,
        daily_data: pd.DataFrame,
        initial_position: PortfolioState,
        symbol: str = "601138.SH",
    ) -> Dict:
        if minute_data is None or minute_data.empty:
            return {
                "signals": pd.DataFrame(),
                "fills": pd.DataFrame(),
                "final_position": initial_position,
            }

        signals: List[Dict] = []
        fills: List[Dict] = []
        position = initial_position
        carry_signal_history: List[SignalEvent] = []
        is_first_trade_day = True
        pending_fill: Optional[Dict] = None

        for trade_date, day_df in minute_data.groupby(minute_data.index.date, sort=True):
            day_df = day_df.sort_index()
            if not is_first_trade_day:
                position = self._roll_position_to_next_trade_day(position)
            signal_history = list(carry_signal_history)
            regime_input = self._daily_slice_before(daily_data, trade_date)
            regime = self.regime_classifier.calculate(regime_input)

            for idx in range(len(day_df)):
                current_bar = day_df.iloc[idx]
                current_timestamp = day_df.index[idx]
                current_datetime = self._as_datetime(current_timestamp)

                if pending_fill is not None:
                    executed_fill = self._execute_pending_fill(
                        pending_fill=pending_fill,
                        execution_timestamp=current_timestamp,
                        execution_datetime=current_datetime,
                        execution_price=float(current_bar["open"]),
                        symbol=symbol,
                    )
                    fills.append(executed_fill["fill_record"])
                    signal_history.append(executed_fill["signal_event"])
                    position = self._apply_fill(
                        position,
                        executed_fill["action"],
                        executed_fill["price"],
                        executed_fill["volume"],
                        fee_breakdown=executed_fill["fee_breakdown"],
                    )
                    pending_fill = None

                window = day_df.iloc[: idx + 1]
                features = self.feature_calculator.calculate_snapshot(window)
                if features is None:
                    continue

                current_time = current_timestamp.time()
                signal = self.engine.generate_signal(
                    regime=regime,
                    features=features.to_dict(),
                    position=position.to_dict(),
                    current_time=current_time,
                    current_datetime=current_datetime,
                    signal_history=signal_history,
                )

                signals.append(
                    {
                        "timestamp": current_timestamp,
                        "symbol": symbol,
                        "regime": regime,
                        "action": signal["action"],
                        "reason": signal["reason"],
                        "price": signal["price"],
                        "volume": signal["volume"],
                    }
                )

                if signal["action"] != "observe":
                    if self.execution_mode == "same_bar_close":
                        fill_price = float(signal["price"] or current_bar["close"])
                        fill_volume = int(signal["volume"])
                        fills.append(
                            {
                                "timestamp": current_timestamp,
                                "signal_timestamp": current_timestamp,
                                "symbol": symbol,
                                "action": signal["action"],
                                "price": fill_price,
                                "volume": fill_volume,
                                "execution_mode": self.execution_mode,
                                **self._calculate_fee_breakdown(
                                    action=signal["action"],
                                    price=fill_price,
                                    volume=fill_volume,
                                ),
                            }
                        )
                        signal_history.append(
                            SignalEvent(
                                action=signal["action"],
                                branch=signal.get("branch"),
                                price=fill_price,
                                volume=fill_volume,
                                signal_time=current_datetime,
                            )
                        )
                        position = self._apply_fill(
                            position,
                            signal["action"],
                            fill_price,
                            fill_volume,
                            fee_breakdown=self._calculate_fee_breakdown(
                                action=signal["action"],
                                price=fill_price,
                                volume=fill_volume,
                            ),
                        )
                    else:
                        pending_fill = {
                            "action": signal["action"],
                            "branch": signal.get("branch"),
                            "signal_timestamp": current_timestamp,
                            "signal_datetime": current_datetime,
                            "volume": int(signal["volume"]),
                        }

            carry_signal_history = self._next_day_signal_history(signal_history)
            is_first_trade_day = False

        return {
            "signals": pd.DataFrame(signals),
            "fills": pd.DataFrame(fills),
            "final_position": position,
        }

    def _daily_slice_before(self, daily_data: pd.DataFrame, trade_date) -> pd.DataFrame:
        if daily_data is None or daily_data.empty:
            return pd.DataFrame()

        working = daily_data.copy()
        if isinstance(working.index, pd.DatetimeIndex):
            mask = working.index.date < trade_date
            sliced = working.loc[mask]
            if not sliced.empty:
                return sliced

        if "datetime" in working.columns:
            datetimes = pd.to_datetime(working["datetime"])
            sliced = working.loc[datetimes.dt.date < trade_date]
            if not sliced.empty:
                return sliced

        return working

    def _roll_position_to_next_trade_day(self, position: PortfolioState) -> PortfolioState:
        total_position = max(int(position.total_position), 0)
        available_volume = total_position
        max_position = position.base_position + position.tactical_position
        trade_unit = max(self.params.t0_trade_unit, 1)

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

    def _next_day_signal_history(self, signal_history: List[SignalEvent]) -> List[SignalEvent]:
        if not signal_history:
            return []

        branch_state = self.engine._build_branch_state(signal_history)
        if branch_state.completed:
            return []
        return list(signal_history)

    def _execute_pending_fill(
        self,
        *,
        pending_fill: Dict,
        execution_timestamp,
        execution_datetime: datetime,
        execution_price: float,
        symbol: str,
    ) -> Dict:
        fill_volume = int(pending_fill["volume"])
        action = str(pending_fill["action"])
        branch = pending_fill.get("branch")
        fill_record = {
            "timestamp": execution_timestamp,
            "signal_timestamp": pending_fill["signal_timestamp"],
            "symbol": symbol,
            "action": action,
            "price": execution_price,
            "volume": fill_volume,
            "execution_mode": self.execution_mode,
            **self._calculate_fee_breakdown(action=action, price=execution_price, volume=fill_volume),
        }
        signal_event = SignalEvent(
            action=action,
            branch=branch,
            price=execution_price,
            volume=fill_volume,
            signal_time=execution_datetime,
        )
        return {
            "fill_record": fill_record,
            "signal_event": signal_event,
            "action": action,
            "price": execution_price,
            "volume": fill_volume,
            "fee_breakdown": self._calculate_fee_breakdown(
                action=action,
                price=execution_price,
                volume=fill_volume,
            ),
        }

    def _apply_fill(
        self,
        position: PortfolioState,
        action: str,
        price: float,
        volume: int,
        fee_breakdown: Optional[Dict[str, float]] = None,
    ) -> PortfolioState:
        total_position = position.total_position
        available_volume = position.available_volume
        cash_available = position.cash_available
        fees = fee_breakdown or self._calculate_fee_breakdown(action=action, price=price, volume=volume)
        total_fee = float(fees.get("total_fee", 0.0))

        if action == "positive_t_sell":
            total_position -= volume
            available_volume = max(available_volume - volume, 0)
            cash_available += price * volume - total_fee
        elif action == "positive_t_buyback":
            total_position += volume
            cash_available -= price * volume + total_fee
        elif action == "reverse_t_buy":
            total_position += volume
            cash_available -= price * volume + total_fee
        elif action == "reverse_t_sell":
            total_position -= volume
            available_volume = max(available_volume - volume, 0)
            cash_available += price * volume - total_fee

        max_position = position.base_position + position.tactical_position
        trade_unit = max(self.params.t0_trade_unit, 1)

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

    def _calculate_fee_breakdown(self, *, action: str, price: float, volume: int) -> Dict[str, float]:
        notional = max(float(price) * int(volume), 0.0)
        commission_rate = float(getattr(self.params, "t0_commission_rate", 0.0) or 0.0)
        min_commission = float(getattr(self.params, "t0_min_commission", 0.0) or 0.0)
        transfer_fee_rate = float(getattr(self.params, "t0_transfer_fee_rate", 0.0) or 0.0)
        stamp_duty_rate = float(getattr(self.params, "t0_stamp_duty_rate", 0.0) or 0.0)

        commission = max(notional * commission_rate, min_commission) if notional > 0 else 0.0
        transfer_fee = notional * transfer_fee_rate
        stamp_duty = notional * stamp_duty_rate if action.endswith("sell") else 0.0
        total_fee = commission + transfer_fee + stamp_duty

        return {
            "notional": round(notional, 6),
            "commission": round(commission, 6),
            "transfer_fee": round(transfer_fee, 6),
            "stamp_duty": round(stamp_duty, 6),
            "total_fee": round(total_fee, 6),
        }

    def _as_datetime(self, timestamp) -> datetime:
        if isinstance(timestamp, datetime):
            return timestamp
        return pd.Timestamp(timestamp).to_pydatetime()
