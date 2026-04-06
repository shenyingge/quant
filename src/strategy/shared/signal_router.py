"""Signal router for conflict detection and resolution."""

from __future__ import annotations

from dataclasses import dataclass

from src.infrastructure.logger_config import logger


@dataclass
class ConflictRecord:
    """Record of detected signal conflict."""

    stock_code: str
    strategy_name: str
    signal_type: str
    volume: int
    reason: str


class SignalRouter:
    """Routes and validates signals from multiple strategies."""

    def __init__(self, strict_mode: bool = False):
        self.strict_mode = strict_mode

    def route_signals(
        self,
        stock_code: str,
        signals: list[tuple[str, list[dict]]],
        current_position: int = 0,
    ) -> tuple[dict | None, list[ConflictRecord]]:
        """
        Route signals from multiple strategies to a unified decision.

        Args:
            stock_code: Target stock code
            signals: List of (strategy_name, signal_list) tuples
            current_position: Current holding quantity (default 0)

        Returns:
            (unified_signal, conflict_records) tuple
        """
        conflicts = []
        all_actions = []

        # Flatten and normalize signals
        for strategy_name, signal_list in signals:
            for signal in signal_list:
                action = signal.get("type", "NEUTRAL")
                volume = signal.get("volume", 0)
                all_actions.append({
                    "strategy": strategy_name,
                    "action": action,
                    "volume": volume,
                    "signal": signal,
                })

        if not all_actions:
            return None, []

        # Filter out NEUTRAL actions if other signals exist
        non_neutral = [a for a in all_actions if a["action"] != "NEUTRAL"]
        if non_neutral:
            all_actions = non_neutral

        if not all_actions:
            return None, []

        # Detect conflicts
        action_types = set(a["action"] for a in all_actions)
        if len(action_types) > 1:
            logger.warning(
                "Signal conflict on %s: %s",
                stock_code,
                action_types,
            )
            for action in all_actions:
                conflicts.append(
                    ConflictRecord(
                        stock_code=stock_code,
                        strategy_name=action["strategy"],
                        signal_type=action["action"],
                        volume=action["volume"],
                        reason="Multiple strategy signals in different directions",
                    )
                )

            # Resolve conflict: fallback to NEUTRAL in strict mode
            if self.strict_mode:
                return None, conflicts

            # Otherwise use primary action
            primary_action = all_actions[0]
            return {"type": primary_action["action"], "volume": primary_action["volume"]}, conflicts

        # No conflict: aggregate
        primary_action = all_actions[0]
        total_volume = sum(a["volume"] for a in all_actions if a["action"] == primary_action["action"])

        unified_signal = {
            "type": primary_action["action"],
            "volume": total_volume,
            "strategies": [a["strategy"] for a in all_actions],
            "confidence": len(all_actions),
        }

        return unified_signal, conflicts
