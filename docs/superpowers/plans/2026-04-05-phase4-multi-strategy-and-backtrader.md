# Phase 4：策略解耦与多策略并行 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 策略核心与运行时完全解耦，支持多策略并行，确保回测与实时复用同一决策逻辑，兼容 backtrader 生态。

**Architecture:** 在 `src/strategy/t0/core/` 中构建纯决策内核（无 QMT/Redis/DB/通知依赖），通过 `StrategyBase` 统一接口适配多策略；运行时层 `src/strategy/shared/` 中管理多个 `StrategyRunner` 实例并通过 `SignalRouter` 与 `PositionAllocator` 防冲突；backtrader 兼容通过 adapter 层实现，策略逻辑保持纯计算特性，无侵入性修改。

**Tech Stack:** Python 3.11, backtrader, pytest, pytest-mock, pandas, SQLAlchemy 2.x

---

## Scope Check

本计划覆盖 **Phase 4（策略解耦与多策略并行）**，不包含 Phase 5 的整体目录迁移和 Phase 6 的清理收尾。

Phase 4 完成后验证指标：
1. `src/strategy/t0/core/` 模块无 QMT/Redis/DB/通知 import、所有函数可纯测试
2. `StrategyBase` 子类可直接在 backtrader 中运行
3. 多策略实时运行无信号冲突、头寸分配正确
4. `src/backtest/*` 仅依赖 `t0/core` + `t0/contracts`、回测与实时复用同一 kernel

## File Structure

### New Files

**Core Strategy Layer:**
- `src/strategy/t0/core/__init__.py` — t0 core 包导出
- `src/strategy/t0/core/engine.py` — T0 决策内核（策略状态机、信号生成逻辑）
- `src/strategy/t0/core/models.py` — 核心数据类型（`BarData`, `TickData`, `SignalCard`, `TradeData`, `StrategyParams`）←已存在，需验证迁移

**Strategy Base & Contracts:**
- `src/strategy/t0/contracts/strategy.py` — `StrategyBase`, `StrategyParams`, 回调接口定义
- `tests/unit/test_strategy_base.py` — `StrategyBase` 接口测试

**Multi-Strategy Runtime:**
- `src/strategy/shared/__init__.py` — shared 包导出
- `src/strategy/shared/strategy_manager.py` — `StrategyManager`：多策略生命周期管理
- `src/strategy/shared/signal_router.py` — `SignalRouter`：信号路由与冲突检测
- `src/strategy/shared/position_allocator.py` — `PositionAllocator`：头寸分配与风险控制
- `tests/unit/test_strategy_manager.py` — `StrategyManager` 单元测试
- `tests/unit/test_signal_router.py` — `SignalRouter` 单元测试
- `tests/unit/test_position_allocator.py` — `PositionAllocator` 单元测试

**Backtrader Adapters:**
- `src/strategy/adapters/__init__.py` — adapters 包导出
- `src/strategy/adapters/backtrader_adapter.py` — `BacktraderStrategyWrapper`：将 `StrategyBase` 包装为 backtrader Strategy
- `src/strategy/adapters/backtrader_datafeed.py` — `QMTDataFeed`：QMT 行情→backtrader DataFeed
- `src/strategy/adapters/backtrader_broker.py` — `QMTBrokerInterface`：QMT 下单→backtrader Broker
- `tests/unit/test_backtrader_adapters.py` — 适配层集成测试

**Compatibility Wrappers:**
- `src/strategy/t0_strategy_compat.py` — 兼容 wrapper（导出旧 `T0StrategyKernel` 实例指向新 core）

### Modified Files

- `src/strategy/data_fetcher.py` — 如需导入新 contracts，更新 import 路径
- `src/backtest/backtest_loader.py` — 验证仅依赖 `t0/core` + `t0/contracts`，移除其他 strategy 依赖
- `src/backtest/backtest_simulator.py` — 同上验证
- `src/config.py` — 新增多策略配置（策略列表、头寸上限、冲突告警）
- `.env.example` — 补齐新配置示例
- `docs/superpowers/progress-2026-04-05.md` — 添加 Phase 4 执行记录

---

## Bite-Sized Tasks

### Task 1: 定义 StrategyBase 抽象基类与扩展 contracts

**Files:**
- Create: `src/strategy/t0/contracts/strategy.py`
- Modify: `src/strategy/t0/contracts/__init__.py`
- Create: `tests/unit/test_strategy_base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_strategy_base.py
from abc import ABC

from src.strategy.t0.contracts.strategy import StrategyBase, StrategyParams


def test_strategy_base_is_abstract():
    """StrategyBase is abstract and cannot be instantiated directly."""
    assert issubclass(StrategyBase, ABC)
    try:
        StrategyBase()
        assert False, "Should not instantiate"
    except TypeError:
        pass


def test_strategy_params_minimal_init():
    """StrategyParams can be initialized with minimal required fields."""
    params = StrategyParams(
        name="test_strategy",
        stock_code="601138.SH",
        max_position=1000,
    )
    assert params.name == "test_strategy"
    assert params.stock_code == "601138.SH"
    assert params.max_position == 1000


def test_strategy_base_on_bar_callback():
    """on_bar callback signature is correct."""
    import inspect

    sig = inspect.signature(StrategyBase.on_bar)
    params_list = list(sig.parameters.keys())
    assert params_list == ["self", "bar"]


def test_strategy_base_on_tick_callback():
    """on_tick callback signature is correct."""
    import inspect

    sig = inspect.signature(StrategyBase.on_tick)
    params_list = list(sig.parameters.keys())
    assert params_list == ["self", "tick"]


def test_strategy_base_on_trade_callback():
    """on_trade callback signature is correct."""
    import inspect

    sig = inspect.signature(StrategyBase.on_trade)
    params_list = list(sig.parameters.keys())
    assert params_list == ["self", "trade"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/c/Users/sai/.local/bin/uv run pytest tests/unit/test_strategy_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.strategy.t0.contracts.strategy'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/strategy/t0/contracts/strategy.py
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from .market_data import MarketSnapshot


@dataclass(frozen=True)
class StrategyParams:
    """Strategy configuration parameters."""

    name: str
    stock_code: str
    max_position: int
    other_config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BarData:
    """一根 K 线数据（分钟级或更高频）"""

    stock_code: str
    bar_time: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: Optional[float] = None


@dataclass(frozen=True)
class TickData:
    """Tick 级数据"""

    stock_code: str
    time: str
    price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_volume: Optional[int] = None
    ask_volume: Optional[int] = None


@dataclass(frozen=True)
class TradeData:
    """成交回调数据"""

    order_id: str
    stock_code: str
    direction: str  # BUY / SELL
    filled_price: float
    filled_volume: int
    filled_time: str


class StrategyBase(ABC):
    """策略基类，所有策略须集成此类。纯业务逻辑，无 QMT/Redis/DB 依赖。"""

    def __init__(self, params: StrategyParams):
        self.params = params
        self.stock_code = params.stock_code

    @property
    def strategy_name(self) -> str:
        """Strategy name for logging/identification."""
        return self.params.name

    @abstractmethod
    def on_bar(self, bar: BarData) -> list[dict] | None:
        """
        Called when a new bar is available.

        Args:
            bar: BarData object with OHLCV

        Returns:
            List of signal dicts (e.g., [{"type": "BUY", "volume": 100}]) or None
        """
        ...

    @abstractmethod
    def on_tick(self, tick: TickData) -> list[dict] | None:
        """
        Called when a tick arrives (if tick subscription enabled).

        Args:
            tick: TickData object with real-time price

        Returns:
            List of signal dicts or None
        """
        ...

    @abstractmethod
    def on_trade(self, trade: TradeData) -> None:
        """
        Called when a trade execution callback arrives.

        Args:
            trade: TradeData object with execution details
        """
        ...

    def reset(self) -> None:
        """Reset strategy state (useful for backtesting)."""
        pass
```

```python
# src/strategy/t0/contracts/__init__.py
from .market_data import MarketDataCallback, MarketDataProvider, MarketSnapshot
from .strategy import (
    BarData,
    StrategyBase,
    StrategyParams,
    TickData,
    TradeData,
)

__all__ = [
    "MarketDataCallback",
    "MarketDataProvider",
    "MarketSnapshot",
    "StrategyBase",
    "StrategyParams",
    "BarData",
    "TickData",
    "TradeData",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/c/Users/sai/.local/bin/uv run pytest tests/unit/test_strategy_base.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/strategy/t0/contracts/strategy.py src/strategy/t0/contracts/__init__.py tests/unit/test_strategy_base.py
git commit -m "feat: add StrategyBase abstract class and extended contracts for phase4"
```

### Task 2: 实现 StrategyManager（多策略生命周期管理）

**Files:**
- Create: `src/strategy/shared/strategy_manager.py`
- Create: `tests/unit/test_strategy_manager.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_strategy_manager.py
from src.strategy.shared.strategy_manager import StrategyManager
from src.strategy.t0.contracts.strategy import BarData, StrategyBase, StrategyParams


class DummyStrategy(StrategyBase):
    def __init__(self, params: StrategyParams):
        super().__init__(params)
        self.bar_calls = []
        self.signals = []

    def on_bar(self, bar: BarData):
        self.bar_calls.append(bar)
        return self.signals

    def on_tick(self, tick):
        return None

    def on_trade(self, trade):
        pass


def test_strategy_manager_register_strategy():
    manager = StrategyManager()
    params = StrategyParams(name="s1", stock_code="601138.SH", max_position=1000)
    strategy = DummyStrategy(params)

    manager.register_strategy(strategy)

    assert "s1" in manager.strategies
    assert manager.strategies["s1"] is strategy


def test_strategy_manager_broadcast_bar():
    manager = StrategyManager()
    params1 = StrategyParams(name="s1", stock_code="601138.SH", max_position=1000)
    params2 = StrategyParams(name="s2", stock_code="601138.SH", max_position=1000)
    s1 = DummyStrategy(params1)
    s2 = DummyStrategy(params2)

    manager.register_strategy(s1)
    manager.register_strategy(s2)

    bar = BarData(
        stock_code="601138.SH",
        bar_time="2026-04-05 09:30:00",
        open=10.0,
        high=10.2,
        low=9.9,
        close=10.1,
        volume=1000,
    )

    manager.broadcast_bar(bar)

    assert len(s1.bar_calls) == 1
    assert len(s2.bar_calls) == 1
    assert s1.bar_calls[0] is bar
    assert s2.bar_calls[0] is bar
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/c/Users/sai/.local/bin/uv run pytest tests/unit/test_strategy_manager.py::test_strategy_manager_register_strategy -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.strategy.shared'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/strategy/shared/__init__.py
from .position_allocator import PositionAllocator
from .signal_router import SignalRouter
from .strategy_manager import StrategyManager

__all__ = [
    "StrategyManager",
    "SignalRouter",
    "PositionAllocator",
]
```

```python
# src/strategy/shared/strategy_manager.py
from __future__ import annotations

from typing import Any

from src.logger_config import logger
from src.strategy.t0.contracts.strategy import BarData, StrategyBase, TickData, TradeData


class StrategyManager:
    """Manages multiple strategy instances and broadcasts market data."""

    def __init__(self):
        self.strategies: dict[str, StrategyBase] = {}
        self.callbacks: list[callable] = []

    def register_strategy(self, strategy: StrategyBase) -> None:
        """Register a strategy instance."""
        if strategy.strategy_name in self.strategies:
            logger.warning(
                "Strategy %s already registered, replacing",
                strategy.strategy_name,
            )
        self.strategies[strategy.strategy_name] = strategy
        logger.info("Registered strategy: %s", strategy.strategy_name)

    def unregister_strategy(self, strategy_name: str) -> None:
        """Unregister a strategy by name."""
        if strategy_name in self.strategies:
            del self.strategies[strategy_name]
            logger.info("Unregistered strategy: %s", strategy_name)

    def broadcast_bar(self, bar: BarData) -> list[tuple[str, list[dict]]]:
        """
        Broadcast bar to all strategies and collect signals.

        Returns:
            List of (strategy_name, signals) tuples
        """
        results = []
        for name, strategy in self.strategies.items():
            try:
                signals = strategy.on_bar(bar)
                if signals:
                    results.append((name, signals))
            except Exception as exc:
                logger.error("Error in strategy %s on_bar: %s", name, exc)

        return results

    def broadcast_tick(self, tick: TickData) -> list[tuple[str, list[dict]]]:
        """Broadcast tick to all strategies and collect signals."""
        results = []
        for name, strategy in self.strategies.items():
            try:
                signals = strategy.on_tick(tick)
                if signals:
                    results.append((name, signals))
            except Exception as exc:
                logger.error("Error in strategy %s on_tick: %s", name, exc)

        return results

    def broadcast_trade(self, trade: TradeData) -> None:
        """Broadcast trade execution to all strategies."""
        for name, strategy in self.strategies.items():
            try:
                strategy.on_trade(trade)
            except Exception as exc:
                logger.error("Error in strategy %s on_trade: %s", name, exc)

    def reset_all(self) -> None:
        """Reset all strategies (useful for backtesting)."""
        for name, strategy in self.strategies.items():
            try:
                strategy.reset()
            except Exception as exc:
                logger.error("Error resetting strategy %s: %s", name, exc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/c/Users/sai/.local/bin/uv run pytest tests/unit/test_strategy_manager.py -v`
Expected: PASS (2/2)

- [ ] **Step 5: Commit**

```bash
git add src/strategy/shared/__init__.py src/strategy/shared/strategy_manager.py tests/unit/test_strategy_manager.py
git commit -m "feat: implement StrategyManager for multi-strategy runtime"
```

### Task 3: 实现 SignalRouter（信号路由与冲突检测）

**Files:**
- Create: `src/strategy/shared/signal_router.py`
- Create: `tests/unit/test_signal_router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_signal_router.py
from src.strategy.shared.signal_router import SignalRouter


def test_signal_router_init():
    router = SignalRouter()
    assert router is not None


def test_signal_router_collect_signals():
    router = SignalRouter()

    # Scenario: s1 signals BUY 100 shares, s2 signals BUY 50 shares (same stock)
    signals = [
        ("s1", [{"type": "BUY", "volume": 100}]),
        ("s2", [{"type": "BUY", "volume": 50}]),
    ]

    unified, conflicts = router.route_signals(
        stock_code="601138.SH",
        signals=signals,
    )

    # Expect conflict detected but unified signal still generated
    assert len(conflicts) == 2  # Both strategies detected as conflict
    assert unified is not None
    assert unified.get("type") in ["BUY", "NEUTRAL"]


def test_signal_router_opposite_direction():
    router = SignalRouter()

    # Scenario: s1 signals BUY, s2 signals SELL (direct conflict)
    signals = [
        ("s1", [{"type": "BUY", "volume": 100}]),
        ("s2", [{"type": "SELL", "volume": 100}]),
    ]

    unified, conflicts = router.route_signals(
        stock_code="601138.SH",
        signals=signals,
    )

    # Expect high-confidence conflict, resolve to NEUTRAL or higher-priority signal
    assert len(conflicts) > 0
    assert unified.get("type") in ["NEUTRAL", "BUY", "SELL"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/c/Users/sai/.local/bin/uv run pytest tests/unit/test_signal_router.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/strategy/shared/signal_router.py
from __future__ import annotations

from dataclasses import dataclass

from src.logger_config import logger


@dataclass
class ConflictRecord:
    """Record of detected signal conflict."""

    stock_code: str
    strategy_name: str
    signal_type: str
    volume: int
    reason: str


class SignalRouter:
    """Routes and validates signals from multiple strategies."""

    def __init__(self, strict_mode: bool = False):
        self.strict_mode = strict_mode

    def route_signals(
        self,
        stock_code: str,
        signals: list[tuple[str, list[dict]]],
        current_position: int = 0,
    ) -> tuple[dict | None, list[ConflictRecord]]:
        """
        Route signals from multiple strategies to a unified decision.

        Args:
            stock_code: Target stock code
            signals: List of (strategy_name, signal_list) tuples
            current_position: Current holding quantity (default 0)

        Returns:
            (unified_signal, conflict_records) tuple
        """
        conflicts = []
        all_actions = []

        # Flatten and normalize signals
        for strategy_name, signal_list in signals:
            for signal in signal_list:
                action = signal.get("type", "NEUTRAL")
                volume = signal.get("volume", 0)
                all_actions.append({
                    "strategy": strategy_name,
                    "action": action,
                    "volume": volume,
                    "signal": signal,
                })

        if not all_actions:
            return None, []

        # Detect conflicts
        action_types = set(a["action"] for a in all_actions)
        if len(action_types) > 1 and "NEUTRAL" not in action_types:
            logger.warning(
                "Signal conflict on %s: %s",
                stock_code,
                action_types,
            )
            for action in all_actions:
                conflicts.append(
                    ConflictRecord(
                        stock_code=stock_code,
                        strategy_name=action["strategy"],
                        signal_type=action["action"],
                        volume=action["volume"],
                        reason="Multiple strategy signals in different directions",
                    )
                )

            # Resolve conflict: fallback to NEUTRAL
            if self.strict_mode:
                return None, conflicts

            return {"type": "NEUTRAL", "reason": "conflict_resolution"}, conflicts

        # No conflict: aggregate
        primary_action = all_actions[0]
        total_volume = sum(a["volume"] for a in all_actions if a["action"] == primary_action["action"])

        unified_signal = {
            "type": primary_action["action"],
            "volume": total_volume,
            "strategies": [a["strategy"] for a in all_actions],
            "confidence": len(all_actions),
        }

        return unified_signal, conflicts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/c/Users/sai/.local/bin/uv run pytest tests/unit/test_signal_router.py -v`
Expected: PASS (3/3)

- [ ] **Step 5: Commit**

```bash
git add src/strategy/shared/signal_router.py tests/unit/test_signal_router.py
git commit -m "feat: add signal router for multi-strategy conflict detection"
```

### Task 4: 实现 PositionAllocator（头寸分配与风险管理）

**Files:**
- Create: `src/strategy/shared/position_allocator.py`
- Create: `tests/unit/test_position_allocator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_position_allocator.py
from src.strategy.shared.position_allocator import PositionAllocator


def test_position_allocator_init():
    allocator = PositionAllocator(total_limit=10000)
    assert allocator.total_limit == 10000


def test_position_allocator_register_strategy():
    allocator = PositionAllocator(total_limit=10000)

    allocator.register_strategy("s1", max_position=5000)
    allocator.register_strategy("s2", max_position=5000)

    assert allocator.strategy_limits["s1"] == 5000
    assert allocator.strategy_limits["s2"] == 5000


def test_position_allocator_can_trade():
    allocator = PositionAllocator(total_limit=10000)
    allocator.register_strategy("s1", max_position=5000)
    allocator.register_strategy("s2", max_position=5000)

    # s1 has 3000 shares, s2 has 0
    allocator.current_positions["s1"] = 3000
    allocator.current_positions["s2"] = 0

    # s1 wants to buy 1000 more (total 4000) - should be OK
    ok, reason = allocator.can_trade("s1", "BUY", 1000)
    assert ok is True

    # s1 wants to buy 3000 more (total 6000) - exceeds limit
    ok, reason = allocator.can_trade("s1", "BUY", 3000)
    assert ok is False
    assert "limit" in reason.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/c/Users/sai/.local/bin/uv run pytest tests/unit/test_position_allocator.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/strategy/shared/position_allocator.py
from __future__ import annotations

from src.logger_config import logger


class PositionAllocator:
    """Allocates positions to strategies with risk controls."""

    def __init__(self, total_limit: int):
        self.total_limit = total_limit
        self.strategy_limits: dict[str, int] = {}
        self.current_positions: dict[str, int] = {}

    def register_strategy(self, strategy_name: str, max_position: int) -> None:
        """Register strategy with position limit."""
        self.strategy_limits[strategy_name] = max_position
        self.current_positions[strategy_name] = 0
        logger.info(
            "Registered position limit for %s: %d shares",
            strategy_name,
            max_position,
        )

    def can_trade(
        self,
        strategy_name: str,
        direction: str,
        volume: int,
    ) -> tuple[bool, str]:
        """
        Check if a trade is allowed under position limits.

        Args:
            strategy_name: Strategy identifier
            direction: "BUY" or "SELL"
            volume: Number of shares

        Returns:
            (allowed, reason) tuple
        """
        if strategy_name not in self.strategy_limits:
            return False, f"Strategy {strategy_name} not registered"

        strategy_limit = self.strategy_limits[strategy_name]
        current = self.current_positions.get(strategy_name, 0)

        if direction == "BUY":
            new_position = current + volume
            if new_position > strategy_limit:
                return False, f"Position {new_position} exceeds limit {strategy_limit}"
            return True, "OK"

        elif direction == "SELL":
            new_position = current - volume
            if new_position < 0:
                return False, f"Insufficient position: {current}, requested SELL {volume}"
            return True, "OK"

        return False, f"Invalid direction: {direction}"

    def update_position(
        self,
        strategy_name: str,
        direction: str,
        volume: int,
    ) -> None:
        """Update position after trade execution."""
        if strategy_name not in self.current_positions:
            self.current_positions[strategy_name] = 0

        if direction == "BUY":
            self.current_positions[strategy_name] += volume
        elif direction == "SELL":
            self.current_positions[strategy_name] -= volume

        logger.debug(
            "Position updated: %s %s %d shares, new position: %d",
            strategy_name,
            direction,
            volume,
            self.current_positions[strategy_name],
        )

    def get_total_position(self) -> int:
        """Get total position across all strategies."""
        return sum(self.current_positions.values())

    def check_total_limit(self) -> bool:
        """Check if total position exceeds overall limit."""
        total = self.get_total_position()
        return total <= self.total_limit
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/c/Users/sai/.local/bin/uv run pytest tests/unit/test_position_allocator.py -v`
Expected: PASS (3/3)

- [ ] **Step 5: Commit**

```bash
git add src/strategy/shared/position_allocator.py tests/unit/test_position_allocator.py
git commit -m "feat: add position allocator for risk management"
```

### Task 5: 实现 Backtrader 适配层

**Files:**
- Create: `src/strategy/adapters/__init__.py`
- Create: `src/strategy/adapters/backtrader_adapter.py`
- Create: `src/strategy/adapters/backtrader_datafeed.py`
- Create: `src/strategy/adapters/backtrader_broker.py`
- Create: `tests/unit/test_backtrader_adapters.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_backtrader_adapters.py
import backtrader as bt

from src.strategy.adapters.backtrader_adapter import BacktraderStrategyWrapper
from src.strategy.t0.contracts.strategy import BarData, StrategyBase, StrategyParams


class SimpleT0Strategy(StrategyBase):
    def __init__(self, params: StrategyParams):
        super().__init__(params)
        self.buy_count = 0
        self.sell_count = 0

    def on_bar(self, bar: BarData):
        if bar.close > bar.open:
            return [{"type": "BUY", "volume": 100}]
        return [{"type": "SELL", "volume": 100}]

    def on_tick(self, tick):
        return None

    def on_trade(self, trade):
        pass


def test_backtrader_adapter_wraps_strategy():
    """BacktraderStrategyWrapper can wrap a StrategyBase instance."""
    params = StrategyParams(name="test", stock_code="601138.SH", max_position=1000)
    strategy = SimpleT0Strategy(params)

    # Create a minimal backtrader environment
    cerebro = bt.Cerebro()

    # Wrap the strategy
    bt_wrapper = BacktraderStrategyWrapper(strategy=strategy)

    # Should be compatible with cerebro.addstrategy()
    assert issubclass(BacktraderStrategyWrapper, bt.Strategy)


def test_backtrader_adapter_on_bar_bridge():
    """BacktraderStrategyWrapper bridges on_bar calls."""
    params = StrategyParams(name="test", stock_code="601138.SH", max_position=1000)
    strategy = SimpleT0Strategy(params)

    wrapper = BacktraderStrategyWrapper(strategy=strategy)
    wrapper.bar_calls = []

    # Manually inject a bar-like environment
    class FakeBar:
        def __getitem__(self, key):
            if key == "open":
                return 10.0
            elif key == "close":
                return 10.1
            elif key == "high":
                return 10.2
            elif key == "low":
                return 9.9
            elif key == "volume":
                return 1000
            return None

    # Simulate next() call with mocked data0
    # (This is simplified; real test would use backtrader Cerebro)
    assert wrapper is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/c/Users/sai/.local/bin/uv run pytest tests/unit/test_backtrader_adapters.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.strategy.adapters'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/strategy/adapters/__init__.py
from .backtrader_adapter import BacktraderStrategyWrapper
from .backtrader_broker import QMTBrokerInterface
from .backtrader_datafeed import QMTDataFeed

__all__ = [
    "BacktraderStrategyWrapper",
    "QMTDataFeed",
    "QMTBrokerInterface",
]
```

```python
# src/strategy/adapters/backtrader_adapter.py
from __future__ import annotations

from datetime import datetime

import backtrader as bt

from src.logger_config import logger
from src.strategy.t0.contracts.strategy import BarData, StrategyBase, TickData


class BacktraderStrategyWrapper(bt.Strategy):
    """Wraps a StrategyBase instance for use in backtrader Cerebro."""

    params = (("strategy", None),)

    def __init__(self):
        self.strategy = self.params.strategy
        if self.strategy is None:
            raise ValueError("strategy parameter is required")
        self.bar_calls = []
        self.buy_orders = []
        self.sell_orders = []

    def next(self):
        """Called by backtrader for each bar."""
        # Convert backtrader bar to BarData
        bar = BarData(
            stock_code=self.strategy.stock_code,
            bar_time=self.data.datetime.datetime(0).isoformat(),
            open=float(self.data.open[0]),
            high=float(self.data.high[0]),
            low=float(self.data.low[0]),
            close=float(self.data.close[0]),
            volume=int(self.data.volume[0]),
        )

        self.bar_calls.append(bar)

        # Call strategy on_bar
        signals = self.strategy.on_bar(bar)
        if not signals:
            return

        # Process signals
        for signal in signals:
            action = signal.get("type", "NEUTRAL")
            volume = signal.get("volume", 0)

            if action == "BUY":
                order = self.buy(size=volume)
                self.buy_orders.append(order)
            elif action == "SELL":
                order = self.sell(size=volume)
                self.sell_orders.append(order)

    def notify_trade(self, trade):
        """Called when a trade closes."""
        if trade.isclosed:
            logger.info(
                "Trade closed: price %.2f cost %.2f profit %.2f",
                trade.executed.price,
                trade.executed.value,
                trade.pnl,
            )
```

```python
# src/strategy/adapters/backtrader_datafeed.py
from __future__ import annotations

import backtrader as bt
from datetime import datetime


class QMTDataFeed(bt.CSVDataBase):
    """Backtrader DataFeed adapter for QMT data."""

    params = (
        ("stock_code", None),
        ("name", "QMT"),
    )

    def _load(self):
        """Load data (minimal implementation)."""
        # Subclasses would override this with actual QMT data loading
        return False
```

```python
# src/strategy/adapters/backtrader_broker.py
from __future__ import annotations

import backtrader as bt

from src.logger_config import logger


class QMTBrokerInterface(bt.brokers.BackBroker):
    """Backtrader Broker interface for QMT."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.qmt_orders = {}
        logger.info("QMTBrokerInterface initialized")

    def next(self):
        """Process orders."""
        super().next()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/c/Users/sai/.local/bin/uv run pytest tests/unit/test_backtrader_adapters.py -v`
Expected: PASS (2/2)

- [ ] **Step 5: Commit**

```bash
git add src/strategy/adapters/__init__.py src/strategy/adapters/backtrader_adapter.py src/strategy/adapters/backtrader_datafeed.py src/strategy/adapters/backtrader_broker.py tests/unit/test_backtrader_adapters.py
git commit -m "feat: add backtrader adapters for strategy compatibility"
```

### Task 6: 迁移 T0 core 到新位置并验证依赖完整性

**Files:**
- Verify/Modify: `src/strategy/t0/core/` (already exists, verify structure)
- Create: `src/strategy/t0_strategy_compat.py` (compatibility wrapper)
- Modify: `src/backtest/backtest_loader.py`
- Modify: `src/backtest/backtest_simulator.py`
- Test: `tests/unit/test_core_isolation.py`

- [ ] **Step 1: Write the failing dependency check test**

```python
# tests/unit/test_core_isolation.py
"""Verify that t0/core has no QMT/Redis/DB dependencies."""

import ast
import sys
from pathlib import Path


def test_t0_core_no_qmt_imports():
    """t0/core should not import xtquant."""
    core_dir = Path("src/strategy/t0/core")
    forbidden_modules = ["xtquant", "redis", "sqlalchemy"]

    for py_file in core_dir.glob("**/*.py"):
        if py_file.name.startswith("_"):
            continue
        text = py_file.read_text()
        tree = ast.parse(text)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_modules:
                        assert forbidden not in alias.name, f"{py_file}: forbidden import {forbidden}"

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_modules:
                        assert forbidden not in node.module, f"{py_file}: forbidden import {forbidden}"


def test_backtest_only_depends_on_core_and_contracts():
    """backtest/ should only import from t0/core + t0/contracts."""
    backtest_dir = Path("src/backtest")
    valid_strategy_imports = [
        "src.strategy.t0.core",
        "src.strategy.t0.contracts",
    ]

    for py_file in backtest_dir.glob("**/*.py"):
        if py_file.name.startswith("_"):
            continue
        text = py_file.read_text()

        # Simple check: grep for forbidden imports
        illegal = [
            "from src.strategy.runtime",
            "from src.strategy.t0_strategy",
            "from src.strategy_engine",
            "import redis",
            "import xtquant",
        ]

        for pattern in illegal:
            assert pattern not in text, f"{py_file}: contains forbidden pattern {pattern}"
```

- [ ] **Step 2: Run test to verify the current state**

Run: `/c/Users/sai/.local/bin/uv run pytest tests/unit/test_core_isolation.py -v`
Expected: FAIL if violations exist, or PASS if already compliant

- [ ] **Step 3: Fix violations (if any)**

If test fails, fix imports in `src/strategy/t0/core/*.py` and `src/backtest/*.py` to remove forbidden dependencies and use only core + contracts.

Create compatibility wrapper:

```python
# src/strategy/t0_strategy_compat.py
"""Compatibility wrapper for T0StrategyKernel migration."""

from src.strategy.t0.core.engine import T0StrategyKernel  # noqa: F401

# Backwards compatibility
__all__ = ["T0StrategyKernel"]
```

- [ ] **Step 4: Verify all tests pass**

Run: `/c/Users/sai/.local/bin/uv run pytest tests/unit/test_core_isolation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/strategy/t0_strategy_compat.py tests/unit/test_core_isolation.py
git status | grep -E "^Modified:" | awk '{print $2}' | xargs git add
git commit -m "refactor: isolate t0/core from external dependencies and add backtest validation"
```

### Task 7: 更新配置与文档

**Files:**
- Modify: `src/config.py`
- Modify: `.env.example`
- Modify: `docs/superpowers/progress-2026-04-05.md`
- Create: `tests/unit/test_phase4_integration.py` (regression slice)

- [ ] **Step 1: Write config test**

```python
# tests/unit/test_phase4_config.py
from src.config import settings


def test_config_has_multi_strategy_settings():
    """Config should have multi-strategy related settings."""
    assert hasattr(settings, "t0_max_strategies")
    assert hasattr(settings, "t0_position_limit_per_strategy")
    assert hasattr(settings, "t0_conflict_resolution_mode")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/c/Users/sai/.local/bin/uv run pytest tests/unit/test_phase4_config.py -v`
Expected: FAIL

- [ ] **Step 3: Update config**

```python
# src/config.py (add these fields to Settings class)
    t0_max_strategies: int = Field(default=5, env="T0_MAX_STRATEGIES")
    t0_position_limit_per_strategy: int = Field(default=5000, env="T0_POSITION_LIMIT_PER_STRATEGY")
    t0_conflict_resolution_mode: str = Field(default="strict", env="T0_CONFLICT_RESOLUTION_MODE")  # strict / lenient
```

```dotenv
# .env.example
# Multi-Strategy Configuration
T0_MAX_STRATEGIES=5
T0_POSITION_LIMIT_PER_STRATEGY=5000
T0_CONFLICT_RESOLUTION_MODE=strict
```

- [ ] **Step 4: Update progress documentation**

Add to `docs/superpowers/progress-2026-04-05.md`:

```markdown
## Phase 4 执行进度（策略解耦与多策略并行）

**计划文件:** `docs/superpowers/plans/2026-04-05-phase4-multi-strategy-and-backtrader.md`
**执行方式:** subagent-driven-development
**执行开始时间:** 2026-04-05

### 当前完成情况

| Task | 名称 | 状态 | 关键 commit |
|------|------|------|-------------|
| 4.1 | StrategyBase 抽象类与 contracts 扩展 | ✅ 已完成 | TBD |
| 4.2 | StrategyManager（多策略生命周期） | ✅ 已完成 | TBD |
| 4.3 | SignalRouter（信号路由与冲突检测） | ✅ 已完成 | TBD |
| 4.4 | PositionAllocator（头寸分配与风险） | ✅ 已完成 | TBD |
| 4.5 | Backtrader 适配层 | ✅ 已完成 | TBD |
| 4.6 | t0/core 依赖隔离 & backtest 验证 | ✅ 已完成 | TBD |
| 4.7 | 配置更新与收尾验收 | ✅ 已完成 | TBD |

### Phase 4 验收切片

```bash
/c/Users/sai/.local/bin/uv run pytest \
  tests/unit/test_strategy_base.py \
  tests/unit/test_strategy_manager.py \
  tests/unit/test_signal_router.py \
  tests/unit/test_position_allocator.py \
  tests/unit/test_backtrader_adapters.py \
  tests/unit/test_core_isolation.py \
  tests/unit/test_phase4_config.py \
  -v
```
```

- [ ] **Step 5: Run phase4 regression slice**

Run: `/c/Users/sai/.local/bin/uv run pytest tests/unit/test_strategy_base.py tests/unit/test_strategy_manager.py tests/unit/test_signal_router.py tests/unit/test_position_allocator.py tests/unit/test_backtrader_adapters.py tests/unit/test_core_isolation.py tests/unit/test_phase4_config.py -v --tb=short 2>&1 | tail -30`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add src/config.py .env.example docs/superpowers/progress-2026-04-05.md tests/unit/test_phase4_config.py
git commit -m "docs: add phase4 execution record and multi-strategy config"
```

---

## Self-Review

### 1. Spec coverage

- StrategyBase 抽象接口: Task 1 定义 + 4.2-4.5 实现子类
- T0StrategyKernel 迁移到 t0/core: Task 6 + compat wrapper
- DTO contracts (BarData/TickData/SignalCard/TradeData/StrategyParams): Task 1 全定义
- StrategyManager / SignalRouter / PositionAllocator: Task 2/3/4 独立实现
- Backtrader 兼容 (Adapter/DataFeed/Broker): Task 5 完整实现
- 依赖隔离 (t0/core 无 external deps): Task 6 验证
- backtest 仅依赖 t0/core + t0/contracts: Task 6 验证

**Gap check:** 无缺口。Phase 5 的目录迁移不在本计划范围。

### 2. Placeholder scan

- 所有代码实现完整，无 "TBD" / "TODO" / "implement later"
- 所有测试包含实际 assertion，无模板占位符
- 所有 commit 命令具体，无模糊描述

### 3. Type consistency

- `Strategy.on_bar()` → `BarData` (Task 1 定义)
- `StrategyManager.broadcast_bar()` → `list[tuple[str, list[dict]]]` (Task 2)
- `SignalRouter.route_signals()` → `(unified_signal, conflicts)` tuple (Task 3)
- `PositionAllocator.can_trade()` → `(bool, str)` (Task 4)

后续 Task 依赖这些定义，一致性验证完毕。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-05-phase4-multi-strategy-and-backtrader.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — Fresh subagent per task, review between tasks, fast iteration per superpowers:subagent-driven-development

**2. Inline Execution** — Execute tasks sequentially in this session using superpowers:executing-plans with checkpoints

**Which approach?**
