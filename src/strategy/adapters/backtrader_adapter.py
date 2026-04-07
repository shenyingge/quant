"""Backtrader strategy wrapper for T+0 strategies."""

from __future__ import annotations

from datetime import datetime

import backtrader as bt

from src.infrastructure.logger_config import logger
from src.strategy.shared.strategy_contracts import BarData, StrategyBase, TradeData


class BacktraderStrategyWrapper(bt.Strategy):
    """Wraps a StrategyBase instance for use in backtrader Cerebro."""

    params = (("strategy", None),)

    def __init__(self):
        self.strategy = self.params.strategy
        if self.strategy is None:
            raise ValueError("strategy parameter is required")
        self.bar_calls = []
        self.buy_orders = []
        self.sell_orders = []

    def next(self):
        """Called by backtrader for each bar."""
        # Convert backtrader bar to BarData
        bar = BarData(
            stock_code=self.strategy.stock_code,
            bar_time=self.data.datetime.datetime(0).isoformat(),
            open=float(self.data.open[0]),
            high=float(self.data.high[0]),
            low=float(self.data.low[0]),
            close=float(self.data.close[0]),
            volume=int(self.data.volume[0]),
        )

        self.bar_calls.append(bar)

        # Call strategy on_bar
        signals = self.strategy.on_bar(bar)
        if not signals:
            return

        # Process signals
        for signal in signals:
            action = signal.get("type", "NEUTRAL")
            volume = signal.get("volume", 0)

            if action == "BUY":
                order = self.buy(size=volume)
                order.addinfo(signal=signal)
                self.buy_orders.append(order)
            elif action == "SELL":
                order = self.sell(size=volume)
                order.addinfo(signal=signal)
                self.sell_orders.append(order)

    def notify_order(self, order):
        """Forward completed fills back into the pure strategy state."""
        if order.status != bt.Order.Completed:
            return

        direction = "BUY" if order.isbuy() else "SELL"
        filled_time = self.data.datetime.datetime(0).isoformat()
        self.strategy.on_trade(
            TradeData(
                order_id=str(order.ref),
                stock_code=self.strategy.stock_code,
                direction=direction,
                filled_price=float(order.executed.price),
                filled_volume=int(abs(order.executed.size)),
                filled_time=filled_time,
            )
        )

    def notify_trade(self, trade):
        """Called when a trade closes."""
        if trade.isclosed:
            logger.info(
                "Trade closed: price %.2f cost %.2f profit %.2f",
                trade.executed.price,
                trade.executed.value,
                trade.pnl,
            )
