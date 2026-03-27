import importlib
import sys


def test_notifications_import_does_not_trigger_strategy_cycle():
    for module_name in [
        "src.notifications",
        "src.strategy",
        "src.strategy.strategy_engine",
        "src.strategy.t0_orchestrator",
    ]:
        sys.modules.pop(module_name, None)

    notifications = importlib.import_module("src.notifications")

    assert hasattr(notifications, "FeishuNotifier")
