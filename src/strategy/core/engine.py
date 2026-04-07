"""纯策略核心状态机。"""

from datetime import datetime, time
from typing import Dict, List, Optional

from src.strategy.core.fees import TradingFeeSchedule
from src.strategy.core.models import BranchState, SignalEvent


class T0StrategyEngine:
    """只根据输入数据与状态输出信号。"""

    def __init__(self, params):
        self.params = params
        self.fee_schedule = TradingFeeSchedule.from_t0_params(params)

    def generate_signal(
        self,
        regime: str,
        features: Dict,
        position: Dict,
        current_time,
        current_datetime: Optional[datetime] = None,
        signal_history: Optional[List[SignalEvent]] = None,
    ) -> Dict:
        history = signal_history or []

        if history:
            branch_state = self._build_branch_state(history)
            followup_signal = self._handle_existing_branch(
                branch_state, features, position, current_time, current_datetime
            )
            if followup_signal is not None:
                return followup_signal

        for branch in self._get_branch_priority(regime):
            if branch == "positive_t":
                signal = self._check_positive_t(features, position, current_time)
            elif branch == "reverse_t":
                signal = self._check_reverse_t(features, position, current_time)
            else:
                continue

            if signal["action"] != "observe":
                return signal

        return self._observe_signal("无符合条件的信号")

    def _check_positive_t(self, features: Dict, position: Dict, current_time) -> Dict:
        if self._within_window(
            current_time,
            self.params.t0_positive_sell_start_time,
            self.params.t0_positive_sell_end_time,
        ):
            return self._check_positive_t_sell(features, position)
        if self._within_window(
            current_time,
            self.params.t0_positive_buyback_start_time,
            self.params.t0_positive_buyback_end_time,
        ):
            return self._observe_signal("今日未执行positive_t卖出，暂无回补")
        return self._observe_signal("不在正T时间窗口")

    def _check_reverse_t(self, features: Dict, position: Dict, current_time) -> Dict:
        if self._within_window(
            current_time,
            self.params.t0_reverse_buy_start_time,
            self.params.t0_reverse_buy_end_time,
        ):
            return self._check_reverse_t_buy(features, position)
        if self._within_window(
            current_time,
            self.params.t0_reverse_sell_start_time,
            self.params.t0_reverse_sell_end_time,
        ):
            return self._observe_signal("今日未执行reverse_t买入，暂无卖出")
        return self._observe_signal("不在反T时间窗口")

    def _check_positive_t_sell(self, features: Dict, position: Dict) -> Dict:
        day_open = features["day_open"]
        high = features["high_so_far"]
        close = features["current_close"]
        vwap = features["vwap"]
        prev_close = float(features.get("prev_close", day_open) or day_open)
        open_gap_pct = self._calculate_open_gap_pct(day_open, prev_close)
        rise_reference = max(day_open, prev_close) if prev_close > 0 else day_open
        gap_down_limit = getattr(self.params, "t0_positive_sell_gap_down_limit", None)

        if gap_down_limit is not None and open_gap_pct <= float(gap_down_limit):
            return self._observe_signal(
                f"开盘低开{abs(open_gap_pct):.1f}%，跳过正T卖出"
            )

        rise = ((high - rise_reference) / rise_reference * 100) if rise_reference > 0 else 0
        pullback = ((high - close) / high * 100) if high > 0 else 0
        below_vwap = close < vwap
        volume = self._get_sell_volume(position)

        if volume <= 0:
            return self._observe_signal("当前无可卖出的T仓")

        if (
            rise >= self.params.t0_positive_sell_min_rise
            and pullback >= self.params.t0_positive_sell_min_pullback
            and below_vwap
        ):
            return {
                "action": "positive_t_sell",
                "reason": f"冲高失败: 涨{rise:.1f}%后回撤{pullback:.1f}%",
                "price": close,
                "volume": volume,
                "branch": "positive_t",
            }

        return self._observe_signal("正T卖出条件不满足")

    def _check_positive_t_buyback(
        self,
        features: Dict,
        position: Dict,
        branch_state: BranchState,
        current_datetime: Optional[datetime] = None,
    ) -> Dict:
        bounce = features["bounce_from_low"]
        absorption = features["absorption_score"]
        sell_price = branch_state.entry_price
        volume = self._get_buy_volume(position, features["current_close"], branch_state.volume)

        if sell_price is None:
            return self._observe_signal("缺少positive_t卖出价格，无法判断回补")
        if volume <= 0:
            return self._observe_signal("当前无可用机动仓回补")

        forced_reason = self._build_positive_t_buyback_fallback_reason(
            branch_state=branch_state,
            features=features,
            current_datetime=current_datetime,
        )
        if forced_reason is not None:
            return {
                "action": "positive_t_buyback",
                "reason": forced_reason,
                "price": features["current_close"],
                "volume": volume,
                "branch": "positive_t",
            }

        if bounce >= 0.4 and absorption >= 0.6:
            roundtrip = self.fee_schedule.estimate_roundtrip(
                buy_price=features["current_close"],
                sell_price=sell_price,
                volume=volume,
            )
            if roundtrip["net_pnl"] <= 0:
                return self._observe_signal(self._build_fee_block_reason("正T回补", roundtrip))
            return {
                "action": "positive_t_buyback",
                "reason": f"急跌反弹: 反弹{bounce:.1f}%",
                "price": features["current_close"],
                "volume": volume,
                "branch": "positive_t",
            }

        return self._observe_signal("正T回补条件不满足")

    def _check_reverse_t_buy(self, features: Dict, position: Dict) -> Dict:
        bounce = features["bounce_from_low"]
        close_vs_vwap = features["close_vs_vwap"]
        absorption = features["absorption_score"]
        volume = self._get_buy_volume(position, features["current_close"])

        if volume <= 0:
            return self._observe_signal("当前无可用机动仓买入")

        if (
            bounce >= self.params.t0_reverse_buy_min_bounce
            and close_vs_vwap >= -0.5
            and absorption >= 0.6
        ):
            return {
                "action": "reverse_t_buy",
                "reason": f"急跌止跌: 反弹{bounce:.1f}%",
                "price": features["current_close"],
                "volume": volume,
                "branch": "reverse_t",
            }

        return self._observe_signal("反T买入条件不满足")

    def _check_reverse_t_sell(
        self,
        features: Dict,
        position: Dict,
        branch_state: BranchState,
        current_datetime: Optional[datetime] = None,
    ) -> Dict:
        entry_price = branch_state.entry_price
        volume = self._get_sell_volume(position, branch_state.volume)

        if entry_price is None:
            return self._observe_signal("缺少reverse_t买入价格，无法判断卖出")
        if volume <= 0:
            return self._observe_signal("当前无可卖出的T仓")

        forced_reason = self._build_reverse_t_sell_fallback_reason(
            branch_state=branch_state,
            features=features,
            current_datetime=current_datetime,
        )
        if forced_reason is not None:
            return {
                "action": "reverse_t_sell",
                "reason": forced_reason,
                "price": features["current_close"],
                "volume": volume,
                "branch": "reverse_t",
            }

        profit = (
            ((features["current_close"] - entry_price) / entry_price * 100)
            if entry_price > 0
            else 0
        )
        near_vwap = abs(features["close_vs_vwap"]) <= self.params.t0_reverse_sell_max_vwap_distance
        roundtrip = self.fee_schedule.estimate_roundtrip(
            buy_price=entry_price,
            sell_price=features["current_close"],
            volume=volume,
        )

        carry_take_profit_reason = self._build_reverse_t_sell_carry_take_profit_reason(
            branch_state=branch_state,
            roundtrip=roundtrip,
        )
        if carry_take_profit_reason is not None:
            return {
                "action": "reverse_t_sell",
                "reason": carry_take_profit_reason,
                "price": features["current_close"],
                "volume": volume,
                "branch": "reverse_t",
            }

        if not near_vwap or profit < self.params.t0_reverse_sell_min_profit:
            return self._observe_signal("反T卖出条件不满足")

        if roundtrip["net_pnl"] <= 0:
            return self._observe_signal(self._build_fee_block_reason("反T卖出", roundtrip))

        return {
            "action": "reverse_t_sell",
            "reason": f"反T止盈: 相对买入价浮盈{profit:.1f}%",
            "price": features["current_close"],
            "volume": volume,
            "branch": "reverse_t",
        }

    def _handle_existing_branch(
        self,
        branch_state: BranchState,
        features: Dict,
        position: Dict,
        current_time,
        current_datetime: Optional[datetime],
    ) -> Optional[Dict]:
        if branch_state.completed:
            return self._observe_signal(f"今日已完成{branch_state.branch}闭环")

        if branch_state.branch == "positive_t":
            if self._within_window(
                current_time,
                self.params.t0_positive_buyback_start_time,
                self.params.t0_positive_buyback_end_time,
            ):
                hold_check = self._check_min_hold(branch_state, current_datetime)
                if hold_check is not None:
                    return hold_check
                return self._check_positive_t_buyback(
                    features,
                    position,
                    branch_state,
                    current_datetime=current_datetime,
                )
            return self._observe_signal("今日已执行positive_t卖出，等待回补窗口")

        if branch_state.branch == "reverse_t":
            if self._within_window(
                current_time,
                self.params.t0_reverse_sell_start_time,
                self.params.t0_reverse_sell_end_time,
            ):
                hold_check = self._check_min_hold(branch_state, current_datetime)
                if hold_check is not None:
                    return hold_check
                return self._check_reverse_t_sell(
                    features,
                    position,
                    branch_state,
                    current_datetime=current_datetime,
                )
            return self._observe_signal("今日已执行reverse_t买入，等待卖出窗口")

        return None

    def _build_branch_state(self, history: List[SignalEvent]) -> BranchState:
        first_signal = history[0]
        branch = first_signal.branch or self._infer_branch(first_signal.action)
        actions = [item.action for item in history]
        volume = next((item.volume for item in history if item.volume), 0)
        entry_price = next((item.price for item in history if item.price is not None), None)
        entry_time = next((item.signal_time for item in history if item.signal_time), None)
        completed = False

        if branch == "positive_t":
            completed = "positive_t_buyback" in actions
        elif branch == "reverse_t":
            completed = "reverse_t_sell" in actions

        return BranchState(
            branch=branch,
            completed=completed,
            volume=volume,
            entry_price=entry_price,
            entry_time=entry_time,
            carry_trading_days=max((max(item.carry_trading_days, 0) for item in history), default=0),
        )

    def _build_fee_block_reason(self, prefix: str, roundtrip: Dict[str, float]) -> str:
        return (
            f"{prefix}价差不足覆盖手续费: "
            f"毛利{roundtrip['gross_pnl']:.2f}元, "
            f"费用{roundtrip['total_fee']:.2f}元"
        )

    def _build_positive_t_buyback_fallback_reason(
        self,
        *,
        branch_state: BranchState,
        features: Dict,
        current_datetime: Optional[datetime],
    ) -> Optional[str]:
        sell_price = branch_state.entry_price
        current_close = float(features.get("current_close", 0) or 0)
        if sell_price is None or sell_price <= 0 or current_close <= 0:
            return None

        adverse_move_pct = ((current_close - sell_price) / sell_price * 100) if sell_price > 0 else 0
        raw_stop_loss_pct = getattr(self.params, "t0_positive_buyback_stop_loss_pct", None)
        if raw_stop_loss_pct is not None:
            stop_loss_pct = max(float(raw_stop_loss_pct), 0.0)
            if stop_loss_pct > 0 and adverse_move_pct >= stop_loss_pct:
                return f"止损回补: 高于卖出价{adverse_move_pct:.1f}%"

        carry_days = max(int(branch_state.carry_trading_days), 0)
        raw_max_carry_days = getattr(self.params, "t0_positive_buyback_max_carry_days", None)
        max_carry_days = (
            max(int(raw_max_carry_days), 0) if raw_max_carry_days is not None else 0
        )
        if max_carry_days > 0 and carry_days >= max_carry_days:
            return f"跨日兜底回补: 已持有{carry_days}天"

        return None

    def _build_reverse_t_sell_fallback_reason(
        self,
        *,
        branch_state: BranchState,
        features: Dict,
        current_datetime: Optional[datetime],
    ) -> Optional[str]:
        entry_price = branch_state.entry_price
        current_close = float(features.get("current_close", 0) or 0)
        if entry_price is None or entry_price <= 0 or current_close <= 0:
            return None

        adverse_move_pct = ((entry_price - current_close) / entry_price * 100) if entry_price > 0 else 0
        raw_stop_loss_pct = getattr(self.params, "t0_reverse_sell_stop_loss_pct", None)
        if raw_stop_loss_pct is not None:
            stop_loss_pct = max(float(raw_stop_loss_pct), 0.0)
            if stop_loss_pct > 0 and adverse_move_pct >= stop_loss_pct:
                return f"止损卖出: 低于买入价{adverse_move_pct:.1f}%"

        carry_days = max(int(branch_state.carry_trading_days), 0)
        raw_max_carry_days = getattr(self.params, "t0_reverse_sell_max_carry_days", None)
        max_carry_days = (
            max(int(raw_max_carry_days), 0) if raw_max_carry_days is not None else 0
        )
        if max_carry_days > 0 and carry_days >= max_carry_days:
            return f"跨日兜底卖出: 已持有{carry_days}天"

        return None

    def _build_reverse_t_sell_carry_take_profit_reason(
        self,
        *,
        branch_state: BranchState,
        roundtrip: Dict[str, float],
    ) -> Optional[str]:
        raw_carry_days = getattr(
            self.params,
            "t0_reverse_sell_take_profit_after_carry_days",
            None,
        )
        if raw_carry_days is None:
            return None

        carry_days = max(int(branch_state.carry_trading_days), 0)
        take_profit_after_days = max(int(raw_carry_days), 0)
        if take_profit_after_days <= 0 or carry_days < take_profit_after_days:
            return None

        net_pnl = float(roundtrip.get("net_pnl", 0.0) or 0.0)
        if net_pnl <= 0:
            return None

        return f"跨日止盈卖出: 已持有{carry_days}天, 净盈利{net_pnl:.2f}元"

    def _calculate_open_gap_pct(self, day_open: float, prev_close: float) -> float:
        if prev_close <= 0:
            return 0.0
        return ((day_open - prev_close) / prev_close) * 100

    def _check_min_hold(
        self, branch_state: BranchState, current_datetime: Optional[datetime]
    ) -> Optional[Dict]:
        if self.params.t0_min_hold_minutes <= 0:
            return None
        if branch_state.entry_time is None:
            return None
        if current_datetime is None:
            return None

        minutes_held = (current_datetime - branch_state.entry_time).total_seconds() / 60
        if minutes_held >= self.params.t0_min_hold_minutes:
            return None

        return self._observe_signal(
            f"最小持有时间未满足，还需{int(self.params.t0_min_hold_minutes - minutes_held + 0.9999)}分钟"
        )

    def _within_window(self, current_time: time, start: str, end: str) -> bool:
        return self.params.parse_time(start) <= current_time <= self.params.parse_time(end)

    def _infer_branch(self, action: Optional[str]) -> Optional[str]:
        if not action:
            return None
        if action.startswith("positive_t"):
            return "positive_t"
        if action.startswith("reverse_t"):
            return "reverse_t"
        return None

    def _get_branch_priority(self, regime: str) -> list:
        if regime == "downtrend":
            return ["positive_t", "reverse_t"]
        if regime == "uptrend":
            return ["reverse_t"]
        return ["reverse_t", "positive_t"]

    def _get_sell_volume(self, position: Dict, preferred_volume: Optional[int] = None) -> int:
        sell_capacity = self._round_down_lot(position.get("t0_sell_available", 0))
        if preferred_volume is not None:
            sell_capacity = min(sell_capacity, self._round_down_lot(preferred_volume))
        return min(sell_capacity, self.params.t0_tactical_position)

    def _get_buy_volume(
        self,
        position: Dict,
        price: float,
        preferred_volume: Optional[int] = None,
    ) -> int:
        buy_capacity = self._round_down_lot(position.get("t0_buy_capacity", 0))
        max_cash_volume = self._cash_limited_volume(price)
        volume = min(buy_capacity, max_cash_volume, self.params.t0_tactical_position)
        if preferred_volume is not None:
            volume = min(volume, self._round_down_lot(preferred_volume))
        return volume

    def _cash_limited_volume(self, price: float) -> int:
        if price <= 0:
            return 0
        max_volume = int(self.params.t0_max_trade_value // price)
        return self._round_down_lot(max_volume)

    def _round_down_lot(self, volume: int) -> int:
        trade_unit = max(int(self.params.t0_trade_unit), 1)
        return max(int(volume) // trade_unit * trade_unit, 0)

    def _observe_signal(self, reason: str) -> Dict:
        return {
            "action": "observe",
            "reason": reason,
            "price": 0,
            "volume": 0,
            "branch": None,
        }
