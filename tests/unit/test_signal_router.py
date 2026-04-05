"""Tests for SignalRouter."""

from src.strategy.shared.signal_router import ConflictRecord, SignalRouter


def test_signal_router_init():
    """SignalRouter can be initialized."""
    router = SignalRouter()
    assert router is not None


def test_signal_router_no_signals():
    """Router returns None when no signals."""
    router = SignalRouter()

    unified, conflicts = router.route_signals(
        stock_code="601138.SH",
        signals=[],
    )

    assert unified is None
    assert len(conflicts) == 0


def test_signal_router_single_signal():
    """Router passes through single signal."""
    router = SignalRouter()

    signals = [("s1", [{"type": "BUY", "volume": 100}])]

    unified, conflicts = router.route_signals(
        stock_code="601138.SH",
        signals=signals,
    )

    assert unified is not None
    assert unified["type"] == "BUY"
    assert unified["volume"] == 100
    assert len(conflicts) == 0


def test_signal_router_same_direction_signals():
    """Router aggregates same-direction signals."""
    router = SignalRouter()

    signals = [
        ("s1", [{"type": "BUY", "volume": 100}]),
        ("s2", [{"type": "BUY", "volume": 50}]),
    ]

    unified, conflicts = router.route_signals(
        stock_code="601138.SH",
        signals=signals,
    )

    assert unified is not None
    assert unified["type"] == "BUY"
    assert unified["volume"] == 150
    assert len(conflicts) == 0


def test_signal_router_opposite_direction_conflict():
    """Router detects opposite-direction signals as conflict."""
    router = SignalRouter()

    signals = [
        ("s1", [{"type": "BUY", "volume": 100}]),
        ("s2", [{"type": "SELL", "volume": 100}]),
    ]

    unified, conflicts = router.route_signals(
        stock_code="601138.SH",
        signals=signals,
    )

    # Should detect conflict
    assert len(conflicts) > 0
    assert unified is not None
    assert unified["type"] in ["NEUTRAL", "BUY", "SELL"]


def test_signal_router_conflict_record():
    """ConflictRecord captures conflict details."""
    record = ConflictRecord(
        stock_code="601138.SH",
        strategy_name="s1",
        signal_type="BUY",
        volume=100,
        reason="Multi-direction conflict",
    )

    assert record.stock_code == "601138.SH"
    assert record.strategy_name == "s1"
    assert record.signal_type == "BUY"


def test_signal_router_neutral_with_other_signals():
    """Router ignores NEUTRAL signals when other signals exist."""
    router = SignalRouter()

    signals = [
        ("s1", [{"type": "NEUTRAL"}]),
        ("s2", [{"type": "BUY", "volume": 100}]),
    ]

    unified, conflicts = router.route_signals(
        stock_code="601138.SH",
        signals=signals,
    )

    # Should use BUY signal
    assert unified["type"] == "BUY"
    assert len(conflicts) == 0
