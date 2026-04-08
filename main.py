from __future__ import annotations

import sys
from datetime import date
from typing import Optional

from src.cli.market_data import (
    export_minute_daily as cli_export_minute_daily,
    export_minute_history as cli_export_minute_history,
    ingest_minute_daily as cli_ingest_minute_daily,
    ingest_minute_history as cli_ingest_minute_history,
)
from src.cli.ops import (
    run_cms_check as cli_run_cms_check,
    run_cms_server as cli_run_cms_server,
    run_watchdog as cli_run_watchdog,
    sync_account_positions as cli_sync_account_positions,
)
from src.cli.registry import COMMANDS as REGISTRY_COMMANDS
from src.cli.registry import print_usage as cli_print_usage
from src.cli.registry import resolve_app_role as cli_resolve_app_role
from src.cli.shared import TRADING_ENGINE_NAME
from src.cli.trading import (
    run_trading_service as cli_run_trading_service,
    run_trading_service_test as cli_run_trading_service_test,
    test_system as cli_test_system,
)
from src.infrastructure.config import settings
from src.infrastructure.logger_config import configure_process_logger
from src.infrastructure.logger_config import configured_logger as logger
from src.trading.calendar.trading_day_checker import is_trading_day

def _resolve_app_role(command: Optional[str]) -> str:
    return cli_resolve_app_role(command)


def run_trading_service(args: list[str]) -> int:
    return cli_run_trading_service(args, is_trading_day_fn=is_trading_day, logger_obj=logger)


def run_trading_service_test(args: list[str]) -> int:
    return cli_run_trading_service_test(args, logger_obj=logger)


def test_system(args: list[str]) -> int:
    return cli_test_system(args, logger_obj=logger)


def run_cms_check(args: list[str]) -> int:
    return cli_run_cms_check(args, logger_obj=logger)


def sync_account_positions(args: list[str]) -> int:
    return cli_sync_account_positions(args, logger_obj=logger)


def run_cms_server(args: list[str]) -> int:
    return cli_run_cms_server(args, settings_obj=settings, logger_obj=logger)


def run_watchdog(args: list[str]) -> int:
    return cli_run_watchdog(args)


def export_minute_history(args: list[str]) -> int:
    return cli_export_minute_history(args)


def export_minute_daily(args: list[str]) -> int:
    return cli_export_minute_daily(
        args,
        is_trading_day_fn=is_trading_day,
        date_cls=date,
        export_minute_history_fn=export_minute_history,
        logger_obj=logger,
    )


def ingest_minute_history(args: list[str]) -> int:
    return cli_ingest_minute_history(args)


def ingest_minute_daily(args: list[str]) -> int:
    return cli_ingest_minute_daily(
        args,
        is_trading_day_fn=is_trading_day,
        date_cls=date,
        ingest_minute_history_fn=ingest_minute_history,
        logger_obj=logger,
    )


COMMANDS = dict(REGISTRY_COMMANDS)
COMMANDS.update(
    {
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
)


def print_usage() -> None:
    cli_print_usage(logger_obj=logger)


def main() -> int:
    command = sys.argv[1].lower() if len(sys.argv) > 1 else None
    configure_process_logger(_resolve_app_role(command))

    if command != "cms-check":
        logger.info("QMT服务 v{}", settings.__dict__.get("version", "1.0.0"))
        logger.info("=" * 50)

    if command not in COMMANDS:
        print_usage()
        return 1

    try:
        return COMMANDS[command](sys.argv[2:])
    except Exception as exc:
        logger.error("命令执行失败: {}", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
