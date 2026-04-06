"""Test Phase 4 configuration settings."""

from src.infrastructure.config import settings


def test_config_has_t0_max_strategies():
    """Config has T0_MAX_STRATEGIES setting."""
    assert hasattr(settings, "t0_max_strategies")
    assert isinstance(settings.t0_max_strategies, int)
    assert settings.t0_max_strategies > 0


def test_config_has_t0_position_limit_per_strategy():
    """Config has T0_POSITION_LIMIT_PER_STRATEGY setting."""
    assert hasattr(settings, "t0_position_limit_per_strategy")
    assert isinstance(settings.t0_position_limit_per_strategy, int)
    assert settings.t0_position_limit_per_strategy > 0


def test_config_has_t0_conflict_resolution_mode():
    """Config has T0_CONFLICT_RESOLUTION_MODE setting."""
    assert hasattr(settings, "t0_conflict_resolution_mode")
    assert settings.t0_conflict_resolution_mode in ["strict", "lenient"]
