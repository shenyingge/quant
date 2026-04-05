"""Test trader module migration maintains backward compatibility."""

import pytest


def test_trader_old_import():
    """Old import path works."""
    from src.trader import QMTTrader
    assert QMTTrader is not None


def test_trader_new_import():
    """New import path works."""
    from src.trading.execution.qmt_trader import QMTTrader
    assert QMTTrader is not None


def test_trader_same_class():
    """Both paths reference same class."""
    from src.trader import QMTTrader as OldTrader
    from src.trading.execution.qmt_trader import QMTTrader as NewTrader
    assert OldTrader is NewTrader
