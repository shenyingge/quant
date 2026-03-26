"""统一的日志配置模块。"""

import os
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

_logger_configured = False
_logger_state: dict[str, Optional[str]] = {
    "app_role": None,
    "log_file": None,
    "log_level": None,
}


def _normalize_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_app_role(app_role: Optional[str] = None) -> str:
    raw_value = app_role or os.environ.get("APP_ROLE") or "app"
    normalized = str(raw_value).strip().lower().replace(" ", "_")
    return normalized.replace("/", "_").replace("\\", "_")


def resolve_log_file_path(
    app_role: Optional[str] = None,
    explicit_log_file: Optional[str] = None,
) -> Optional[Path]:
    raw_log_file = explicit_log_file or os.environ.get("LOG_FILE")
    if raw_log_file:
        return Path(raw_log_file)

    log_to_file = _normalize_bool(os.environ.get("LOG_TO_FILE"), default=True)
    if not log_to_file:
        return None

    log_dir = Path(os.environ.get("LOG_DIR", "./logs"))
    role = _resolve_app_role(app_role)
    return log_dir / f"{role.replace('-', '_')}.log"


def setup_logger(
    *,
    app_role: Optional[str] = None,
    log_file: Optional[str] = None,
    reset: bool = False,
):
    """配置全局日志器。"""
    global _logger_configured, _logger_state, configured_logger

    resolved_role = _resolve_app_role(app_role)
    resolved_log_file = resolve_log_file_path(resolved_role, log_file)
    resolved_log_level = os.environ.get("LOG_LEVEL", "DEBUG").upper()

    if (
        _logger_configured
        and not reset
        and _logger_state["app_role"] == resolved_role
        and _logger_state["log_file"] == (str(resolved_log_file) if resolved_log_file else None)
        and _logger_state["log_level"] == resolved_log_level
    ):
        return configured_logger

    logger.remove()
    logger.configure(extra={"app_role": resolved_role})

    if sys.platform.startswith("win"):
        os.environ["PYTHONIOENCODING"] = "utf-8"
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass
        if hasattr(sys.stderr, "reconfigure"):
            try:
                sys.stderr.reconfigure(encoding="utf-8")
            except Exception:
                pass

    log_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {extra[app_role]: <16} | "
        "{process.id}:{thread.name} | {name}:{function}:{line} - {message}"
    )

    logger.add(
        sys.stdout,
        format=log_format,
        level=resolved_log_level,
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )

    if resolved_log_file is not None:
        resolved_log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            str(resolved_log_file),
            format=log_format,
            level=resolved_log_level,
            enqueue=True,
            backtrace=False,
            diagnose=False,
            encoding="utf-8",
            rotation=os.environ.get("LOG_ROTATION", "20 MB"),
            retention=os.environ.get("LOG_RETENTION", "14 days"),
        )

    _logger_configured = True
    _logger_state = {
        "app_role": resolved_role,
        "log_file": str(resolved_log_file) if resolved_log_file else None,
        "log_level": resolved_log_level,
    }
    configured_logger = logger
    return configured_logger


def configure_process_logger(app_role: str, log_file: Optional[str] = None):
    """为当前进程重新配置日志角色和输出文件。"""
    resolved_role = _resolve_app_role(app_role)
    default_log_file = Path(os.environ.get("LOG_DIR", "./logs")) / (
        f"{resolved_role.replace('-', '_')}.log"
    )
    os.environ["APP_ROLE"] = resolved_role
    return setup_logger(
        app_role=resolved_role,
        log_file=log_file or str(default_log_file),
        reset=True,
    )


configured_logger = setup_logger()
logger = configured_logger
