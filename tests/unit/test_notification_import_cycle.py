import importlib
import sys


def test_notifications_import_does_not_trigger_strategy_cycle():
    for module_name in [
        "src.infrastructure.notifications",
        "src.infrastructure.notifications.feishu",
        "src.strategy",
        "src.strategy.strategies.t0.strategy_engine",
    ]:
        sys.modules.pop(module_name, None)

    notifications = importlib.import_module("src.infrastructure.notifications")

    assert hasattr(notifications, "FeishuNotifier")
