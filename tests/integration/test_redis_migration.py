"""Test redis_listener module migration maintains backward compatibility."""

import pytest


def test_redis_listener_old_import():
    """Old import path works."""
    from src.redis_listener import RedisSignalListener
    assert RedisSignalListener is not None


def test_redis_listener_new_import():
    """New import path works."""
    from src.infrastructure.redis.signal_listener import RedisSignalListener
    assert RedisSignalListener is not None


def test_redis_listener_same_class():
    """Both paths reference same class."""
    from src.redis_listener import RedisSignalListener as OldListener
    from src.infrastructure.redis.signal_listener import RedisSignalListener as NewListener
    assert OldListener is NewListener
