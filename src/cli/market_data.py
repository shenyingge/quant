from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date

from src.infrastructure.logger_config import configured_logger as logger
from src.trading.trading_day_checker import is_trading_day


def export_minute_history(args: Sequence[str]) -> int:
    """Export minute-history bundle."""
    from src.market_data.minute_history_exporter import main as export_main

    return export_main(list(args))


def export_minute_daily(
    args: Sequence[str],
    *,
    is_trading_day_fn: Callable[[], bool] = is_trading_day,
    date_cls=date,
    export_minute_history_fn: Callable[[Sequence[str]], int] = export_minute_history,
    logger_obj=logger,
) -> int:
    """Export today's minute-history bundle with default task args."""
    if not is_trading_day_fn():
        logger_obj.info("今天不是交易日，跳过分钟行情导出")
        return 0

    trade_date = date_cls.today().strftime("%Y%m%d")
    default_args = ["--trade-date", trade_date, "--listed-only", "--overwrite", "--skip-zip"]
    return export_minute_history_fn(default_args + list(args))


def ingest_minute_history(args: Sequence[str]) -> int:
    """Ingest minute-history bundle into Meta DB."""
    from src.market_data.minute_history_ingestor import main as ingest_main

    return ingest_main(list(args))


def ingest_minute_daily(
    args: Sequence[str],
    *,
    is_trading_day_fn: Callable[[], bool] = is_trading_day,
    date_cls=date,
    ingest_minute_history_fn: Callable[[Sequence[str]], int] = ingest_minute_history,
    logger_obj=logger,
) -> int:
    """Ingest today's minute-history bundle with default task args."""
    if not is_trading_day_fn():
        logger_obj.info("今天不是交易日，跳过分钟行情入库")
        return 0

    trade_date = date_cls.today().strftime("%Y%m%d")
    default_args = ["--trade-date", trade_date, "--listed-only"]
    return ingest_minute_history_fn(default_args + list(args))
