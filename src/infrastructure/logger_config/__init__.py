"""Centralized Loguru configuration for all runtime processes."""

from __future__ import annotations

import gzip
import os
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Callable, Optional

from loguru import logger
from src.infrastructure.config import settings

_logger_configured = False
_logger_state: dict[str, Optional[str]] = {
    "app_role": None,
    "log_file": None,
    "log_level": None,
    "log_rotation": None,
    "log_retention": None,
    "log_compression": None,
    "log_archive_dir": None,
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


def _resolve_log_active_dir() -> Path:
    raw_value = (
        os.environ.get("LOG_ACTIVE_DIR")
        or os.environ.get("LOG_DIR")
        or settings.log_dir
        or "./logs/current"
    )
    return Path(raw_value)


def _resolve_log_archive_dir() -> Path:
    raw_value = os.environ.get("LOG_ARCHIVE_DIR") or settings.log_archive_dir or "./logs/archive"
    return Path(raw_value)


def build_role_log_file_path(app_role: Optional[str] = None) -> Path:
    role = _resolve_app_role(app_role)
    return _resolve_log_active_dir() / f"{role.replace('-', '_')}.log"


def resolve_log_file_path(
    app_role: Optional[str] = None,
    explicit_log_file: Optional[str] = None,
) -> Optional[Path]:
    if explicit_log_file:
        return Path(explicit_log_file)

    log_to_file = _normalize_bool(os.environ.get("LOG_TO_FILE"), default=True)
    if not log_to_file:
        return None

    return build_role_log_file_path(app_role)


def _parse_retention_seconds(raw_value: Optional[str]) -> int:
    default_seconds = 30 * 24 * 60 * 60
    if not raw_value:
        return default_seconds

    value = str(raw_value).strip().lower()
    if not value:
        return default_seconds

    if value.isdigit():
        return int(value) * 24 * 60 * 60

    match = re.fullmatch(
        r"(\d+)\s*(second|seconds|minute|minutes|hour|hours|day|days|week|weeks)",
        value,
    )
    if not match:
        return default_seconds

    amount = int(match.group(1))
    unit = match.group(2)
    unit_seconds = {
        "second": 1,
        "seconds": 1,
        "minute": 60,
        "minutes": 60,
        "hour": 60 * 60,
        "hours": 60 * 60,
        "day": 24 * 60 * 60,
        "days": 24 * 60 * 60,
        "week": 7 * 24 * 60 * 60,
        "weeks": 7 * 24 * 60 * 60,
    }
    return amount * unit_seconds[unit]


def _ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = "".join(path.suffixes)
    counter = 1
    while True:
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _cleanup_archived_logs(archive_dir: Path, retention_seconds: int) -> None:
    if retention_seconds <= 0 or not archive_dir.exists():
        return

    cutoff = time.time() - retention_seconds
    for candidate in archive_dir.rglob("*"):
        if not candidate.is_file():
            continue
        try:
            if candidate.stat().st_mtime < cutoff:
                candidate.unlink()
        except OSError:
            continue

    for directory in sorted(
        (path for path in archive_dir.rglob("*") if path.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        try:
            if not any(directory.iterdir()):
                directory.rmdir()
        except OSError:
            continue


def _compress_to_zip(source_path: Path, target_path: Path) -> None:
    with zipfile.ZipFile(target_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(source_path, arcname=source_path.name)


def _compress_to_gzip(source_path: Path, target_path: Path) -> None:
    with source_path.open("rb") as source_handle, gzip.open(target_path, "wb") as target_handle:
        shutil.copyfileobj(source_handle, target_handle)


def _build_archive_handler(app_role: Optional[str]) -> Callable[[str], None]:
    archive_root = _resolve_log_archive_dir()
    role = _resolve_app_role(app_role)
    compression_format = (
        os.environ.get("LOG_COMPRESSION") or settings.log_compression or "zip"
    ).strip().lower()
    retention_seconds = _parse_retention_seconds(
        os.environ.get("LOG_RETENTION") or settings.log_retention or "30 days"
    )

    def _archive(rotated_log_path: str) -> None:
        source_path = Path(rotated_log_path)
        if not source_path.exists():
            return

        target_dir = archive_root / role
        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            if compression_format in {"", "none", "off"}:
                target_path = _ensure_unique_path(target_dir / source_path.name)
                shutil.move(str(source_path), str(target_path))
            elif compression_format == "gz":
                target_path = _ensure_unique_path(target_dir / f"{source_path.name}.gz")
                _compress_to_gzip(source_path, target_path)
                source_path.unlink()
            else:
                target_path = _ensure_unique_path(target_dir / f"{source_path.name}.zip")
                _compress_to_zip(source_path, target_path)
                source_path.unlink()
        except Exception as exc:  # pragma: no cover - best effort archival
            try:
                sys.stderr.write(f"Failed to archive rotated log {source_path}: {exc}\n")
            except Exception:
                pass
            return

        _cleanup_archived_logs(target_dir, retention_seconds)

    return _archive


def setup_logger(
    *,
    app_role: Optional[str] = None,
    log_file: Optional[str] = None,
    reset: bool = False,
):
    """Configure the process-wide logger."""
    global _logger_configured, _logger_state, configured_logger

    resolved_role = _resolve_app_role(app_role)
    resolved_log_file = resolve_log_file_path(resolved_role, log_file)
    resolved_log_level = (os.environ.get("LOG_LEVEL") or settings.log_level or "DEBUG").upper()
    resolved_log_rotation = os.environ.get("LOG_ROTATION") or settings.log_rotation or "20 MB"
    resolved_log_retention = os.environ.get("LOG_RETENTION") or settings.log_retention or "30 days"
    resolved_log_compression = (
        os.environ.get("LOG_COMPRESSION") or settings.log_compression or "zip"
    )
    resolved_log_archive_dir = str(_resolve_log_archive_dir())

    if (
        _logger_configured
        and not reset
        and _logger_state["app_role"] == resolved_role
        and _logger_state["log_file"] == (str(resolved_log_file) if resolved_log_file else None)
        and _logger_state["log_level"] == resolved_log_level
        and _logger_state["log_rotation"] == resolved_log_rotation
        and _logger_state["log_retention"] == resolved_log_retention
        and _logger_state["log_compression"] == resolved_log_compression
        and _logger_state["log_archive_dir"] == resolved_log_archive_dir
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
            rotation=resolved_log_rotation,
            retention=None,
            compression=_build_archive_handler(resolved_role),
        )

    _logger_configured = True
    _logger_state = {
        "app_role": resolved_role,
        "log_file": str(resolved_log_file) if resolved_log_file else None,
        "log_level": resolved_log_level,
        "log_rotation": resolved_log_rotation,
        "log_retention": resolved_log_retention,
        "log_compression": resolved_log_compression,
        "log_archive_dir": resolved_log_archive_dir,
    }
    configured_logger = logger
    return configured_logger


def configure_process_logger(app_role: str, log_file: Optional[str] = None):
    """Reconfigure logging for a specific runtime process role."""
    resolved_role = _resolve_app_role(app_role)
    default_log_file = build_role_log_file_path(resolved_role)
    os.environ["APP_ROLE"] = resolved_role
    return setup_logger(
        app_role=resolved_role,
        log_file=log_file or str(default_log_file),
        reset=True,
    )


configured_logger = setup_logger()
logger = configured_logger
