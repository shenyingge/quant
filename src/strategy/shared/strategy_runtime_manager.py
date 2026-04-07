"""Runtime manager for loading and executing registered strategy runtimes."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Iterable

from src.infrastructure.logger_config import logger
from src.strategy.shared.strategy_registry import build_strategy_runtime, discover_strategy_runtimes


class StrategyRuntimeManager:
    """Load registered strategy runtimes and execute them sequentially or in parallel."""

    def __init__(self, strategy_keys: Iterable[str] | None = None, *, max_workers: int = 1):
        self.strategy_keys = list(strategy_keys or [])
        self.max_workers = max(int(max_workers), 1)
        self.runtimes: dict[str, object] = {}

    def load_runtimes(self, strategy_keys: Iterable[str] | None = None) -> dict[str, object]:
        keys = list(strategy_keys or self.strategy_keys)
        if not keys:
            keys = list(discover_strategy_runtimes().keys())

        self.runtimes = {key: build_strategy_runtime(key) for key in keys}
        return dict(self.runtimes)

    def run_once_all(self, *, parallel: bool = False) -> dict[str, dict]:
        if not self.runtimes:
            self.load_runtimes()

        if parallel and len(self.runtimes) > 1 and self.max_workers > 1:
            return self._run_in_parallel()
        return self._run_sequentially()

    def _run_sequentially(self) -> dict[str, dict]:
        results: dict[str, dict] = {}
        for strategy_key, runtime in self.runtimes.items():
            results[strategy_key] = self._run_runtime(strategy_key, runtime)
        return results

    def _run_in_parallel(self) -> dict[str, dict]:
        results: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_map = {
                executor.submit(self._run_runtime, strategy_key, runtime): strategy_key
                for strategy_key, runtime in self.runtimes.items()
            }
            for future in as_completed(future_map):
                strategy_key = future_map[future]
                results[strategy_key] = future.result()
        return results

    def _run_runtime(self, strategy_key: str, runtime) -> dict:
        try:
            return runtime.run_once()
        except Exception as exc:
            logger.error("Strategy runtime %s failed during run_once: %s", strategy_key, exc)
            return {
                "strategy": strategy_key,
                "status": "error",
                "error": str(exc),
            }

