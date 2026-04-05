"""Test notifications module migration maintains backward compatibility."""

import pytest


def test_notifications_old_import():
    """Old import path works."""
    from src.notifications import FeishuNotifier
    assert FeishuNotifier is not None


def test_notifications_new_import():
    """New import path works."""
    from src.infrastructure.notifications.feishu import FeishuNotifier
    assert FeishuNotifier is not None


def test_notifications_are_same_class():
    """Both imports reference same class."""
    from src.notifications import FeishuNotifier as OldNotifier
    from src.infrastructure.notifications.feishu import FeishuNotifier as NewNotifier
    assert OldNotifier is NewNotifier
