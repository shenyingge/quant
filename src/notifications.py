"""Backward compatibility wrapper for src.notifications -> src.infrastructure.notifications migration.

All notification implementations have been migrated to
src.infrastructure.notifications. This module now re-exports them for backward compatibility.
"""

from src.infrastructure.notifications.feishu import FeishuNotifier

__all__ = ["FeishuNotifier"]
