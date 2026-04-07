"""分钟级 T+0 策略重放器。"""

from dataclasses import replace
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from src.strategy.core.engine import T0StrategyEngine
from src.strategy.core.models import PortfolioState, SignalEvent
from src.strategy.core.params import T0StrategyParams
from src.strategy.core.regime_classifier import RegimeClassifier
from src.strategy.shared.strategy_contracts import BarData, StrategyParams, TradeData
from src.strategy.strategies.t0.strategy import T0Strategy
from src.strategy.strategies.t0.feature_calculator import FeatureCalculator
from src.trading.costs.trading_costs import TradingFeeSchedule


class T0BacktestSimulator:
    """使用纯策略核心逐 bar 重放分钟数据。"""

    def __init__(
        self,
        params: Optional[T0StrategyParams] = None,
        execution_mode: str = "same_bar_close",
        force_same_day_close: bool = False,
    ):
        self.params = params or T0StrategyParams()
        self.feature_calculator = FeatureCalculator()
        self.regime_classifier = RegimeClassifier()
        self.engine = T0StrategyEngine(self.params)
        self.strategy = None
        if execution_mode not in {"same_bar_close", "next_bar_open"}:
            raise ValueError(f"Unsupported execution_mode: {execution_mode}")
        self.execution_mode = execution_mode
        self.force_same_day_close = force_same_day_close

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
        pending_fill: Optional[Dict] = None
        strategy = self._build_strategy(
            symbol=symbol,
            daily_data=daily_data,
            initial_position=initial_position,
        )

        for trade_date, day_df in minute_data.groupby(minute_data.index.date, sort=True):
            day_df = day_df.sort_index()
            strategy._advance_trade_day(trade_date)

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
                    strategy.on_trade(
                        TradeData(
                            order_id=f"{symbol}-{len(fills)}",
                            stock_code=symbol,
                            direction=self._trade_direction_for_action(executed_fill["action"]),
                            filled_price=executed_fill["price"],
                            filled_volume=executed_fill["volume"],
                            filled_time=current_datetime.isoformat(),
                        )
                    )
                    pending_fill = None

                signal = self._normalize_strategy_signal(
                    strategy.on_bar(
                        BarData(
                            stock_code=symbol,
                            bar_time=current_datetime.isoformat(),
                            open=float(current_bar["open"]),
                            high=float(current_bar["high"]),
                            low=float(current_bar["low"]),
                            close=float(current_bar["close"]),
                            volume=int(current_bar["volume"]),
                            amount=(
                                float(current_bar["amount"])
                                if "amount" in current_bar and pd.notna(current_bar["amount"])
                                else None
                            ),
                        )
                    )
                )

                signals.append(
                    {
                        "timestamp": current_timestamp,
                        "symbol": symbol,
                        "regime": strategy.current_regime or "transition",
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
                        strategy.on_trade(
                            TradeData(
                                order_id=f"{symbol}-{len(fills)}",
                                stock_code=symbol,
                                direction=self._trade_direction_for_action(signal["action"]),
                                filled_price=fill_price,
                                filled_volume=fill_volume,
                                filled_time=current_datetime.isoformat(),
                            )
                        )
                    else:
                        pending_fill = {
                            "action": signal["action"],
                            "branch": signal.get("branch"),
                            "signal_timestamp": current_timestamp,
                            "signal_datetime": current_datetime,
                            "volume": int(signal["volume"]),
                        }

            if getattr(self, "force_same_day_close", False):
                pending_fill = None
                forced_close = self._build_forced_same_day_close(
                    signal_history=strategy.signal_history,
                    day_df=day_df,
                    symbol=symbol,
                )
                if forced_close is not None:
                    fills.append(forced_close["fill_record"])
                    strategy.on_trade(
                        TradeData(
                            order_id=f"{symbol}-{len(fills)}",
                            stock_code=symbol,
                            direction=self._trade_direction_for_action(forced_close["action"]),
                            filled_price=forced_close["price"],
                            filled_volume=forced_close["volume"],
                            filled_time=self._as_datetime(day_df.index[-1]).isoformat(),
                        )
                    )

        return {
            "signals": pd.DataFrame(signals),
            "fills": pd.DataFrame(fills),
            "final_position": strategy.position,
        }

    def _build_strategy(
        self,
        *,
        symbol: str,
        daily_data: pd.DataFrame,
        initial_position: PortfolioState,
    ) -> T0Strategy:
        strategy = T0Strategy(
            StrategyParams(
                name=f"t0_backtest_{symbol}",
                stock_code=symbol,
                max_position=int(initial_position.max_position),
            ),
            t0_params=self.params,
            daily_data=daily_data,
            initial_position=initial_position,
        )
        strategy.feature_calculator = self.feature_calculator
        strategy.regime_classifier = self.regime_classifier
        strategy.engine = self.engine
        strategy.reset()
        strategy.set_daily_data(daily_data)
        strategy.set_position(initial_position)
        self.strategy = strategy
        return strategy

    def _normalize_strategy_signal(self, signals: Optional[list[dict]]) -> Dict:
        if not signals:
            return {
                "action": "observe",
                "reason": "无符合条件的信号",
                "price": 0.0,
                "volume": 0,
                "branch": None,
            }

        signal = dict(signals[0])
        return {
            "action": signal.get("signal_action") or self._infer_action_from_order_type(signal.get("type")),
            "reason": signal.get("reason", ""),
            "price": float(signal.get("price", 0.0) or 0.0),
            "volume": int(signal.get("volume", 0) or 0),
            "branch": signal.get("branch"),
        }

    def _infer_action_from_order_type(self, order_type: Optional[str]) -> str:
        normalized = str(order_type or "").upper()
        if normalized == "BUY":
            return "reverse_t_buy"
        if normalized == "SELL":
            return "positive_t_sell"
        return "observe"

    def _trade_direction_for_action(self, action: str) -> str:
        if str(action).endswith("buy") or str(action).endswith("buyback"):
            return "BUY"
        return "SELL"

    def _build_day_snapshots(self, day_df: pd.DataFrame) -> List[Optional[object]]:
        if hasattr(self.feature_calculator, "calculate_day_snapshots"):
            return self.feature_calculator.calculate_day_snapshots(day_df)
        return [
            self.feature_calculator.calculate_snapshot(day_df.iloc[: idx + 1])
            for idx in range(len(day_df))
        ]

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
        return [
            replace(event, carry_trading_days=max(int(event.carry_trading_days), 0) + 1)
            for event in signal_history
        ]

    def _build_forced_same_day_close(
        self,
        *,
        signal_history: List[SignalEvent],
        day_df: pd.DataFrame,
        symbol: str,
    ) -> Optional[Dict]:
        if not signal_history or day_df.empty:
            return None

        branch_state = self.engine._build_branch_state(signal_history)
        if branch_state.completed or branch_state.branch is None or branch_state.volume <= 0:
            return None

        last_timestamp = day_df.index[-1]
        last_close = float(day_df.iloc[-1]["close"])
        execution_datetime = self._as_datetime(last_timestamp)
        action = self._get_forced_close_action(branch_state.branch)
        fill_volume = int(branch_state.volume)
        fee_breakdown = self._calculate_fee_breakdown(
            action=action,
            price=last_close,
            volume=fill_volume,
        )
        fill_record = {
            "timestamp": last_timestamp,
            "signal_timestamp": last_timestamp,
            "symbol": symbol,
            "action": action,
            "price": last_close,
            "volume": fill_volume,
            "execution_mode": f"{self.execution_mode}_force_same_day_close",
            **fee_breakdown,
        }
        signal_event = SignalEvent(
            action=action,
            branch=branch_state.branch,
            price=last_close,
            volume=fill_volume,
            signal_time=execution_datetime,
        )
        return {
            "fill_record": fill_record,
            "signal_event": signal_event,
            "action": action,
            "price": last_close,
            "volume": fill_volume,
            "fee_breakdown": fee_breakdown,
        }

    def _get_forced_close_action(self, branch: str) -> str:
        if branch == "positive_t":
            return "positive_t_buyback"
        if branch == "reverse_t":
            return "reverse_t_sell"
        raise ValueError(f"Unsupported branch for forced close: {branch}")

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
            **self._calculate_fee_breakdown(
                action=action, price=execution_price, volume=fill_volume
            ),
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
        fees = fee_breakdown or self._calculate_fee_breakdown(
            action=action, price=price, volume=volume
        )
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

    def _calculate_fee_breakdown(
        self, *, action: str, price: float, volume: int
    ) -> Dict[str, float]:
        return (
            TradingFeeSchedule.from_t0_params(self.params)
            .calculate(
                side=action,
                price=price,
                volume=volume,
            )
            .to_dict()
        )

    def _as_datetime(self, timestamp) -> datetime:
        if isinstance(timestamp, datetime):
            return timestamp
        return pd.Timestamp(timestamp).to_pydatetime()
