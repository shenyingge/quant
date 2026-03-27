"""Backward-compatible wrapper for the renamed strategy engine module."""

from src.strategy.strategy_engine import StrategyEngine

T0Orchestrator = StrategyEngine

__all__ = ["StrategyEngine", "T0Orchestrator"]
