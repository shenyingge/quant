"""Compatibility wrapper for T0StrategyKernel migration to t0/core."""

# This module maintains backwards compatibility during the Phase 4 refactoring
# where T0StrategyKernel is being migrated to src/strategy/t0/core/

try:
    from src.strategy.t0.core.engine import T0StrategyKernel  # noqa: F401
except ImportError:
    # If t0/core doesn't exist yet, provide a placeholder
    T0StrategyKernel = None

__all__ = ["T0StrategyKernel"]
