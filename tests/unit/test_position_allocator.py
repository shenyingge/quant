"""Tests for PositionAllocator."""

from src.strategy.shared.position_allocator import PositionAllocator


def test_position_allocator_init():
    """PositionAllocator can be initialized."""
    allocator = PositionAllocator(total_limit=10000)
    assert allocator.total_limit == 10000


def test_position_allocator_register_strategy():
    """Register strategy with position limit."""
    allocator = PositionAllocator(total_limit=10000)

    allocator.register_strategy("s1", max_position=5000)
    allocator.register_strategy("s2", max_position=5000)

    assert allocator.strategy_limits["s1"] == 5000
    assert allocator.strategy_limits["s2"] == 5000


def test_position_allocator_buy_within_limit():
    """Can buy within position limit."""
    allocator = PositionAllocator(total_limit=10000)
    allocator.register_strategy("s1", max_position=5000)

    allocator.current_positions["s1"] = 3000

    ok, reason = allocator.can_trade("s1", "BUY", 1000)
    assert ok is True


def test_position_allocator_buy_exceeds_limit():
    """Cannot buy beyond position limit."""
    allocator = PositionAllocator(total_limit=10000)
    allocator.register_strategy("s1", max_position=5000)

    allocator.current_positions["s1"] = 3000

    ok, reason = allocator.can_trade("s1", "BUY", 3000)
    assert ok is False
    assert "limit" in reason.lower()


def test_position_allocator_sell_within_position():
    """Can sell within current position."""
    allocator = PositionAllocator(total_limit=10000)
    allocator.register_strategy("s1", max_position=5000)

    allocator.current_positions["s1"] = 1000

    ok, reason = allocator.can_trade("s1", "SELL", 500)
    assert ok is True


def test_position_allocator_sell_exceeds_position():
    """Cannot sell more than current position."""
    allocator = PositionAllocator(total_limit=10000)
    allocator.register_strategy("s1", max_position=5000)

    allocator.current_positions["s1"] = 1000

    ok, reason = allocator.can_trade("s1", "SELL", 1500)
    assert ok is False
    assert "insufficient" in reason.lower()


def test_position_allocator_update_position():
    """Update position after trade."""
    allocator = PositionAllocator(total_limit=10000)
    allocator.register_strategy("s1", max_position=5000)

    allocator.update_position("s1", "BUY", 100)
    assert allocator.current_positions["s1"] == 100

    allocator.update_position("s1", "SELL", 50)
    assert allocator.current_positions["s1"] == 50


def test_position_allocator_get_total_position():
    """Get total position across all strategies."""
    allocator = PositionAllocator(total_limit=10000)
    allocator.register_strategy("s1", max_position=5000)
    allocator.register_strategy("s2", max_position=5000)

    allocator.current_positions["s1"] = 2000
    allocator.current_positions["s2"] = 3000

    total = allocator.get_total_position()
    assert total == 5000


def test_position_allocator_check_total_limit():
    """Check if total position exceeds overall limit."""
    allocator = PositionAllocator(total_limit=5000)
    allocator.register_strategy("s1", max_position=5000)
    allocator.register_strategy("s2", max_position=5000)

    allocator.current_positions["s1"] = 3000
    allocator.current_positions["s2"] = 1000

    ok = allocator.check_total_limit()
    assert ok is True

    allocator.current_positions["s2"] = 3000
    ok = allocator.check_total_limit()
    assert ok is False
