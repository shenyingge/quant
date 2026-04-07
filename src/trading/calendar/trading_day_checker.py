"""Trading-day checks backed by Meta DB with QMT/Tushare fallback."""

from datetime import date, datetime
import threading
from typing import Optional

from sqlalchemy import text

from src.infrastructure.config import settings
from src.infrastructure.db import SessionLocal
from src.infrastructure.logger_config import configured_logger as logger


_trading_day_cache_lock = threading.Lock()
_trading_day_cache = {}


def _resolve_check_date(check_date: Optional[date] = None) -> date:
    if check_date is not None:
        return check_date
    return datetime.now().date()


def _resolve_trading_calendar_schema() -> str:
    schema = (settings.meta_db_schema or "").strip() or "gold"
    normalized = schema.replace("_", "")
    if not normalized.isalnum():
        logger.warning(
            "META_DB_SCHEMA value {!r} is invalid for trading-day lookup, falling back to gold",
            schema,
        )
        return "gold"
    return schema


def _check_with_database(current_date: date) -> Optional[bool]:
    current_date_str = current_date.strftime("%Y%m%d")
    schema = _resolve_trading_calendar_schema()
    session = SessionLocal()

    try:
        logger.info("Checking trading day for {} via Meta DB {}.trade_cal", current_date_str, schema)
        statement = text(
            f'SELECT is_open FROM "{schema}".trade_cal WHERE cal_date = :check_date LIMIT 1'
        )
        result = session.execute(statement, {"check_date": current_date_str}).scalar_one_or_none()

        if result is None:
            logger.warning(
                "Meta DB returned no trade_cal row for {}, falling back to QMT",
                current_date_str,
            )
            return None

        normalized = str(result).strip().lower()
        is_open = normalized in {"1", "true", "t", "yes"}
        if is_open:
            logger.info("{} is a trading day (Meta DB)", current_date_str)
        else:
            logger.info("{} is not a trading day (Meta DB)", current_date_str)
        return is_open
    except Exception as exc:
        logger.warning("Meta DB trading-day check failed, falling back to QMT: {}", exc)
        return None
    finally:
        session.close()


def _check_with_tushare(current_date: date) -> Optional[bool]:
    current_date_str = current_date.strftime("%Y%m%d")
    if not settings.tushare_token:
        logger.warning("TUSHARE_TOKEN is not configured, skipping Tushare trading-day check")
        return None

    try:
        import tushare as ts

        logger.info("Checking trading day for {} via Tushare", current_date_str)
        pro = ts.pro_api(settings.tushare_token)
        calendar_df = pro.trade_cal(
            exchange=settings.tushare_trade_calendar_exchange,
            start_date=current_date_str,
            end_date=current_date_str,
            fields="exchange,cal_date,is_open,pretrade_date",
        )

        if calendar_df is None or calendar_df.empty:
            logger.warning(
                "Tushare returned no calendar data for {}, falling back to QMT",
                current_date_str,
            )
            return None

        row = calendar_df.iloc[0]
        is_open = str(row.get("is_open", "0")).strip() == "1"

        if is_open:
            logger.info("{} is a trading day", current_date_str)
        else:
            logger.info("{} is not a trading day", current_date_str)
            pretrade_date = str(row.get("pretrade_date", "")).strip()
            if pretrade_date:
                logger.info("Previous trading day: {}", pretrade_date)

        return is_open
    except Exception as exc:
        logger.warning("Tushare trading-day check failed, falling back to QMT: {}", exc)
        return None


def _check_with_qmt(current_date: date) -> Optional[bool]:
    current_date_str = current_date.strftime("%Y%m%d")
    start_date = f"{current_date.year}0101"
    end_date = f"{current_date.year}1231"

    try:
        from xtquant import xtdata

        logger.info("Checking trading day for {} via QMT", current_date_str)
        try:
            if hasattr(xtdata, "download_holiday_data"):
                xtdata.download_holiday_data()
        except Exception as exc:
            logger.debug("QMT holiday refresh failed, continuing with cached data: {}", exc)

        trading_calendar = xtdata.get_trading_calendar("SH", start_date, end_date)
        if not trading_calendar:
            logger.error("QMT returned no trading calendar data for {}", current_date.year)
            return None

        is_open = current_date_str in trading_calendar
        if is_open:
            logger.info("{} is a trading day (QMT)", current_date_str)
        else:
            logger.info("{} is not a trading day (QMT)", current_date_str)
        return is_open
    except Exception as exc:
        logger.error("QMT trading-day check failed: {}", exc)
        return None


def resolve_trading_day_status(check_date: Optional[date] = None) -> Optional[bool]:
    """Return trading-day status when providers can answer, otherwise None."""
    if settings.test_mode_enabled:
        logger.info("Test mode enabled, skipping trading-day check")
        return True

    if not settings.trading_day_check_enabled:
        logger.info("Trading-day check disabled, skipping trading-day check")
        return True

    current_date = _resolve_check_date(check_date)

    with _trading_day_cache_lock:
        cached_result = _trading_day_cache.get(current_date)
    if cached_result is not None:
        return cached_result

    database_result = _check_with_database(current_date)
    if database_result is not None:
        with _trading_day_cache_lock:
            _trading_day_cache[current_date] = database_result
        return database_result

    qmt_result = _check_with_qmt(current_date)
    if qmt_result is not None:
        with _trading_day_cache_lock:
            _trading_day_cache[current_date] = qmt_result
        return qmt_result

    tushare_result = _check_with_tushare(current_date)
    if tushare_result is not None:
        with _trading_day_cache_lock:
            _trading_day_cache[current_date] = tushare_result
        return tushare_result

    return None


def is_trading_day(check_date: Optional[date] = None) -> bool:
    """
    Check whether a date is a trading day.

    Returns:
        True when the market is open on the given date, otherwise False.
    """
    status = resolve_trading_day_status(check_date)
    if status is not None:
        return status

    logger.error(
        "Both Tushare and QMT failed to determine trading-day status; defaulting to non-trading day"
    )
    return False
