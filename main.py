from __future__ import annotations

import sys
import time
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
from src.cli.shared import (
    STRATEGY_ENGINE_NAME,
    TRADING_ENGINE_NAME,
    get_t0_poll_interval_seconds,
    resolve_qmt_session_id,
    should_skip_non_trading_day,
)
from src.cli.strategy import (
    reconcile_t0_state as cli_reconcile_t0_state,
    run_t0_backtest as cli_run_t0_backtest,
    run_t0_daemon as cli_run_t0_daemon,
    run_t0_diagnose as cli_run_t0_diagnose,
    run_t0_strategy as cli_run_t0_strategy,
    sync_t0_position as cli_sync_t0_position,
)
from src.cli.trading import (
    run_trading_service as cli_run_trading_service,
    run_trading_service_test as cli_run_trading_service_test,
    test_system as cli_test_system,
)
from src.infrastructure.config import settings
from src.infrastructure.logger_config import configure_process_logger
from src.infrastructure.logger_config import configured_logger as logger
from src.trading.trading_day_checker import is_trading_day


def _resolve_qmt_session_id(mode: str) -> int:
    return resolve_qmt_session_id(mode, settings_obj=settings)


def _should_skip_non_trading_day(component_name: str) -> bool:
    return should_skip_non_trading_day(
        component_name,
        is_trading_day_fn=is_trading_day,
        logger_obj=logger,
    )


def _get_t0_poll_interval_seconds() -> int:
    return get_t0_poll_interval_seconds(settings_obj=settings)


def _resolve_app_role(command: Optional[str]) -> str:
    return cli_resolve_app_role(command)


def run_trading_service(args: list[str]) -> int:
    return cli_run_trading_service(args, is_trading_day_fn=is_trading_day, logger_obj=logger)


def run_trading_service_test(args: list[str]) -> int:
    return cli_run_trading_service_test(args, logger_obj=logger)


def test_system(args: list[str]) -> int:
    return cli_test_system(args, logger_obj=logger)


def run_t0_daemon(args: list[str]) -> int:
    return cli_run_t0_daemon(
        args,
        should_skip_non_trading_day_fn=_should_skip_non_trading_day,
        get_t0_poll_interval_seconds_fn=_get_t0_poll_interval_seconds,
        logger_obj=logger,
        time_module=time,
    )


def run_t0_strategy(args: list[str] | None = None) -> int:
    return cli_run_t0_strategy(
        args,
        should_skip_non_trading_day_fn=_should_skip_non_trading_day,
        logger_obj=logger,
    )


def sync_t0_position(args: list[str]) -> int:
    return cli_sync_t0_position(
        args,
        should_skip_non_trading_day_fn=_should_skip_non_trading_day,
        resolve_qmt_session_id_fn=_resolve_qmt_session_id,
        settings_obj=settings,
        logger_obj=logger,
        time_module=time,
    )


def reconcile_t0_state(args: list[str]) -> int:
    return cli_reconcile_t0_state(
        args,
        should_skip_non_trading_day_fn=_should_skip_non_trading_day,
        resolve_qmt_session_id_fn=_resolve_qmt_session_id,
        settings_obj=settings,
        logger_obj=logger,
        time_module=time,
    )


def run_t0_backtest(args: list[str]) -> int:
    return cli_run_t0_backtest(args, logger_obj=logger)


def run_t0_diagnose(args: list[str]) -> int:
    return cli_run_t0_diagnose(args, logger_obj=logger)


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
        "t0-daemon": run_t0_daemon,
        "t0-strategy": run_t0_strategy,
        "t0-sync-position": sync_t0_position,
        "t0-reconcile": reconcile_t0_state,
        "t0-backtest": run_t0_backtest,
        "t0-diagnose": run_t0_diagnose,
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
