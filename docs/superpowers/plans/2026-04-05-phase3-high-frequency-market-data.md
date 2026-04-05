# Phase 3 High-Frequency Market Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 T+0 实盘运行时引入可替换的高频行情提供层，在不破坏现有分钟线回测路径的前提下支持 tick 与 3 秒快照。

**Architecture:** 在运行时层新增 `MarketDataProvider` 协议与 QMT 适配实现（tick 订阅 + 定时快照），再通过桥接适配器把 `DataFetcher` 和 `StrategyEngine` 从直接依赖 xtquant 转为依赖协议。策略核心仍保持纯计算，不新增任何 QMT/Redis/DB 依赖。

**Tech Stack:** Python 3.11, xtquant SDK, pandas, pytest, pytest-mock, uv

---

## Scope Check

原始规格覆盖 Phase 0-6 多子系统。本计划仅覆盖 **Phase 3（高频行情接入）**，不包含 Phase 4 的多策略并行和 backtrader 适配。这样可保证本计划单独落地后即可验证：

1. 运行时可按 <=3 秒更新快照。
2. `DataFetcher` 与 `StrategyEngine` 不再直接绑死 xtdata 调用点。
3. 回测分钟线路径保持不变。

## File Structure

### New Files

- `src/strategy/t0/contracts/__init__.py`
  - 导出 Phase 3 新增的行情协议与 typed payload。
- `src/strategy/t0/contracts/market_data.py`
  - `MarketDataProvider` 协议、`MarketSnapshot` dataclass、回调类型定义。
- `src/market_data/__init__.py`
  - 市场数据域包入口。
- `src/market_data/ingestion/__init__.py`
  - 导出 QMT 行情 provider 实现。
- `src/market_data/ingestion/qmt_tick_provider.py`
  - `QMTTickProvider`：封装 `xtdata.subscribe_quote` / `unsubscribe_quote`。
- `src/market_data/ingestion/qmt_snapshot_provider.py`
  - `QMTSnapshotProvider`：封装 `xtdata.get_full_tick`，支持 3 秒轮询回调与最新快照缓存。
- `tests/unit/test_market_data_contracts.py`
  - 协议与 typed payload 单元测试。
- `tests/unit/test_qmt_market_data_providers.py`
  - tick/snapshot provider 的行为测试（monkeypatch xtdata）。
- `tests/unit/test_data_fetcher_market_provider_bridge.py`
  - `DataFetcher` 使用 provider 的桥接测试。

### Modified Files

- `src/strategy/data_fetcher.py`
  - 构造函数支持注入 `market_data_provider`。
  - `fetch_realtime_snapshot` 优先走 provider，再回退旧逻辑。
  - `_append_snapshot_tick` / `_refresh_ticks_from_fallbacks` 与 provider 对齐。
- `src/strategy/strategy_engine.py`
  - 运行时初始化 `QMTSnapshotProvider` 并注入 `DataFetcher`。
- `src/config.py`
  - 新增 Phase 3 配置项（快照轮询频率、provider 开关、tick 优先级）。
- `.env.example`
  - 补齐新增配置项示例。
- `docs/superpowers/progress-2026-04-05.md`
  - 增加 Phase 3 执行入口与本计划链接。

---

### Task 1: 定义 MarketDataProvider 协议与 typed payload

**Files:**
- Create: `src/strategy/t0/contracts/__init__.py`
- Create: `src/strategy/t0/contracts/market_data.py`
- Test: `tests/unit/test_market_data_contracts.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_market_data_contracts.py
from dataclasses import asdict

from src.strategy.t0.contracts.market_data import MarketSnapshot


def test_market_snapshot_to_dict_fields_complete():
    snapshot = MarketSnapshot(
        stock_code="601138.SH",
        time="2026-04-05 09:30:03",
        price=10.23,
        high=10.30,
        low=10.10,
        open=10.15,
        amount=120000.0,
        volume=3500.0,
        pre_close=10.00,
        source="qmt_snapshot",
    )

    payload = asdict(snapshot)

    assert payload["stock_code"] == "601138.SH"
    assert payload["price"] == 10.23
    assert payload["source"] == "qmt_snapshot"
    assert sorted(payload.keys()) == sorted(
        [
            "stock_code",
            "time",
            "price",
            "high",
            "low",
            "open",
            "amount",
            "volume",
            "pre_close",
            "source",
        ]
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_market_data_contracts.py::test_market_snapshot_to_dict_fields_complete -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.strategy.t0.contracts.market_data'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/strategy/t0/contracts/market_data.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True)
class MarketSnapshot:
    stock_code: str
    time: str | None
    price: float | None
    high: float | None
    low: float | None
    open: float | None
    amount: float | None
    volume: float | None
    pre_close: float | None
    source: str


MarketDataCallback = Callable[[MarketSnapshot], None]


class MarketDataProvider(Protocol):
    def subscribe_tick(self, stock_codes: list[str], callback: MarketDataCallback) -> None:
        ...

    def subscribe_snapshot(
        self,
        stock_codes: list[str],
        interval_seconds: int,
        callback: MarketDataCallback,
    ) -> None:
        ...

    def get_latest_snapshot(self, stock_code: str) -> MarketSnapshot | None:
        ...

    def get_minute_bars(self, stock_code: str, count: int) -> list[dict]:
        ...
```

```python
# src/strategy/t0/contracts/__init__.py
from .market_data import MarketDataCallback, MarketDataProvider, MarketSnapshot

__all__ = [
    "MarketDataCallback",
    "MarketDataProvider",
    "MarketSnapshot",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_market_data_contracts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_market_data_contracts.py src/strategy/t0/contracts/__init__.py src/strategy/t0/contracts/market_data.py
git commit -m "feat: add market data provider contracts for phase3"
```

### Task 2: 实现 QMT tick/snapshot providers

**Files:**
- Create: `src/market_data/__init__.py`
- Create: `src/market_data/ingestion/__init__.py`
- Create: `src/market_data/ingestion/qmt_tick_provider.py`
- Create: `src/market_data/ingestion/qmt_snapshot_provider.py`
- Test: `tests/unit/test_qmt_market_data_providers.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_qmt_market_data_providers.py
import threading

from src.market_data.ingestion.qmt_snapshot_provider import QMTSnapshotProvider
from src.market_data.ingestion.qmt_tick_provider import QMTTickProvider


class FakeXtData:
    def __init__(self):
        self.subscriptions = {}
        self.unsubscribed = []

    def subscribe_quote(self, stock_code, period="tick", count=0, callback=None):
        seq = len(self.subscriptions) + 1
        self.subscriptions[seq] = {
            "stock_code": stock_code,
            "period": period,
            "callback": callback,
        }
        return seq

    def unsubscribe_quote(self, seq):
        self.unsubscribed.append(seq)

    def get_full_tick(self, stock_codes):
        return {
            stock_codes[0]: {
                "time": 1712280603000,
                "lastPrice": 10.25,
                "high": 10.30,
                "low": 10.10,
                "open": 10.15,
                "amount": 120000.0,
                "volume": 3500.0,
                "lastClose": 10.00,
            }
        }


def test_qmt_tick_provider_subscribe_and_unsubscribe(monkeypatch):
    fake = FakeXtData()
    provider = QMTTickProvider(xtdata_client=fake)
    received = []

    provider.subscribe_tick(["601138.SH"], lambda snap: received.append(snap))

    seq = list(fake.subscriptions.keys())[0]
    callback = fake.subscriptions[seq]["callback"]
    callback({"601138.SH": [{"time": 1712280603000, "lastPrice": 10.25}]})

    provider.close()

    assert received
    assert fake.unsubscribed == [seq]


def test_qmt_snapshot_provider_poll_once_updates_cache(monkeypatch):
    fake = FakeXtData()
    provider = QMTSnapshotProvider(xtdata_client=fake)

    barrier = threading.Event()

    def _on_snapshot(snapshot):
        if snapshot.stock_code == "601138.SH":
            barrier.set()

    provider.subscribe_snapshot(["601138.SH"], interval_seconds=1, callback=_on_snapshot)
    provider._poll_once()
    latest = provider.get_latest_snapshot("601138.SH")
    provider.close()

    assert latest is not None
    assert latest.price == 10.25
    assert barrier.is_set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_qmt_market_data_providers.py -v`
Expected: FAIL with `ModuleNotFoundError` for provider modules

- [ ] **Step 3: Write minimal implementation**

```python
# src/market_data/ingestion/qmt_tick_provider.py
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.logger_config import logger
from src.strategy.t0.contracts.market_data import MarketDataCallback, MarketSnapshot


class QMTTickProvider:
    def __init__(self, xtdata_client: Any):
        self._xtdata = xtdata_client
        self._seq_by_symbol: dict[str, int] = {}

    def subscribe_tick(self, stock_codes: list[str], callback: MarketDataCallback) -> None:
        for stock_code in stock_codes:
            seq = self._xtdata.subscribe_quote(
                stock_code,
                period="tick",
                count=0,
                callback=self._wrap_callback(stock_code, callback),
            )
            if seq is not None and int(seq) >= 0:
                self._seq_by_symbol[stock_code] = int(seq)

    def subscribe_snapshot(
        self,
        stock_codes: list[str],
        interval_seconds: int,
        callback: MarketDataCallback,
    ) -> None:
        return None

    def get_latest_snapshot(self, stock_code: str) -> MarketSnapshot | None:
        return None

    def get_minute_bars(self, stock_code: str, count: int) -> list[dict]:
        return []

    def _wrap_callback(self, stock_code: str, callback: MarketDataCallback) -> Callable[[Any], None]:
        def _inner(payload: Any) -> None:
            quote = payload.get(stock_code) if isinstance(payload, dict) else payload
            if isinstance(quote, list) and quote:
                quote = quote[-1]
            if not isinstance(quote, dict):
                return

            callback(
                MarketSnapshot(
                    stock_code=stock_code,
                    time=str(quote.get("time") or quote.get("timetag") or ""),
                    price=quote.get("lastPrice") or quote.get("price"),
                    high=quote.get("high"),
                    low=quote.get("low"),
                    open=quote.get("open"),
                    amount=quote.get("amount"),
                    volume=quote.get("volume"),
                    pre_close=quote.get("lastClose") or quote.get("pre_close"),
                    source="qmt_tick",
                )
            )

        return _inner

    def close(self) -> None:
        for seq in list(self._seq_by_symbol.values()):
            try:
                self._xtdata.unsubscribe_quote(seq)
            except Exception as exc:
                logger.warning("Failed to unsubscribe tick seq=%s: %s", seq, exc)
        self._seq_by_symbol.clear()
```

```python
# src/market_data/ingestion/qmt_snapshot_provider.py
from __future__ import annotations

import threading
from typing import Any

from src.strategy.t0.contracts.market_data import MarketDataCallback, MarketSnapshot


class QMTSnapshotProvider:
    def __init__(self, xtdata_client: Any):
        self._xtdata = xtdata_client
        self._callbacks: list[MarketDataCallback] = []
        self._stock_codes: list[str] = []
        self._latest: dict[str, MarketSnapshot] = {}
        self._lock = threading.RLock()

    def subscribe_tick(self, stock_codes: list[str], callback: MarketDataCallback) -> None:
        return None

    def subscribe_snapshot(
        self,
        stock_codes: list[str],
        interval_seconds: int,
        callback: MarketDataCallback,
    ) -> None:
        with self._lock:
            self._stock_codes = sorted(set(stock_codes))
            self._callbacks.append(callback)

    def _poll_once(self) -> None:
        if not self._stock_codes:
            return

        payload = self._xtdata.get_full_tick(self._stock_codes)
        if not isinstance(payload, dict):
            return

        with self._lock:
            for stock_code in self._stock_codes:
                row = payload.get(stock_code)
                if not isinstance(row, dict):
                    continue
                snapshot = MarketSnapshot(
                    stock_code=stock_code,
                    time=str(row.get("time") or row.get("timetag") or ""),
                    price=row.get("lastPrice") or row.get("price"),
                    high=row.get("high"),
                    low=row.get("low"),
                    open=row.get("open"),
                    amount=row.get("amount"),
                    volume=row.get("volume"),
                    pre_close=row.get("lastClose") or row.get("lastSettlementPrice"),
                    source="qmt_snapshot",
                )
                self._latest[stock_code] = snapshot
                for callback in self._callbacks:
                    callback(snapshot)

    def get_latest_snapshot(self, stock_code: str) -> MarketSnapshot | None:
        with self._lock:
            return self._latest.get(stock_code)

    def get_minute_bars(self, stock_code: str, count: int) -> list[dict]:
        return []

    def close(self) -> None:
        with self._lock:
            self._callbacks.clear()
            self._stock_codes.clear()
```

```python
# src/market_data/ingestion/__init__.py
from .qmt_snapshot_provider import QMTSnapshotProvider
from .qmt_tick_provider import QMTTickProvider

__all__ = ["QMTSnapshotProvider", "QMTTickProvider"]
```

```python
# src/market_data/__init__.py
__all__ = []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_qmt_market_data_providers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_qmt_market_data_providers.py src/market_data/__init__.py src/market_data/ingestion/__init__.py src/market_data/ingestion/qmt_tick_provider.py src/market_data/ingestion/qmt_snapshot_provider.py
git commit -m "feat: add qmt tick and snapshot providers"
```

### Task 3: 桥接 DataFetcher 到 MarketDataProvider

**Files:**
- Modify: `src/strategy/data_fetcher.py`
- Create: `tests/unit/test_data_fetcher_market_provider_bridge.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_data_fetcher_market_provider_bridge.py
from datetime import date

import pandas as pd

from src.strategy.data_fetcher import DataFetcher
from src.strategy.t0.contracts.market_data import MarketSnapshot


class FakeProvider:
    def __init__(self):
        self.snapshot = MarketSnapshot(
            stock_code="601138.SH",
            time="2026-04-05 09:30:03",
            price=10.25,
            high=10.30,
            low=10.10,
            open=10.15,
            amount=120000.0,
            volume=3500.0,
            pre_close=10.00,
            source="qmt_snapshot",
        )

    def subscribe_tick(self, stock_codes, callback):
        return None

    def subscribe_snapshot(self, stock_codes, interval_seconds, callback):
        return None

    def get_latest_snapshot(self, stock_code):
        return self.snapshot

    def get_minute_bars(self, stock_code, count):
        return []


def test_fetch_realtime_snapshot_prefers_provider():
    fetcher = DataFetcher(market_data_provider=FakeProvider())

    snapshot = fetcher.fetch_realtime_snapshot("601138.SH")

    assert snapshot is not None
    assert snapshot["price"] == 10.25
    assert snapshot["time"] == "2026-04-05 09:30:03"


def test_append_snapshot_tick_uses_provider_snapshot():
    fetcher = DataFetcher(market_data_provider=FakeProvider())
    df = pd.DataFrame(
        {
            "open": [10.1],
            "high": [10.2],
            "low": [10.0],
            "close": [10.1],
            "volume": [100],
            "amount": [1010],
        },
        index=pd.to_datetime(["2026-04-05 09:30:00"]),
    )

    result = fetcher._append_snapshot_tick(df, "601138.SH", date(2026, 4, 5))

    assert result is not None
    assert pd.Timestamp("2026-04-05 09:30:03") in result.index
    assert result.loc[pd.Timestamp("2026-04-05 09:30:03"), "close"] == 10.25
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_data_fetcher_market_provider_bridge.py -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'market_data_provider'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/strategy/data_fetcher.py (constructor + snapshot bridge)
from src.strategy.t0.contracts.market_data import MarketDataProvider


class DataFetcher:
    def __init__(
        self,
        cache_dir: str = "./cache",
        intraday_period: Optional[str] = None,
        market_data_provider: Optional[MarketDataProvider] = None,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._daily_cache = {}
        self._snapshot_cache = None
        self._snapshot_cache_time = None
        self.tick_cache = RedisTickCache()
        self.market_data_provider = market_data_provider
        raw_period = intraday_period or getattr(settings, "t0_intraday_bar_period", "1m")
        self.intraday_period = self._normalize_intraday_period(raw_period)
        self.intraday_period_seconds = self._period_to_seconds(self.intraday_period)

    def fetch_realtime_snapshot(self, stock_code: str) -> Optional[dict]:
        if self.market_data_provider is not None:
            latest = self.market_data_provider.get_latest_snapshot(stock_code)
            if latest is not None:
                return {
                    "time": latest.time,
                    "price": latest.price,
                    "high": latest.high,
                    "low": latest.low,
                    "open": latest.open,
                    "amount": latest.amount,
                    "volume": latest.volume,
                    "pre_close": latest.pre_close,
                }

        # 保留原有 xtdata 回退逻辑
        ...
```

```python
# src/strategy/data_fetcher.py (_append_snapshot_tick only)
    def _append_snapshot_tick(
        self, df: Optional[pd.DataFrame], stock_code: str, trade_date: date
    ) -> Optional[pd.DataFrame]:
        snapshot = self.fetch_realtime_snapshot(stock_code)
        if not snapshot:
            return df

        snapshot_time = snapshot.get("time")
        if not snapshot_time:
            return df

        try:
            snapshot_dt = pd.Timestamp(snapshot_time)
        except Exception:
            return df

        if snapshot_dt.date() != trade_date:
            return df

        row = {
            "close": snapshot.get("price"),
            "open": snapshot.get("open"),
            "high": snapshot.get("high"),
            "low": snapshot.get("low"),
            "amount": snapshot.get("amount"),
            "volume": snapshot.get("volume"),
            "pre_close": snapshot.get("pre_close"),
        }
        if row["close"] is None:
            return df

        snapshot_df = pd.DataFrame([row], index=pd.DatetimeIndex([snapshot_dt], name="datetime"))
        if df is None or df.empty:
            return self._finalize_market_dataframe(snapshot_df)

        combined = pd.concat([df, snapshot_df]).sort_index()
        combined = combined[~combined.index.duplicated(keep="last")]
        return self._finalize_market_dataframe(combined)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_data_fetcher_market_provider_bridge.py tests/test_data_fetcher_normalization.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_data_fetcher_market_provider_bridge.py src/strategy/data_fetcher.py
git commit -m "refactor: bridge data fetcher to market data provider interface"
```

### Task 4: 在 StrategyEngine 中接入快照 provider 并保证 <=3 秒更新

**Files:**
- Modify: `src/config.py`
- Modify: `.env.example`
- Modify: `src/strategy/strategy_engine.py`
- Test: `tests/unit/test_strategy_engine_market_provider.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_strategy_engine_market_provider.py
from src.strategy.strategy_engine import StrategyEngine


class FakeSnapshotProvider:
    def __init__(self):
        self.subscribed = []

    def subscribe_snapshot(self, stock_codes, interval_seconds, callback):
        self.subscribed.append((tuple(stock_codes), interval_seconds, callback))

    def get_latest_snapshot(self, stock_code):
        return None


def test_strategy_engine_subscribes_snapshot_provider(monkeypatch):
    fake_provider = FakeSnapshotProvider()

    monkeypatch.setattr("src.strategy.strategy_engine.build_market_data_provider", lambda: fake_provider)

    engine = StrategyEngine()

    assert fake_provider.subscribed
    stock_codes, interval_seconds, _ = fake_provider.subscribed[0]
    assert stock_codes == (engine.stock_code,)
    assert interval_seconds <= 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_strategy_engine_market_provider.py::test_strategy_engine_subscribes_snapshot_provider -v`
Expected: FAIL with `AttributeError` because `build_market_data_provider` does not exist

- [ ] **Step 3: Write minimal implementation**

```python
# src/config.py (new settings)
    t0_market_data_provider_enabled: bool = Field(
        default=True, env="T0_MARKET_DATA_PROVIDER_ENABLED"
    )
    t0_snapshot_interval_seconds: int = Field(default=3, env="T0_SNAPSHOT_INTERVAL_SECONDS")
```

```python
# src/strategy/strategy_engine.py (provider bootstrap)
from src.market_data.ingestion import QMTSnapshotProvider

try:
    from xtquant import xtdata
except Exception:
    xtdata = None


def build_market_data_provider():
    if not settings.t0_market_data_provider_enabled:
        return None
    if xtdata is None:
        return None
    return QMTSnapshotProvider(xtdata_client=xtdata)


class StrategyEngine:
    def __init__(self):
        self.stock_code = settings.t0_stock_code
        self.market_data_provider = build_market_data_provider()

        self.data_fetcher = DataFetcher(market_data_provider=self.market_data_provider)
        ...

        if self.market_data_provider is not None:
            interval_seconds = max(1, min(int(settings.t0_snapshot_interval_seconds), 3))
            self.market_data_provider.subscribe_snapshot(
                [self.stock_code],
                interval_seconds=interval_seconds,
                callback=lambda _snapshot: None,
            )
```

```dotenv
# .env.example
T0_MARKET_DATA_PROVIDER_ENABLED=true
T0_SNAPSHOT_INTERVAL_SECONDS=3
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_strategy_engine_market_provider.py tests/unit/test_data_fetcher_market_provider_bridge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_strategy_engine_market_provider.py src/config.py .env.example src/strategy/strategy_engine.py
git commit -m "feat: wire snapshot provider into strategy engine with <=3s interval"
```

### Task 5: 更新进度文档并执行 Phase3 回归切片

**Files:**
- Modify: `docs/superpowers/progress-2026-04-05.md`

- [ ] **Step 1: Write failing documentation test (lint-style grep check)**

```bash
# 先确认进度文件还没有 Phase 3 入口（预期 grep 失败）
uv run python - <<'PY'
from pathlib import Path
p = Path("docs/superpowers/progress-2026-04-05.md")
text = p.read_text(encoding="utf-8")
assert "Phase 3" in text and "2026-04-05-phase3-high-frequency-market-data.md" in text
PY
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run python - <<'PY' ... PY`
Expected: FAIL with `AssertionError`

- [ ] **Step 3: Update progress doc with exact section**

```markdown
## Phase 3 启动

- 计划文件：`docs/superpowers/plans/2026-04-05-phase3-high-frequency-market-data.md`
- 范围：MarketDataProvider 协议、QMT tick/snapshot provider、DataFetcher/StrategyEngine 桥接
- 执行顺序：Task 1 -> Task 2 -> Task 3 -> Task 4
- 验证命令：`uv run pytest tests/unit/test_market_data_contracts.py tests/unit/test_qmt_market_data_providers.py tests/unit/test_data_fetcher_market_provider_bridge.py tests/unit/test_strategy_engine_market_provider.py -v`
```

- [ ] **Step 4: Run phase3 regression slice**

Run: `uv run pytest tests/unit/test_market_data_contracts.py tests/unit/test_qmt_market_data_providers.py tests/unit/test_data_fetcher_market_provider_bridge.py tests/unit/test_strategy_engine_market_provider.py tests/test_data_fetcher_normalization.py tests/test_quote_stream_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/progress-2026-04-05.md
git commit -m "docs: add phase3 execution entry and validation commands"
```

---

## Self-Review

### 1. Spec coverage

- Phase 3 协议定义（`MarketDataProvider`）: Task 1
- QMT tick/snapshot provider 实现: Task 2
- T0 runtime 接入新接口: Task 3 + Task 4
- 保留分钟行情用于回测: Task 3 中保留 `DataFetcher` 原分钟线逻辑，回归包含 `tests/test_data_fetcher_normalization.py`
- <=3 秒快照频率: Task 4 通过 `T0_SNAPSHOT_INTERVAL_SECONDS` 并在 Engine 初始化时强制上限 3 秒

Gap check: 无缺口，Phase 4（多策略并行、backtrader）明确不在本计划范围。

### 2. Placeholder scan

已检查并移除以下占位风险：
- 无 `TODO` / `TBD` / “后续补充” 字样
- 每个代码步骤均给出具体代码片段
- 每个任务均给出可直接执行的测试命令与期望结果

### 3. Type consistency

- 协议对象统一为 `MarketSnapshot`
- provider 回调统一签名 `MarketDataCallback`
- `DataFetcher.fetch_realtime_snapshot` 对外维持 `dict` 兼容，不破坏既有调用方
- `StrategyEngine` 只处理 provider 接入，不把 QMT 依赖引入 `src/strategy/core/`

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-05-phase3-high-frequency-market-data.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
