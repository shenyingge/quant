"""Strategy Manager for coordinating multiple strategies."""

from __future__ import annotations

from src.logger_config import logger
from src.strategy.t0.contracts.strategy import BarData, StrategyBase, TickData, TradeData


class StrategyManager:
    """Manages multiple strategy instances and broadcasts market data."""

    def __init__(self):
        self.strategies: dict[str, StrategyBase] = {}

    def register_strategy(self, strategy: StrategyBase) -> None:
        """Register a strategy instance."""
        if strategy.strategy_name in self.strategies:
            logger.warning(
                "Strategy %s already registered, replacing",
                strategy.strategy_name,
            )
        self.strategies[strategy.strategy_name] = strategy
        logger.info("Registered strategy: %s", strategy.strategy_name)

    def unregister_strategy(self, strategy_name: str) -> None:
        """Unregister a strategy by name."""
        if strategy_name in self.strategies:
            del self.strategies[strategy_name]
            logger.info("Unregistered strategy: %s", strategy_name)

    def broadcast_bar(self, bar: BarData) -> list[tuple[str, list[dict]]]:
        """
        Broadcast bar to all strategies and collect signals.

        Returns:
            List of (strategy_name, signals) tuples
        """
        results = []
        for name, strategy in self.strategies.items():
            try:
                signals = strategy.on_bar(bar)
                if signals:
                    results.append((name, signals))
            except Exception as exc:
                logger.error("Error in strategy %s on_bar: %s", name, exc)

        return results

    def broadcast_tick(self, tick: TickData) -> list[tuple[str, list[dict]]]:
        """Broadcast tick to all strategies and collect signals."""
        results = []
        for name, strategy in self.strategies.items():
            try:
                signals = strategy.on_tick(tick)
                if signals:
                    results.append((name, signals))
            except Exception as exc:
                logger.error("Error in strategy %s on_tick: %s", name, exc)

        return results

    def broadcast_trade(self, trade: TradeData) -> None:
        """Broadcast trade execution to all strategies."""
        for name, strategy in self.strategies.items():
            try:
                strategy.on_trade(trade)
            except Exception as exc:
                logger.error("Error in strategy %s on_trade: %s", name, exc)

    def reset_all(self) -> None:
        """Reset all strategies (useful for backtesting)."""
        for name, strategy in self.strategies.items():
            try:
                strategy.reset()
            except Exception as exc:
                logger.error("Error resetting strategy %s: %s", name, exc)
