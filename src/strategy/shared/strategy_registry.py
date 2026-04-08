"""Strategy runtime registry and dynamic discovery helpers."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable

from src.infrastructure.logger_config import logger
from src.strategy.shared.strategy_contracts import StrategyRuntimeBase

_RUNTIME_REGISTRY: dict[str, type[StrategyRuntimeBase]] = {}


def _normalize_strategy_key(strategy_key: str) -> str:
    normalized = str(strategy_key or "").strip().lower()
    if not normalized:
        raise ValueError("strategy_key is required")
    return normalized


def register_strategy_runtime(strategy_key: str):
    """Register a runtime class under a stable strategy key."""

    normalized_key = _normalize_strategy_key(strategy_key)

    def decorator(runtime_cls: type[StrategyRuntimeBase]) -> type[StrategyRuntimeBase]:
        if not issubclass(runtime_cls, StrategyRuntimeBase):
            raise TypeError("runtime_cls must inherit StrategyRuntimeBase")
        runtime_cls.strategy_key = normalized_key
        _RUNTIME_REGISTRY[normalized_key] = runtime_cls
        return runtime_cls

    return decorator


def get_registered_strategy_keys() -> list[str]:
    return sorted(_RUNTIME_REGISTRY)


def discover_strategy_runtimes(strategy_keys: Iterable[str] | None = None) -> dict[str, type[StrategyRuntimeBase]]:
    """Import strategy runtime modules on demand and return the current registry."""

    if strategy_keys is None:
        import src.strategy.strategies as strategy_packages

        keys_to_import = [module.name for module in pkgutil.iter_modules(strategy_packages.__path__)]
    else:
        keys_to_import = [_normalize_strategy_key(key) for key in strategy_keys]

    for strategy_key in keys_to_import:
        if strategy_key in _RUNTIME_REGISTRY:
            continue

        module_name = f"src.strategy.strategies.{strategy_key}.strategy_engine"
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                logger.debug("Strategy runtime module not found: {}", module_name)
                continue
            raise
        except Exception as exc:
            logger.warning("Failed to import strategy runtime {}: {}", module_name, exc)

    return dict(_RUNTIME_REGISTRY)


def get_strategy_runtime_class(strategy_key: str) -> type[StrategyRuntimeBase]:
    normalized_key = _normalize_strategy_key(strategy_key)
    discover_strategy_runtimes([normalized_key])
    try:
        return _RUNTIME_REGISTRY[normalized_key]
    except KeyError as exc:
        raise KeyError(f"Unknown strategy runtime: {normalized_key}") from exc


def build_strategy_runtime(strategy_key: str, config_path: str | None = None, **kwargs) -> StrategyRuntimeBase:
    """构建策略运行时实例。

    Args:
        strategy_key: 策略标识符（如 't0'）
        config_path: 可选的 YAML 配置文件路径
        **kwargs: 传递给运行时构造函数的其他参数

    Returns:
        策略运行时实例
    """
    runtime_cls = get_strategy_runtime_class(strategy_key)

    # 如果提供了配置文件，加载参数
    if config_path:
        from src.strategy.config_loader import load_t0_strategy_config
        params = load_t0_strategy_config(config_path)
        kwargs['params'] = params

    return runtime_cls(**kwargs)

