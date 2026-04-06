from __future__ import annotations

from collections.abc import Callable, Sequence

from src.infrastructure.config import settings
from src.infrastructure.logger_config import configured_logger as logger
from src.trading.calendar.trading_day_checker import is_trading_day

STRATEGY_ENGINE_NAME = "策略引擎"
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
    """按模式解析 QMT session id。"""
    session_id_map = {
        "trading-service": getattr(settings_obj, "qmt_session_id_trading_service", None),
        "t0-daemon": getattr(settings_obj, "qmt_session_id_t0_daemon", None),
        "t0-sync": getattr(settings_obj, "qmt_session_id_t0_sync", None),
    }
    return int(session_id_map.get(mode) or getattr(settings_obj, "qmt_session_id"))


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


def get_t0_poll_interval_seconds(*, settings_obj: object = settings) -> int:
    """读取并规整 T+0 守护轮询间隔。"""
    return max(int(getattr(settings_obj, "t0_poll_interval_seconds", 60)), 1)
