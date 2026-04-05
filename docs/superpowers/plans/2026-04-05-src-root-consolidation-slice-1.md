# Src Root Consolidation Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the first batch of obviously misplaced `src/` root modules into canonical packages without changing behavior, and add guard tests that keep new code off the old root paths.

**Architecture:** This plan only covers the lowest-risk `src` root files whose ownership is already clear from the current architecture: minute-history modules, Meta DB sync, and the Redis trade-record client. It keeps migration risk low by moving a small batch, updating direct import sites, and adding structure tests before any wrapper cleanup.

**Tech Stack:** Python 3.9+, pytest, SQLAlchemy, Redis, xtquant, apply_patch/git mv

---

## File Structure Map

### Create

- `src/market_data/export/__init__.py`
- `src/market_data/export/minute_history_exporter.py`
- `src/market_data/storage/__init__.py`
- `src/market_data/storage/minute_history_models.py`
- `src/infrastructure/db/trading_meta_sync.py`
- `src/infrastructure/redis/trade_records_client.py`
- `tests/unit/test_src_root_consolidation_slice_1.py`

### Modify

- `src/minute_history_ingestor.py`
- `main.py`
- `src/trading/execution/qmt_trader.py`
- `tests/test_minute_history_exporter.py`
- `tests/test_minute_history_ingestor.py`
- `tests/test_remote_sync.py`
- `tests/test_trading_meta_sync.py`
- `tests/unit/test_trading_meta_sync_import.py`
- `tests/live/test_redis_integration.py`

### Delete After Migration

- `src/minute_history_exporter.py`
- `src/minute_history_models.py`
- `src/trading_meta_sync.py`
- `src/redis_client.py`

### Keep For Later Slice

- `src/account_data_service.py`
- `src/account_position_sync.py`
- `src/quote_stream_service.py`
- `src/quote_websocket.py`
- `src/trading_service.py`

### Task 1: Add structural guard tests for slice 1

**Files:**
- Create: `tests/unit/test_src_root_consolidation_slice_1.py`
- Test: `tests/unit/test_src_root_consolidation_slice_1.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_slice_1_legacy_root_modules_are_removed():
    legacy_paths = [
        REPO_ROOT / "src" / "minute_history_exporter.py",
        REPO_ROOT / "src" / "minute_history_models.py",
        REPO_ROOT / "src" / "trading_meta_sync.py",
        REPO_ROOT / "src" / "redis_client.py",
    ]

    missing = [path.as_posix() for path in legacy_paths if path.exists()]
    assert missing == []


def test_slice_1_canonical_modules_exist():
    canonical_paths = [
        REPO_ROOT / "src" / "market_data" / "export" / "minute_history_exporter.py",
        REPO_ROOT / "src" / "market_data" / "storage" / "minute_history_models.py",
        REPO_ROOT / "src" / "infrastructure" / "db" / "trading_meta_sync.py",
        REPO_ROOT / "src" / "infrastructure" / "redis" / "trade_records_client.py",
    ]

    missing = [path.as_posix() for path in canonical_paths if not path.exists()]
    assert missing == []


def test_slice_1_no_production_imports_use_old_module_paths():
    forbidden_imports = [
        "from src.minute_history_exporter import",
        "import src.minute_history_exporter",
        "from src.minute_history_models import",
        "import src.minute_history_models",
        "from src.trading_meta_sync import",
        "import src.trading_meta_sync",
        "from src.redis_client import",
        "import src.redis_client",
    ]
    offenders = []

    for file_path in (REPO_ROOT / "src").rglob("*.py"):
        text = file_path.read_text(encoding="utf-8")
        for marker in forbidden_imports:
            if marker in text:
                offenders.append(f"{file_path.as_posix()}: {marker}")

    assert offenders == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_src_root_consolidation_slice_1.py -v`
Expected: FAIL because the legacy root files still exist and import sites still point at the old module paths.

- [ ] **Step 3: Add the new test file**

```bash
git add tests/unit/test_src_root_consolidation_slice_1.py
```

- [ ] **Step 4: Re-run the same test**

Run: `uv run pytest tests/unit/test_src_root_consolidation_slice_1.py -v`
Expected: FAIL with the same structural assertions. Keep the failure as the red phase for the next tasks.

- [ ] **Step 5: Commit the failing test**

```bash
git add tests/unit/test_src_root_consolidation_slice_1.py
git commit -m "test: add src root consolidation slice 1 guard"
```

### Task 2: Move minute-history exporter and models into market_data

**Files:**
- Create: `src/market_data/export/__init__.py`
- Create: `src/market_data/export/minute_history_exporter.py`
- Create: `src/market_data/storage/__init__.py`
- Create: `src/market_data/storage/minute_history_models.py`
- Modify: `src/minute_history_ingestor.py`
- Modify: `main.py`
- Modify: `tests/test_minute_history_exporter.py`
- Modify: `tests/test_remote_sync.py`

- [ ] **Step 1: Write the failing import update in tests**

```python
import src.market_data.export.minute_history_exporter as minute_history_exporter
```

Replace the old imports in these files:

```python
# tests/test_minute_history_exporter.py
import src.market_data.export.minute_history_exporter as minute_history_exporter

# tests/test_remote_sync.py
import src.market_data.export.minute_history_exporter as minute_history_exporter
```

- [ ] **Step 2: Run targeted tests to verify they fail before the move**

Run: `uv run pytest tests/test_minute_history_exporter.py tests/test_remote_sync.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.market_data.export'`.

- [ ] **Step 3: Move exporter and models into canonical packages**

```bash
mkdir -p src/market_data/export src/market_data/storage
git mv src/minute_history_exporter.py src/market_data/export/minute_history_exporter.py
git mv src/minute_history_models.py src/market_data/storage/minute_history_models.py
printf '"""Market-data export package."""\n' > src/market_data/export/__init__.py
printf '"""Market-data storage package."""\n' > src/market_data/storage/__init__.py
```

Update imports to the canonical paths:

```python
# src/minute_history_ingestor.py
from src.market_data.export.minute_history_exporter import (
    StockRecord,
    fetch_stock_records,
    normalize_result,
    normalize_trade_date,
    resolve_date_range,
)
from src.market_data.storage.minute_history_models import (
    MINUTE_BAR_SCHEMA,
    MinuteBarBase,
    StockMinuteBar,
)

# main.py
from src.market_data.export.minute_history_exporter import main as export_main

# tests/test_minute_history_exporter.py
import src.market_data.export.minute_history_exporter as minute_history_exporter

# tests/test_remote_sync.py
import src.market_data.export.minute_history_exporter as minute_history_exporter
```

- [ ] **Step 4: Run the focused minute-history test set**

Run: `uv run pytest tests/test_minute_history_exporter.py tests/test_minute_history_ingestor.py tests/test_remote_sync.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the market-data relocation**

```bash
git add src/market_data/export/__init__.py src/market_data/export/minute_history_exporter.py src/market_data/storage/__init__.py src/market_data/storage/minute_history_models.py src/minute_history_ingestor.py main.py tests/test_minute_history_exporter.py tests/test_minute_history_ingestor.py tests/test_remote_sync.py
git commit -m "refactor: move minute history modules into market_data"
```

### Task 3: Move Meta DB sync into infrastructure/db

**Files:**
- Create: `src/infrastructure/db/trading_meta_sync.py`
- Modify: `tests/test_trading_meta_sync.py`
- Modify: `tests/unit/test_trading_meta_sync_import.py`

- [ ] **Step 1: Write the failing import update**

Replace the old imports in these files:

```python
# tests/test_trading_meta_sync.py
from src.infrastructure.db.trading_meta_sync import _read_source_rows, sync_sqlite_to_meta_db

# tests/unit/test_trading_meta_sync_import.py
from src.infrastructure.db.trading_meta_sync import sync_sqlite_to_meta_db
```

Update monkeypatch targets too:

```python
monkeypatch.setattr("src.infrastructure.db.trading_meta_sync._resolve_source_db_url", lambda: db_url)
monkeypatch.setattr("src.infrastructure.db.trading_meta_sync._read_source_rows", lambda: source_rows)
monkeypatch.setattr("src.infrastructure.db.trading_meta_sync._sync_rows_to_meta_db", fake_sync)
```

- [ ] **Step 2: Run the Meta DB sync tests to verify they fail**

Run: `uv run pytest tests/test_trading_meta_sync.py tests/unit/test_trading_meta_sync_import.py -v`
Expected: FAIL with `ModuleNotFoundError` for `src.infrastructure.db.trading_meta_sync`.

- [ ] **Step 3: Move the module and keep behavior unchanged**

```bash
git mv src/trading_meta_sync.py src/infrastructure/db/trading_meta_sync.py
```

The moved module keeps the same public API:

```python
SYNC_TABLES = (
    "trading_calendar",
    "stock_info",
    "trading_signals",
    "order_records",
    "strategy_regime_state",
    "strategy_signal_history",
)


def sync_sqlite_to_meta_db() -> TradingMetaSyncResult:
    rows_by_table = _read_source_rows()
    return asyncio.run(_sync_rows_to_meta_db(rows_by_table))
```

- [ ] **Step 4: Run the Meta DB sync tests**

Run: `uv run pytest tests/test_trading_meta_sync.py tests/unit/test_trading_meta_sync_import.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the DB sync relocation**

```bash
git add src/infrastructure/db/trading_meta_sync.py tests/test_trading_meta_sync.py tests/unit/test_trading_meta_sync_import.py
git commit -m "refactor: move trading meta sync into infrastructure db"
```

### Task 4: Move the Redis trade-record client into infrastructure/redis

**Files:**
- Create: `src/infrastructure/redis/trade_records_client.py`
- Modify: `src/trading/execution/qmt_trader.py`
- Modify: `tests/live/test_redis_integration.py`

- [ ] **Step 1: Write the failing import update**

Replace the old imports in these files:

```python
# src/trading/execution/qmt_trader.py
from src.infrastructure.redis.trade_records_client import redis_trade_client

# tests/live/test_redis_integration.py
from src.infrastructure.redis.trade_records_client import redis_trade_client
```

- [ ] **Step 2: Run the affected tests to verify they fail**

Run: `uv run pytest tests/live/test_redis_integration.py -v`
Expected: FAIL with `ModuleNotFoundError` for `src.infrastructure.redis.trade_records_client`.

- [ ] **Step 3: Move the module and preserve the singleton export**

```bash
git mv src/redis_client.py src/infrastructure/redis/trade_records_client.py
```

Ensure the moved file still exports the same singleton:

```python
redis_trade_client = RedisTradeRecordsClient()
```

Update imports to the canonical path:

```python
from src.infrastructure.redis.trade_records_client import redis_trade_client
```

- [ ] **Step 4: Run the focused Redis test set**

Run: `uv run pytest tests/live/test_redis_integration.py tests/unit/test_src_root_consolidation_slice_1.py -v`
Expected: PASS for the import path update. If the live Redis test requires external services, keep the structural unit test as the required gate and note the live dependency in the commit message.

- [ ] **Step 5: Commit the Redis client relocation**

```bash
git add src/infrastructure/redis/trade_records_client.py src/trading/execution/qmt_trader.py tests/live/test_redis_integration.py tests/unit/test_src_root_consolidation_slice_1.py
git commit -m "refactor: move redis trade client into infrastructure redis"
```

### Task 5: Make the structural guard pass and close slice 1

**Files:**
- Modify: `tests/unit/test_src_root_consolidation_slice_1.py`
- Test: `tests/unit/test_src_root_consolidation_slice_1.py`

- [ ] **Step 1: Remove any remaining old-path imports in production code**

Search and fix remaining references:

```bash
rg "src\.minute_history_exporter|src\.minute_history_models|src\.trading_meta_sync|src\.redis_client" src tests main.py
```

Expected remaining hits before cleanup: only files intentionally updated in this slice.

- [ ] **Step 2: Run the structural guard test**

Run: `uv run pytest tests/unit/test_src_root_consolidation_slice_1.py -v`
Expected: PASS.

- [ ] **Step 3: Run the full slice 1 regression set**

Run: `uv run pytest tests/unit/test_src_root_consolidation_slice_1.py tests/test_minute_history_exporter.py tests/test_minute_history_ingestor.py tests/test_remote_sync.py tests/test_trading_meta_sync.py tests/unit/test_trading_meta_sync_import.py -v`
Expected: PASS.

- [ ] **Step 4: Record the slice boundary in docs/superpowers progress notes**

Append a short note to the current progress log describing the moved canonical paths:

```text
Slice 1 moved src root modules into canonical packages:
- minute_history_exporter -> src/market_data/export/minute_history_exporter.py
- minute_history_models -> src/market_data/storage/minute_history_models.py
- trading_meta_sync -> src/infrastructure/db/trading_meta_sync.py
- redis_client -> src/infrastructure/redis/trade_records_client.py
```

- [ ] **Step 5: Commit the passing slice**

```bash
git add tests/unit/test_src_root_consolidation_slice_1.py docs/superpowers/progress-2026-04-05.md
git commit -m "docs: record src root consolidation slice 1"
```

## Self-Review Notes

- Spec coverage: this plan implements the first `src` consolidation slice from the approved spec and intentionally leaves `tests/docs/migrations` and the remaining root modules for separate plans.
- Placeholder scan: no `TODO`/`TBD` placeholders remain; all tasks name exact files, commands, and expected results.
- Type consistency: canonical module names are consistent across tasks: `src.market_data.export.minute_history_exporter`, `src.market_data.storage.minute_history_models`, `src.infrastructure.db.trading_meta_sync`, and `src.infrastructure.redis.trade_records_client`.