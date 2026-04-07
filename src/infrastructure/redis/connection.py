"""Shared Redis connection helpers."""

from __future__ import annotations

from typing import Any, Dict

from src.infrastructure.config import settings


def _normalize_credential(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    return value


def build_redis_client_kwargs(**overrides: Any) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "host": getattr(settings, "redis_host", "localhost"),
        "port": getattr(settings, "redis_port", 6379),
    }

    username = _normalize_credential(getattr(settings, "redis_username", None))
    password = _normalize_credential(getattr(settings, "redis_password", None))

    if username is not None:
        kwargs["username"] = username
    if password is not None:
        kwargs["password"] = password

    kwargs.update(overrides)
    return kwargs