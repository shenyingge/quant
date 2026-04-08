from __future__ import annotations

from collections.abc import Callable, Sequence

from src.infrastructure.logger_config import configured_logger as logger

from src.cli.market_data import (
    export_minute_daily,
    export_minute_history,
    ingest_minute_daily,
    ingest_minute_history,
)
from src.cli.ops import run_cms_check, run_cms_server, run_watchdog, sync_account_positions
from src.cli.shared import TRADING_ENGINE_NAME
from src.cli.trading import run_trading_service, run_trading_service_test, test_system

CommandHandler = Callable[[Sequence[str]], int]


COMMANDS: dict[str, CommandHandler] = {
    "run": run_trading_service,
    "test-run": run_trading_service_test,
    "test": test_system,
    "cms-check": run_cms_check,
    "sync-account-positions": sync_account_positions,
    "cms-server": run_cms_server,
    "watchdog": run_watchdog,
    "export-minute-history": export_minute_history,
    "export-minute-daily": export_minute_daily,
    "ingest-minute-history": ingest_minute_history,
    "ingest-minute-daily": ingest_minute_daily,
}


def resolve_app_role(command: str | None) -> str:
    """Resolve logger role from command name."""
    role_map = {
        "run": "trading_engine",
        "test-run": "trading_engine",
        "test": "system_test",
        "cms-check": "cms_server",
        "sync-account-positions": "cms_server",
        "cms-server": "cms_server",
        "watchdog": "watchdog",
        "export-minute-history": "minute_history_export",
        "export-minute-daily": "minute_history_export",
        "ingest-minute-history": "minute_history_ingest",
        "ingest-minute-daily": "minute_history_ingest",
    }
    return role_map.get(command or "", "cli")


def print_usage(*, logger_obj=logger) -> None:
    """Print CLI usage."""
    logger_obj.info("使用方法:")
    logger_obj.info("")
    logger_obj.info("交易引擎:")
    logger_obj.info("  python main.py run                    - 运行 {}", TRADING_ENGINE_NAME)
    logger_obj.info("  python main.py test-run               - 测试模式运行 {}", TRADING_ENGINE_NAME)
    logger_obj.info("  python main.py test                   - 运行系统连接检查")
    logger_obj.info("")
    logger_obj.info("监控:")
    logger_obj.info("  python main.py cms-check              - 输出 CMS check JSON 结果")
    logger_obj.info("  python main.py sync-account-positions - 从 QMT 手动刷新 Meta DB 持仓快照")
    logger_obj.info("  python main.py cms-server             - 启动独立常驻的 HTTP /health CMS 服务")
    logger_obj.info("  python main.py watchdog               - 启动 24x7 看门狗服务")
    logger_obj.info("")
    logger_obj.info("分钟行情:")
    logger_obj.info("  python main.py export-minute-history  - 导出分钟历史行情包")
    logger_obj.info("  python main.py export-minute-daily    - 按日任务导出当日分钟行情包")
    logger_obj.info("  python main.py ingest-minute-history  - 分钟历史行情入库")
    logger_obj.info("  python main.py ingest-minute-daily    - 按日任务入库当日分钟行情")
    logger_obj.info("")
    logger_obj.info("重试参数（仅适用于 run / test-run）:")
    logger_obj.info("  --max-retries=N                       - 最大重试次数（默认: 3）")
    logger_obj.info("  --retry-delay=N                       - 重试间隔秒数（默认: 60）")
