from __future__ import annotations

from collections.abc import Callable, Sequence

from src.infrastructure.config import settings
from src.infrastructure.logger_config import configured_logger as logger
from src.trading.calendar.trading_day_checker import is_trading_day

TRADING_ENGINE_NAME = "交易引擎"


def parse_retry_params(args: Sequence[str]) -> tuple[int, int]:
    """解析交易引擎重试参数。"""
    max_retries = 3
    retry_delay = 60

    for arg in args:
        if arg.startswith("--max-retries="):
            try:
                max_retries = int(arg.split("=", 1)[1])
            except ValueError:
                logger.warning("无效的重试次数参数: {}", arg)
        elif arg.startswith("--retry-delay="):
            try:
                retry_delay = int(arg.split("=", 1)[1])
            except ValueError:
                logger.warning("无效的重试延迟参数: {}", arg)

    return max_retries, retry_delay


def resolve_qmt_session_id(mode: str, *, settings_obj: object = settings) -> int:
    """Resolve the QMT session id used by runtime commands."""
    if mode == "trading-service":
        return int(
            getattr(settings_obj, "qmt_session_id_trading_service", None)
            or getattr(settings_obj, "qmt_session_id")
        )
    return int(getattr(settings_obj, "qmt_session_id"))
def should_skip_non_trading_day(
    component_name: str,
    *,
    is_trading_day_fn: Callable[[], bool] = is_trading_day,
    logger_obj=logger,
) -> bool:
    """在非交易日跳过需要交易日上下文的命令。"""
    if is_trading_day_fn():
        return False

    logger_obj.info("今天不是交易日，跳过启动 {}", component_name)
    return True
