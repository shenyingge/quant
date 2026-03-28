"""Trading-day checks backed by Tushare with QMT fallback."""

from datetime import date, datetime
from typing import Optional

from src.config import settings
from src.logger_config import configured_logger as logger


def _resolve_check_date(check_date: Optional[date] = None) -> date:
    if check_date is not None:
        return check_date
    return datetime.now().date()


def _check_with_tushare(current_date: date) -> Optional[bool]:
    current_date_str = current_date.strftime("%Y%m%d")
    if not settings.tushare_token:
        logger.warning("未配置 TUSHARE_TOKEN，改为使用 QMT 检查交易日")
        return None

    try:
        import tushare as ts

        logger.info(f"正在通过 Tushare 检查 {current_date_str} 是否为交易日...")
        pro = ts.pro_api(settings.tushare_token)
        calendar_df = pro.trade_cal(
            exchange=settings.tushare_trade_calendar_exchange,
            start_date=current_date_str,
            end_date=current_date_str,
            fields="exchange,cal_date,is_open,pretrade_date",
        )

        if calendar_df is None or calendar_df.empty:
            logger.warning(f"Tushare 未返回 {current_date_str} 的交易日历数据，改为使用 QMT 检查")
            return None

        row = calendar_df.iloc[0]
        is_open = str(row.get("is_open", "0")).strip() == "1"

        if is_open:
            logger.info(f"{current_date_str} 是交易日")
        else:
            logger.info(f"{current_date_str} 不是交易日")
            pretrade_date = str(row.get("pretrade_date", "")).strip()
            if pretrade_date:
                logger.info(f"上一个交易日: {pretrade_date}")

        return is_open
    except Exception as exc:
        logger.warning(f"通过 Tushare 检查交易日失败，将回退到 QMT: {exc}")
        return None


def _check_with_qmt(current_date: date) -> Optional[bool]:
    current_date_str = current_date.strftime("%Y%m%d")
    start_date = f"{current_date.year}0101"
    end_date = f"{current_date.year}1231"

    try:
        from xtquant import xtdata

        logger.info(f"正在通过 QMT 检查 {current_date_str} 是否为交易日...")
        try:
            if hasattr(xtdata, "download_holiday_data"):
                xtdata.download_holiday_data()
        except Exception as exc:
            logger.debug(f"QMT 交易日历刷新失败，继续使用已有数据: {exc}")

        trading_calendar = xtdata.get_trading_calendar("SH", start_date, end_date)
        if not trading_calendar:
            logger.error(f"QMT 未返回 {current_date.year} 年交易日历数据")
            return None

        is_open = current_date_str in trading_calendar
        if is_open:
            logger.info(f"{current_date_str} 是交易日（QMT）")
        else:
            logger.info(f"{current_date_str} 不是交易日（QMT）")
        return is_open
    except Exception as exc:
        logger.error(f"通过 QMT 检查交易日失败: {exc}")
        return None


def is_trading_day(check_date: Optional[date] = None) -> bool:
    """
    Check whether a date is a trading day.

    Returns:
        True when the market is open on the given date, otherwise False.
    """
    if settings.test_mode_enabled:
        logger.info("测试模式已启用，跳过交易日检查")
        return True

    if not settings.trading_day_check_enabled:
        logger.info("交易日检查已禁用，跳过检查")
        return True

    current_date = _resolve_check_date(check_date)

    tushare_result = _check_with_tushare(current_date)
    if tushare_result is not None:
        return tushare_result

    qmt_result = _check_with_qmt(current_date)
    if qmt_result is not None:
        return qmt_result

    logger.error("Tushare 和 QMT 都无法确认交易日状态，默认按非交易日处理")
    return False
