import importlib
import sys


MODULES_TO_CLEAR = [
    "src.infrastructure.notifications",
    "src.infrastructure.notifications.feishu",
    "src.infrastructure.runtime.watchdog_service",
    "src.data_manager",
    "src.data_manager.stock_info",
]


def test_watchdog_import_does_not_hit_notification_cycle():
    for module_name in MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)

    watchdog = importlib.import_module("src.infrastructure.runtime.watchdog_service")

    assert hasattr(watchdog, "run_watchdog_service")
