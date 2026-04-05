"""Backward compatibility wrapper for src.redis_listener -> src.infrastructure.redis migration.

All Redis listener implementations have been migrated to
src.infrastructure.redis. This module now re-exports them for backward compatibility.
"""

from src.infrastructure.redis.signal_listener import RedisSignalListener

__all__ = ["RedisSignalListener"]
