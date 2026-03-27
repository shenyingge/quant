"""Backward-compatible wrapper for the renamed trading engine module."""

from src.trading_engine import TradingEngine

TradingService = TradingEngine

__all__ = ["TradingEngine", "TradingService"]
