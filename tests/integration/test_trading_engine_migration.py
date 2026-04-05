"""Test trading_engine module migration maintains backward compatibility."""

import pytest


def test_trading_engine_old_import():
    """Old import path works."""
    from src.trading_engine import TradingEngine
    assert TradingEngine is not None


def test_trading_engine_new_import():
    """New import path works."""
    from src.trading.runtime.engine import TradingEngine
    assert TradingEngine is not None


def test_trading_engine_same_class():
    """Both paths reference same class."""
    from src.trading_engine import TradingEngine as OldEngine
    from src.trading.runtime.engine import TradingEngine as NewEngine
    assert OldEngine is NewEngine
