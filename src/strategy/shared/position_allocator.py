"""Position allocator for risk management across strategies."""

from __future__ import annotations

from src.logger_config import logger


class PositionAllocator:
    """Allocates positions to strategies with risk controls."""

    def __init__(self, total_limit: int):
        self.total_limit = total_limit
        self.strategy_limits: dict[str, int] = {}
        self.current_positions: dict[str, int] = {}

    def register_strategy(self, strategy_name: str, max_position: int) -> None:
        """Register strategy with position limit."""
        self.strategy_limits[strategy_name] = max_position
        self.current_positions[strategy_name] = 0
        logger.info(
            "Registered position limit for %s: %d shares",
            strategy_name,
            max_position,
        )

    def can_trade(
        self,
        strategy_name: str,
        direction: str,
        volume: int,
    ) -> tuple[bool, str]:
        """
        Check if a trade is allowed under position limits.

        Args:
            strategy_name: Strategy identifier
            direction: "BUY" or "SELL"
            volume: Number of shares

        Returns:
            (allowed, reason) tuple
        """
        if strategy_name not in self.strategy_limits:
            return False, f"Strategy {strategy_name} not registered"

        strategy_limit = self.strategy_limits[strategy_name]
        current = self.current_positions.get(strategy_name, 0)

        if direction == "BUY":
            new_position = current + volume
            if new_position > strategy_limit:
                return False, f"Position {new_position} exceeds limit {strategy_limit}"
            return True, "OK"

        elif direction == "SELL":
            new_position = current - volume
            if new_position < 0:
                return False, f"Insufficient position: {current}, requested SELL {volume}"
            return True, "OK"

        return False, f"Invalid direction: {direction}"

    def update_position(
        self,
        strategy_name: str,
        direction: str,
        volume: int,
    ) -> None:
        """Update position after trade execution."""
        if strategy_name not in self.current_positions:
            self.current_positions[strategy_name] = 0

        if direction == "BUY":
            self.current_positions[strategy_name] += volume
        elif direction == "SELL":
            self.current_positions[strategy_name] -= volume

        logger.debug(
            "Position updated: %s %s %d shares, new position: %d",
            strategy_name,
            direction,
            volume,
            self.current_positions[strategy_name],
        )

    def get_total_position(self) -> int:
        """Get total position across all strategies."""
        return sum(self.current_positions.values())

    def check_total_limit(self) -> bool:
        """Check if total position exceeds overall limit."""
        total = self.get_total_position()
        return total <= self.total_limit
