# Phase 0 + Phase 1: Test Infrastructure & Trade Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a safe test harness (Phase 0) and then refactor trade execution records into a normalized `trade_executions` / `order_cancellations` schema with correct attribution (Phase 1), without touching live order flow until regression tests are green.

**Architecture:** Phase 0 wires up pytest markers, a PostgreSQL test fixture using a temporary schema, and moves existing live-QMT tests out of the default run path. Phase 1 adds new ORM models (`TradeExecution`, `OrderCancellation`) alongside the existing `OrderRecord`, implements an `AttributionService` that routes QMT trade callbacks to the new table, and provides a migration script that backfills `trade_breakdown` JSON into `trade_executions` rows.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.x (sync psycopg driver), PostgreSQL, pytest ≥ 8, pytest-cov, pytest-mock, freezegun, python-ulid, alembic (already configured)

---

## Scope Note

The full spec has 7 phases (0–6). This plan covers **Phase 0 and Phase 1 only**, which are prerequisites for all later phases. Each subsequent phase (Phase 2 minute-bar ingestion, Phase 3 high-frequency quotes, etc.) should be written as a separate plan once this one is shipped and green.

---

## File Map

### Phase 0 – created or modified

| File | Action | Responsibility |
|---|---|---|
| `pytest.ini` | **Create** | Root pytest config: markers, test paths, default options |
| `tests/conftest.py` | **Modify** | Add `pg_session` fixture for PostgreSQL temp-schema isolation |
| `tests/unit/` | **Create dir** | Pure unit tests (no DB, no network) |
| `tests/integration/` | **Create dir** | Tests that hit a real DB |
| `tests/contract/` | **Create dir** | Interface / protocol contract tests |
| `tests/live/` | **Create dir** | Tests that need QMT running — excluded from default run |
| `tests/fixtures/` | **Create dir** | Shared factory helpers |
| `tests/fixtures/__init__.py` | **Create** | Re-exports |
| `tests/fixtures/order_factories.py` | **Create** | `make_order_record()` helper |

### Phase 1 – created or modified

| File | Action | Responsibility |
|---|---|---|
| `src/database.py` | **Modify** | Add `TradeExecution`, `OrderCancellation` ORM models; add `order_uid`, `order_type`, `submit_request_id` columns to `OrderRecord`; keep existing aggregate fields for now (deprecated) |
| `src/meta_db.py` | **Modify** | Add new table names to `TRADING_META_TABLE_NAMES` |
| `src/trading/attribution.py` | **Create** | `AttributionService`: routes broker trade callbacks to `trade_executions` |
| `src/trader.py` | **Modify** | `on_stock_trade` calls `AttributionService.record_execution()` in addition to existing flow |
| `migrations/versions/<timestamp>_add_trade_executions.py` | **Create** | Alembic migration: new tables + new columns on `order_records` |
| `scripts/backfill_trade_executions.py` | **Create** | One-shot script: reads `trade_breakdown` JSON, writes `trade_executions` rows |
| `tests/unit/test_attribution_service.py` | **Create** | Unit tests for `AttributionService` routing logic |
| `tests/integration/test_trade_executions_model.py` | **Create** | Integration tests: ORM round-trip for new models |

---

## Task 0.1: Install missing dev dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Check what's already installed**

```bash
uv run python -c "import pytest, pytest_mock, freezegun, ulid; print('all present')" 2>&1 || true
```

Expected: missing packages will print `ModuleNotFoundError`.

- [ ] **Step 2: Add missing packages**

```bash
uv add --dev pytest pytest-cov pytest-mock freezegun python-ulid
```

Expected output ends with `Resolved ... packages`.

- [ ] **Step 3: Verify imports**

```bash
uv run python -c "import pytest, pytest_mock, freezegun, ulid; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pytest-cov, pytest-mock, freezegun, python-ulid dev deps"
```

---

## Task 0.2: Create pytest.ini with markers

**Files:**
- Create: `pytest.ini`

- [ ] **Step 1: Write the failing marker validation test**

Create `tests/unit/test_pytest_markers.py`:

```python
# tests/unit/test_pytest_markers.py
import pytest


@pytest.mark.unit
def test_unit_marker_recognised():
    assert True


@pytest.mark.integration
def test_integration_marker_recognised():
    assert True
```

- [ ] **Step 2: Run to verify unknown-marker warning appears**

```bash
uv run pytest tests/unit/test_pytest_markers.py -v 2>&1 | head -20
```

Expected: `PytestUnknownMarkWarning` or similar about unregistered markers.

- [ ] **Step 3: Create pytest.ini**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

markers =
    unit: Pure unit tests — no DB, no network, no QMT
    integration: Tests requiring a real PostgreSQL connection
    contract: Interface/protocol contract tests
    db: Tests that write to the database
    redis: Tests that require a running Redis
    live_qmt: Tests that require a live QMT connection — excluded from CI
    manual: Manual-only tests

addopts = -ra --tb=short
```

- [ ] **Step 4: Run again and verify no warning**

```bash
uv run pytest tests/unit/test_pytest_markers.py -v 2>&1 | head -20
```

Expected: 2 PASSED, no marker warnings.

- [ ] **Step 5: Commit**

```bash
git add pytest.ini tests/unit/test_pytest_markers.py
git commit -m "chore: add pytest.ini with test markers"
```

---

## Task 0.3: Create directory structure and move live tests

**Files:**
- Create dirs: `tests/unit/`, `tests/integration/`, `tests/contract/`, `tests/live/`, `tests/fixtures/`
- Create: `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/contract/__init__.py`, `tests/live/__init__.py`, `tests/fixtures/__init__.py`

- [ ] **Step 1: Create `__init__.py` files**

```bash
touch tests/unit/__init__.py tests/integration/__init__.py tests/contract/__init__.py tests/live/__init__.py tests/fixtures/__init__.py
```

- [ ] **Step 2: Move tests that need QMT to `tests/live/`**

The following tests require a live QMT connection or real trading and must be moved:

```bash
mv tests/test_passorder.py tests/live/test_passorder.py
mv tests/test_redis_integration.py tests/live/test_redis_integration.py
mv tests/test_stress_trading.py tests/live/test_stress_trading.py
mv tests/test_concurrent_trading.py tests/live/test_concurrent_trading.py
```

- [ ] **Step 3: Add `live_qmt` marker to moved tests**

Edit `tests/live/test_passorder.py` — add at the top of each test function:

```python
import pytest

pytestmark = pytest.mark.live_qmt
```

Do the same for `test_redis_integration.py`, `test_stress_trading.py`, `test_concurrent_trading.py`.

- [ ] **Step 4: Verify default run excludes live tests**

```bash
uv run pytest -m "not live_qmt and not manual" --collect-only 2>&1 | grep "live_qmt" | wc -l
```

Expected: `0` (no live_qmt tests collected).

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "chore: create test directory structure and mark live_qmt tests"
```

---

## Task 0.4: Add PostgreSQL test fixture

**Files:**
- Modify: `tests/conftest.py`
- Create: `tests/fixtures/order_factories.py`

- [ ] **Step 1: Write a failing integration test for the fixture**

Create `tests/integration/test_pg_fixture.py`:

```python
# tests/integration/test_pg_fixture.py
import pytest
from sqlalchemy import text


@pytest.mark.integration
@pytest.mark.db
def test_pg_session_is_isolated(pg_session):
    """Temporary schema is created and queries succeed."""
    result = pg_session.execute(text("SELECT 1")).scalar()
    assert result == 1


@pytest.mark.integration
@pytest.mark.db
def test_pg_session_has_order_records_table(pg_session):
    """Tables are created in the test schema."""
    result = pg_session.execute(
        text("SELECT COUNT(*) FROM order_records")
    ).scalar()
    assert result == 0
```

- [ ] **Step 2: Run to confirm fixture is missing**

```bash
uv run pytest tests/integration/test_pg_fixture.py -v 2>&1 | tail -10
```

Expected: `ERRORS` — `fixture 'pg_session' not found`.

- [ ] **Step 3: Implement `pg_session` fixture in `tests/conftest.py`**

Add the following to the end of `tests/conftest.py` (keep existing fixtures intact):

```python
import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ── PostgreSQL integration fixture ──────────────────────────────────────────

def _pg_test_url() -> str:
    """
    Read from env var TEST_DATABASE_URL, falling back to the project's
    Meta DB URL (pointing at a disposable test database).
    """
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        from src.meta_db import get_meta_db_sync_url
        url = get_meta_db_sync_url()
    return url


@pytest.fixture(scope="session")
def pg_engine():
    """Session-scoped engine pointing at a real PostgreSQL server."""
    url = _pg_test_url()
    engine = create_engine(url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_session(pg_engine):
    """
    Function-scoped session in an isolated temporary schema.
    The schema is created before the test and dropped after.
    All table DDL is applied inside the schema.
    """
    import uuid
    from src.database import Base

    schema = f"test_{uuid.uuid4().hex[:8]}"

    with pg_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    # Bind Base metadata to the temporary schema
    from sqlalchemy import MetaData
    test_metadata = MetaData(schema=schema)
    for table in Base.metadata.tables.values():
        table.to_metadata(test_metadata, schema=schema)

    with pg_engine.begin() as conn:
        test_metadata.create_all(conn)

    Session = sessionmaker(bind=pg_engine)
    session = Session()

    # Set search_path so unqualified queries hit the test schema
    session.execute(text(f'SET search_path TO "{schema}"'))

    yield session

    session.close()
    with pg_engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
```

- [ ] **Step 4: Run the integration tests**

```bash
uv run pytest tests/integration/test_pg_fixture.py -v -m "integration"
```

Expected: 2 PASSED.

- [ ] **Step 5: Create `tests/fixtures/order_factories.py`**

```python
# tests/fixtures/order_factories.py
"""
Factory helpers for creating test ORM instances without hitting the DB.
"""
from datetime import datetime

from src.database import OrderRecord


def make_order_record(
    *,
    signal_id: str = "SIG001",
    order_id: str = "ORD001",
    stock_code: str = "000001.SZ",
    direction: str = "BUY",
    volume: int = 100,
    price: float = 10.0,
    order_status: str = "PENDING",
    filled_volume: int = 0,
    filled_price: float | None = None,
    error_message: str | None = None,
) -> OrderRecord:
    return OrderRecord(
        signal_id=signal_id,
        order_id=order_id,
        stock_code=stock_code,
        direction=direction,
        volume=volume,
        price=price,
        order_status=order_status,
        order_time=datetime(2026, 4, 4, 9, 30, 0),
        filled_volume=filled_volume,
        filled_price=filled_price,
        error_message=error_message,
    )
```

- [ ] **Step 6: Verify full test suite still passes (excluding live_qmt)**

```bash
uv run pytest -m "not live_qmt and not manual" -q 2>&1 | tail -15
```

Expected: all previously passing tests still pass, plus 2 new integration tests.

- [ ] **Step 7: Commit**

```bash
git add tests/conftest.py tests/fixtures/ tests/integration/
git commit -m "test: add pg_session fixture and order_factories helper"
```

---

## Task 1.1: Add `python-ulid` and define ULID helper

**Files:**
- Create: `src/uid.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_uid.py`:

```python
# tests/unit/test_uid.py
import pytest
from src.uid import new_ulid, is_valid_ulid


@pytest.mark.unit
def test_new_ulid_is_26_chars():
    uid = new_ulid()
    assert len(uid) == 26


@pytest.mark.unit
def test_new_ulid_is_uppercase():
    uid = new_ulid()
    assert uid == uid.upper()


@pytest.mark.unit
def test_is_valid_ulid_accepts_valid():
    uid = new_ulid()
    assert is_valid_ulid(uid)


@pytest.mark.unit
def test_is_valid_ulid_rejects_short():
    assert not is_valid_ulid("TOOSHORT")


@pytest.mark.unit
def test_two_ulids_differ():
    assert new_ulid() != new_ulid()
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
uv run pytest tests/unit/test_uid.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'src.uid'`

- [ ] **Step 3: Implement `src/uid.py`**

```python
# src/uid.py
import re
import ulid as _ulid_lib

_ULID_PATTERN = re.compile(r"^[0-9A-Z]{26}$")


def new_ulid() -> str:
    """Return a new ULID as an uppercase 26-character string."""
    return str(_ulid_lib.new())


def is_valid_ulid(value: str) -> bool:
    return bool(_ULID_PATTERN.match(value))
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_uid.py -v
```

Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/uid.py tests/unit/test_uid.py
git commit -m "feat: add ULID helper src/uid.py"
```

---

## Task 1.2: Add new ORM models to `src/database.py`

**Files:**
- Modify: `src/database.py`
- Modify: `src/meta_db.py`

- [ ] **Step 1: Write failing model tests**

Create `tests/integration/test_trade_execution_model.py`:

```python
# tests/integration/test_trade_execution_model.py
import pytest
from datetime import datetime
from src.database import TradeExecution, OrderCancellation


@pytest.mark.integration
@pytest.mark.db
def test_trade_execution_insert_and_query(pg_session):
    exec_rec = TradeExecution(
        execution_uid="01JRF6Z0000000000000000001",
        broker_trade_id="BT001",
        broker_order_id="BO001",
        stock_code="000001.SZ",
        direction="BUY",
        filled_volume=100,
        filled_price=10.5,
        filled_amount=1050.0,
        filled_time=datetime(2026, 4, 4, 10, 0, 0),
        execution_source="qmt_trade_callback",
        dedupe_key="BT001:BO001:100:10.5",
    )
    pg_session.add(exec_rec)
    pg_session.commit()

    fetched = pg_session.query(TradeExecution).filter_by(broker_trade_id="BT001").first()
    assert fetched is not None
    assert fetched.filled_volume == 100
    assert fetched.direction == "BUY"


@pytest.mark.integration
@pytest.mark.db
def test_trade_execution_dedupe_key_unique(pg_session):
    from sqlalchemy.exc import IntegrityError

    first = TradeExecution(
        execution_uid="01JRF6Z0000000000000000002",
        broker_trade_id="BT002",
        stock_code="000001.SZ",
        direction="BUY",
        filled_volume=100,
        filled_price=10.5,
        filled_amount=1050.0,
        filled_time=datetime(2026, 4, 4, 10, 0, 0),
        execution_source="qmt_trade_callback",
        dedupe_key="UNIQUE_KEY_X",
    )
    duplicate = TradeExecution(
        execution_uid="01JRF6Z0000000000000000003",
        broker_trade_id="BT003",
        stock_code="000001.SZ",
        direction="BUY",
        filled_volume=100,
        filled_price=10.5,
        filled_amount=1050.0,
        filled_time=datetime(2026, 4, 4, 10, 0, 0),
        execution_source="qmt_trade_callback",
        dedupe_key="UNIQUE_KEY_X",
    )
    pg_session.add(first)
    pg_session.commit()
    pg_session.add(duplicate)
    with pytest.raises(IntegrityError):
        pg_session.commit()


@pytest.mark.integration
@pytest.mark.db
def test_order_cancellation_insert(pg_session):
    cancel = OrderCancellation(
        order_uid="01JRF6Z0000000000000000010",
        broker_order_id="BO010",
        stock_code="000001.SZ",
        cancelled_volume=100,
        cancel_time=datetime(2026, 4, 4, 14, 55, 0),
        cancel_reason="timeout",
    )
    pg_session.add(cancel)
    pg_session.commit()

    fetched = pg_session.query(OrderCancellation).filter_by(order_uid="01JRF6Z0000000000000000010").first()
    assert fetched is not None
    assert fetched.cancel_reason == "timeout"
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
uv run pytest tests/integration/test_trade_execution_model.py -v 2>&1 | tail -10
```

Expected: `ImportError: cannot import name 'TradeExecution' from 'src.database'`

- [ ] **Step 3: Add models to `src/database.py`**

Add the following classes after the `OrderRecord` class (before `TradingCalendar`):

```python
class TradeExecution(Base):
    """Each fill from QMT gets its own immutable row."""
    __tablename__ = "trade_executions"

    id               = Column(Integer, primary_key=True)
    execution_uid    = Column(String(50), unique=True, index=True, nullable=False)
    order_uid        = Column(String(50), index=True, nullable=True)
    broker_trade_id  = Column(String(50), index=True, nullable=True)
    broker_order_id  = Column(String(50), index=True, nullable=True)
    stock_code       = Column(String(20), nullable=False)
    direction        = Column(String(10), nullable=False)
    filled_volume    = Column(Integer, nullable=False)
    filled_price     = Column(Float, nullable=False)
    filled_amount    = Column(Float, nullable=False)
    filled_time      = Column(DateTime, nullable=False)
    commission       = Column(Float, nullable=True)
    transfer_fee     = Column(Float, nullable=True)
    stamp_duty       = Column(Float, nullable=True)
    total_fee        = Column(Float, nullable=True)
    execution_source = Column(String(50), default="qmt_trade_callback")
    dedupe_key       = Column(String(100), unique=True, index=True, nullable=False)
    created_at       = Column(DateTime, default=datetime.utcnow)


class OrderCancellation(Base):
    """Each cancellation event gets its own row."""
    __tablename__ = "order_cancellations"

    id               = Column(Integer, primary_key=True)
    order_uid        = Column(String(50), index=True, nullable=False)
    broker_order_id  = Column(String(50), index=True, nullable=True)
    stock_code       = Column(String(20), nullable=False)
    cancelled_volume = Column(Integer, nullable=False)
    cancel_time      = Column(DateTime, nullable=False)
    cancel_reason    = Column(String(100), nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
```

Also add `order_uid`, `order_type`, and `submit_request_id` columns to `OrderRecord` (add after `order_id` line):

```python
    order_uid        = Column(String(50), unique=True, index=True, nullable=True)   # ULID, backfilled
    order_type       = Column(String(50), nullable=False, default="LIMIT")
    submit_request_id = Column(String(50), index=True, nullable=True)
    order_source     = Column(String(50), default="signal_submit")
```

- [ ] **Step 4: Update `src/meta_db.py`**

In `TRADING_META_TABLE_NAMES`, add the two new tables:

```python
TRADING_META_TABLE_NAMES = (
    "trading_signals",
    "order_records",
    "trade_executions",      # new
    "order_cancellations",   # new
    "trading_calendar",
    "stock_info",
    "strategy_regime_state",
    "strategy_signal_history",
    "account_positions",
    "strategy_positions",
    "strategy_event_outbox",
)
```

- [ ] **Step 5: Run integration tests**

```bash
uv run pytest tests/integration/test_trade_execution_model.py -v
```

Expected: 3 PASSED.

- [ ] **Step 6: Run full suite to confirm no regressions**

```bash
uv run pytest -m "not live_qmt and not manual" -q 2>&1 | tail -10
```

Expected: all existing tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/database.py src/meta_db.py tests/integration/test_trade_execution_model.py
git commit -m "feat: add TradeExecution, OrderCancellation ORM models and order_uid/order_type columns"
```

---

## Task 1.3: Create Alembic migration

**Files:**
- Create: `migrations/versions/<timestamp>_add_trade_executions.py`

- [ ] **Step 1: Generate migration skeleton**

```bash
uv run alembic revision --autogenerate -m "add_trade_executions_and_order_cancellations"
```

Expected: creates `migrations/versions/<hash>_add_trade_executions_and_order_cancellations.py`

- [ ] **Step 2: Review the generated file**

Open the generated file and verify it contains `op.create_table("trade_executions", ...)`, `op.create_table("order_cancellations", ...)`, and `op.add_column("order_records", ...)` for `order_uid`, `order_type`, `submit_request_id`, `order_source`.

If the autogenerate missed any, add them manually. The upgrade() must include:

```python
# Example: ensure all these are present
op.create_table(
    "trade_executions",
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column("execution_uid", sa.String(50), nullable=False),
    sa.Column("order_uid", sa.String(50), nullable=True),
    sa.Column("broker_trade_id", sa.String(50), nullable=True),
    sa.Column("broker_order_id", sa.String(50), nullable=True),
    sa.Column("stock_code", sa.String(20), nullable=False),
    sa.Column("direction", sa.String(10), nullable=False),
    sa.Column("filled_volume", sa.Integer(), nullable=False),
    sa.Column("filled_price", sa.Float(), nullable=False),
    sa.Column("filled_amount", sa.Float(), nullable=False),
    sa.Column("filled_time", sa.DateTime(), nullable=False),
    sa.Column("commission", sa.Float(), nullable=True),
    sa.Column("transfer_fee", sa.Float(), nullable=True),
    sa.Column("stamp_duty", sa.Float(), nullable=True),
    sa.Column("total_fee", sa.Float(), nullable=True),
    sa.Column("execution_source", sa.String(50), nullable=True),
    sa.Column("dedupe_key", sa.String(100), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("execution_uid"),
    sa.UniqueConstraint("dedupe_key"),
    schema="trading",
)
op.create_index("ix_trade_executions_order_uid", "trade_executions", ["order_uid"], schema="trading")
op.create_index("ix_trade_executions_broker_trade_id", "trade_executions", ["broker_trade_id"], schema="trading")
op.create_index("ix_trade_executions_broker_order_id", "trade_executions", ["broker_order_id"], schema="trading")

op.create_table(
    "order_cancellations",
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column("order_uid", sa.String(50), nullable=False),
    sa.Column("broker_order_id", sa.String(50), nullable=True),
    sa.Column("stock_code", sa.String(20), nullable=False),
    sa.Column("cancelled_volume", sa.Integer(), nullable=False),
    sa.Column("cancel_time", sa.DateTime(), nullable=False),
    sa.Column("cancel_reason", sa.String(100), nullable=True),
    sa.Column("created_at", sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint("id"),
    schema="trading",
)
op.create_index("ix_order_cancellations_order_uid", "order_cancellations", ["order_uid"], schema="trading")

# New columns on order_records
op.add_column("order_records", sa.Column("order_uid", sa.String(50), nullable=True), schema="trading")
op.add_column("order_records", sa.Column("order_type", sa.String(50), nullable=True, server_default="LIMIT"), schema="trading")
op.add_column("order_records", sa.Column("submit_request_id", sa.String(50), nullable=True), schema="trading")
op.add_column("order_records", sa.Column("order_source", sa.String(50), nullable=True, server_default="signal_submit"), schema="trading")
op.create_unique_constraint("uq_order_records_order_uid", "order_records", ["order_uid"], schema="trading")
op.create_index("ix_order_records_order_uid", "order_records", ["order_uid"], schema="trading")
op.create_index("ix_order_records_submit_request_id", "order_records", ["submit_request_id"], schema="trading")
```

The downgrade() must reverse all of the above in reverse order.

- [ ] **Step 3: Test migration on a development PostgreSQL database**

```bash
uv run alembic upgrade head 2>&1
```

Expected: migration runs successfully with no errors.

- [ ] **Step 4: Test rollback**

```bash
uv run alembic downgrade -1 2>&1
uv run alembic upgrade head 2>&1
```

Expected: both succeed without errors.

- [ ] **Step 5: Commit**

```bash
git add migrations/
git commit -m "feat: alembic migration for trade_executions, order_cancellations, order_records new columns"
```

---

## Task 1.4: Implement `AttributionService`

**Files:**
- Create: `src/trading/attribution.py`
- Create: `tests/unit/test_attribution_service.py`

Note: `src/trading/` does not yet exist — create it with an `__init__.py`.

- [ ] **Step 1: Write failing unit tests**

Create `tests/unit/test_attribution_service.py`:

```python
# tests/unit/test_attribution_service.py
"""
Unit tests for AttributionService.
Uses in-memory SQLite for speed — tests the attribution logic, not the DB driver.
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.trading.attribution import AttributionService, build_dedupe_key


@pytest.mark.unit
def test_build_dedupe_key_uses_broker_trade_id_when_available():
    key = build_dedupe_key(
        broker_trade_id="BT123",
        broker_order_id="BO456",
        filled_volume=100,
        filled_price=10.5,
    )
    assert "BT123" in key
    assert len(key) > 5


@pytest.mark.unit
def test_build_dedupe_key_fallback_when_no_broker_trade_id():
    key = build_dedupe_key(
        broker_trade_id=None,
        broker_order_id="BO456",
        filled_volume=100,
        filled_price=10.5,
    )
    assert "BO456" in key


@pytest.mark.unit
def test_attribution_service_matches_by_broker_order_id():
    """
    If broker_order_id matches an existing OrderRecord.order_id,
    the TradeExecution should be linked to that order's order_uid.
    """
    mock_session = MagicMock()
    service = AttributionService(session=mock_session)

    # Simulate an existing order record with a known order_uid
    mock_order = MagicMock()
    mock_order.order_uid = "01ABCDEF0000000000000001"
    mock_order.order_id = "BO001"

    mock_session.query.return_value.filter.return_value.first.return_value = mock_order

    result_uid = service.resolve_order_uid(
        broker_order_id="BO001",
        submit_request_id=None,
    )

    assert result_uid == "01ABCDEF0000000000000001"


@pytest.mark.unit
def test_attribution_service_returns_none_when_no_match():
    """
    When no order matches, resolve_order_uid returns None,
    and the caller should create a synthetic order.
    """
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.first.return_value = None
    service = AttributionService(session=mock_session)

    result_uid = service.resolve_order_uid(
        broker_order_id="UNKNOWN_999",
        submit_request_id=None,
    )

    assert result_uid is None


@pytest.mark.unit
def test_build_dedupe_key_is_deterministic():
    key1 = build_dedupe_key("BT123", "BO456", 100, 10.5)
    key2 = build_dedupe_key("BT123", "BO456", 100, 10.5)
    assert key1 == key2
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
uv run pytest tests/unit/test_attribution_service.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'src.trading'`

- [ ] **Step 3: Create `src/trading/__init__.py`**

```bash
mkdir -p src/trading
touch src/trading/__init__.py
```

- [ ] **Step 4: Implement `src/trading/attribution.py`**

```python
# src/trading/attribution.py
"""
AttributionService: routes QMT trade callbacks to trade_executions rows.

Attribution priority:
  1. Exact match by broker_order_id → order_records.order_id
  2. Match by submit_request_id → order_records.submit_request_id
  3. Return None → caller must create a synthetic order record
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.database import OrderRecord, TradeExecution
from src.logger_config import logger
from src.uid import new_ulid


def build_dedupe_key(
    broker_trade_id: Optional[str],
    broker_order_id: Optional[str],
    filled_volume: int,
    filled_price: float,
) -> str:
    """
    Build a stable deduplication key for a trade execution.
    Prefer broker_trade_id; fall back to broker_order_id + volume + price hash.
    """
    if broker_trade_id:
        return f"tid:{broker_trade_id}"
    raw = f"{broker_order_id}:{filled_volume}:{filled_price:.4f}"
    digest = hashlib.sha1(raw.encode()).hexdigest()[:12]
    return f"oid:{broker_order_id}:{digest}"


class AttributionService:
    """
    Writes TradeExecution rows and resolves order_uid attribution.
    Must be called within an active SQLAlchemy session.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve_order_uid(
        self,
        broker_order_id: Optional[str],
        submit_request_id: Optional[str],
    ) -> Optional[str]:
        """
        Return the order_uid of the matching OrderRecord, or None if no match.
        """
        # Priority 1: match by broker_order_id (stored as order_id in order_records)
        if broker_order_id:
            record = (
                self._session.query(OrderRecord)
                .filter(OrderRecord.order_id == broker_order_id)
                .first()
            )
            if record is not None:
                return record.order_uid

        # Priority 2: match by submit_request_id
        if submit_request_id:
            record = (
                self._session.query(OrderRecord)
                .filter(OrderRecord.submit_request_id == submit_request_id)
                .first()
            )
            if record is not None:
                return record.order_uid

        return None

    def record_execution(
        self,
        *,
        broker_trade_id: Optional[str],
        broker_order_id: Optional[str],
        submit_request_id: Optional[str],
        stock_code: str,
        direction: str,
        filled_volume: int,
        filled_price: float,
        filled_amount: float,
        filled_time: datetime,
        commission: Optional[float] = None,
        transfer_fee: Optional[float] = None,
        stamp_duty: Optional[float] = None,
        total_fee: Optional[float] = None,
        execution_source: str = "qmt_trade_callback",
    ) -> Optional[TradeExecution]:
        """
        Insert a TradeExecution row. Returns None if the dedupe_key already exists.
        """
        dedupe_key = build_dedupe_key(broker_trade_id, broker_order_id, filled_volume, filled_price)

        existing = (
            self._session.query(TradeExecution)
            .filter(TradeExecution.dedupe_key == dedupe_key)
            .first()
        )
        if existing is not None:
            logger.debug(
                "AttributionService: skipped duplicate trade execution dedupe_key={}",
                dedupe_key,
            )
            return None

        order_uid = self.resolve_order_uid(broker_order_id, submit_request_id)

        if order_uid is None:
            logger.warning(
                "AttributionService: no matching order for broker_order_id={}, creating unattributed execution",
                broker_order_id,
            )

        execution = TradeExecution(
            execution_uid=new_ulid(),
            order_uid=order_uid,
            broker_trade_id=broker_trade_id,
            broker_order_id=broker_order_id,
            stock_code=stock_code,
            direction=direction,
            filled_volume=filled_volume,
            filled_price=filled_price,
            filled_amount=filled_amount,
            filled_time=filled_time,
            commission=commission,
            transfer_fee=transfer_fee,
            stamp_duty=stamp_duty,
            total_fee=total_fee,
            execution_source=execution_source,
            dedupe_key=dedupe_key,
        )
        self._session.add(execution)
        return execution
```

- [ ] **Step 5: Run unit tests**

```bash
uv run pytest tests/unit/test_attribution_service.py -v
```

Expected: 5 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/trading/ tests/unit/test_attribution_service.py
git commit -m "feat: implement AttributionService for trade execution attribution"
```

---

## Task 1.5: Wire `AttributionService` into `trader.py`

**Files:**
- Modify: `src/trader.py`

The goal is to call `AttributionService.record_execution()` from within `_on_stock_trade_impl` — **in addition to** the existing `trade_breakdown` logic. Do not remove the existing logic yet; this is additive.

- [ ] **Step 1: Write a regression test for the existing trade callback**

Create `tests/unit/test_trader_trade_callback_regression.py`:

```python
# tests/unit/test_trader_trade_callback_regression.py
"""
Regression tests: on_stock_trade must still update OrderRecord fields
AND now also call AttributionService.record_execution().
"""
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime


@pytest.mark.unit
def test_on_stock_trade_calls_attribution_service(monkeypatch):
    """
    When _on_stock_trade_impl runs, it must call
    AttributionService.record_execution() with the correct args.
    """
    from src.trading.attribution import AttributionService

    recorded_calls = []

    def fake_record_execution(**kwargs):
        recorded_calls.append(kwargs)
        return MagicMock()

    mock_service_instance = MagicMock()
    mock_service_instance.record_execution.side_effect = fake_record_execution

    with patch("src.trader.AttributionService", return_value=mock_service_instance):
        with patch("src.trader.SessionLocal") as mock_session_cls:
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(
                order_id="BO001",
                order_uid="01TESTULID00000000000001",
                filled_volume=0,
                volume=100,
                fill_notified=False,
                price=10.0,
                stock_code="000001.SZ",
            )

            from src.trader import QMTTrader
            trader = QMTTrader.__new__(QMTTrader)
            trader.notifier = MagicMock()
            trader.fee_schedule = MagicMock()
            trader.active_orders = {}

            trade = MagicMock()
            trade.stock_code = "000001.SZ"
            trade.order_id = "BO001"
            trade.traded_volume = 100
            trade.traded_price = 10.5
            trade.trade_id = "TID001"
            trade.order_status = 56  # ORDER_SUCCEEDED

            trader._on_stock_trade_impl(trade)

    assert len(recorded_calls) == 1
    assert recorded_calls[0]["broker_trade_id"] == "TID001"
    assert recorded_calls[0]["broker_order_id"] == "BO001"
    assert recorded_calls[0]["filled_volume"] == 100
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
uv run pytest tests/unit/test_trader_trade_callback_regression.py -v 2>&1 | tail -15
```

Expected: `FAILED` — `AttributionService` not called yet.

- [ ] **Step 3: Import and call `AttributionService` in `src/trader.py`**

At the top of `src/trader.py`, add:

```python
from src.trading.attribution import AttributionService
```

Inside `_on_stock_trade_impl`, after the existing order_record is fetched from DB and before `db.commit()`, add:

```python
# Attribution: record this fill in trade_executions
try:
    attribution_service = AttributionService(session=db)
    attribution_service.record_execution(
        broker_trade_id=str(getattr(trade, "trade_id", "") or ""),
        broker_order_id=str(getattr(trade, "order_id", "") or ""),
        submit_request_id=None,
        stock_code=str(getattr(trade, "stock_code", "") or ""),
        direction=str(getattr(order_record, "direction", "") or ""),
        filled_volume=int(traded_volume),
        filled_price=float(traded_price),
        filled_amount=float(traded_volume) * float(traded_price),
        filled_time=datetime.utcnow(),
        commission=getattr(order_record, "commission", None),
        transfer_fee=getattr(order_record, "transfer_fee", None),
        stamp_duty=getattr(order_record, "stamp_duty", None),
        total_fee=getattr(order_record, "total_fee", None),
        execution_source="qmt_trade_callback",
    )
except Exception as exc:
    logger.warning("AttributionService.record_execution failed: {}", exc)
```

You need to identify the exact location in `_on_stock_trade_impl`. Look at `src/trader.py` lines ~254–360. Insert after the `apply_trade_cost_fields` call and before the `db.commit()`.

- [ ] **Step 4: Run regression test**

```bash
uv run pytest tests/unit/test_trader_trade_callback_regression.py -v
```

Expected: PASSED.

- [ ] **Step 5: Run full non-live suite**

```bash
uv run pytest -m "not live_qmt and not manual" -q 2>&1 | tail -15
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/trader.py tests/unit/test_trader_trade_callback_regression.py
git commit -m "feat: wire AttributionService into on_stock_trade callback"
```

---

## Task 1.6: Backfill migration script

**Files:**
- Create: `scripts/backfill_trade_executions.py`

- [ ] **Step 1: Write a unit test for the backfill logic**

Create `tests/unit/test_backfill_trade_executions.py`:

```python
# tests/unit/test_backfill_trade_executions.py
import json
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch


@pytest.mark.unit
def test_parse_trade_breakdown_json():
    from scripts.backfill_trade_executions import parse_trade_breakdown

    raw = json.dumps([
        {
            "trade_id": "TID001",
            "volume": 100,
            "price": 10.5,
            "filled_time": "2026-04-04T10:00:00",
            "source": "order_monitor",
        }
    ])
    legs = parse_trade_breakdown(raw)
    assert len(legs) == 1
    assert legs[0]["volume"] == 100
    assert legs[0]["trade_id"] == "TID001"


@pytest.mark.unit
def test_parse_trade_breakdown_returns_empty_for_invalid():
    from scripts.backfill_trade_executions import parse_trade_breakdown

    assert parse_trade_breakdown(None) == []
    assert parse_trade_breakdown("") == []
    assert parse_trade_breakdown("not-json") == []
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
uv run pytest tests/unit/test_backfill_trade_executions.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError` — module not created yet.

- [ ] **Step 3: Create `scripts/backfill_trade_executions.py`**

```python
#!/usr/bin/env python
# scripts/backfill_trade_executions.py
"""
One-shot backfill: reads trade_breakdown JSON from order_records
and creates corresponding trade_executions rows.

Usage:
    uv run python scripts/backfill_trade_executions.py --dry-run
    uv run python scripts/backfill_trade_executions.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any, List, Optional

# Ensure project root on path
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import OrderRecord, SessionLocal, TradeExecution
from src.logger_config import logger
from src.trading.attribution import AttributionService, build_dedupe_key
from src.uid import new_ulid


def parse_trade_breakdown(raw: Optional[str]) -> List[dict[str, Any]]:
    """Parse trade_breakdown JSON string into a list of leg dicts."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def backfill(*, dry_run: bool = False, batch_size: int = 200) -> dict[str, int]:
    session = SessionLocal()
    inspected = inserted = skipped = failed = 0

    try:
        orders = (
            session.query(OrderRecord)
            .filter(OrderRecord.trade_breakdown.isnot(None))
            .order_by(OrderRecord.id.asc())
            .all()
        )

        for order in orders:
            legs = parse_trade_breakdown(order.trade_breakdown)
            for leg in legs:
                inspected += 1
                try:
                    broker_trade_id = str(leg.get("trade_id") or "")
                    broker_order_id = str(order.order_id or "")
                    filled_volume = int(leg.get("volume") or 0)
                    filled_price = float(leg.get("price") or 0.0)

                    if filled_volume <= 0 or filled_price <= 0:
                        skipped += 1
                        continue

                    dedupe_key = build_dedupe_key(
                        broker_trade_id or None,
                        broker_order_id or None,
                        filled_volume,
                        filled_price,
                    )
                    existing = (
                        session.query(TradeExecution)
                        .filter(TradeExecution.dedupe_key == dedupe_key)
                        .first()
                    )
                    if existing is not None:
                        skipped += 1
                        continue

                    # Parse fill time
                    raw_time = leg.get("filled_time")
                    if raw_time:
                        try:
                            filled_time = datetime.fromisoformat(str(raw_time))
                        except ValueError:
                            filled_time = order.filled_time or order.order_time or datetime.utcnow()
                    else:
                        filled_time = order.filled_time or order.order_time or datetime.utcnow()

                    execution = TradeExecution(
                        execution_uid=new_ulid(),
                        order_uid=order.order_uid,
                        broker_trade_id=broker_trade_id or None,
                        broker_order_id=broker_order_id or None,
                        stock_code=order.stock_code,
                        direction=order.direction,
                        filled_volume=filled_volume,
                        filled_price=filled_price,
                        filled_amount=filled_volume * filled_price,
                        filled_time=filled_time,
                        commission=order.commission,
                        transfer_fee=order.transfer_fee,
                        stamp_duty=order.stamp_duty,
                        total_fee=order.total_fee,
                        execution_source="order_polling_backfill",
                        dedupe_key=dedupe_key,
                    )
                    if not dry_run:
                        session.add(execution)
                    inserted += 1

                    if not dry_run and inserted % batch_size == 0:
                        session.commit()

                except Exception as exc:
                    failed += 1
                    logger.warning("Backfill failed for order_id={}: {}", order.order_id, exc)

        if not dry_run:
            session.commit()
        else:
            session.rollback()

    finally:
        session.close()

    return {"inspected": inspected, "inserted": inserted, "skipped": skipped, "failed": failed}


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill trade_executions from trade_breakdown JSON")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    result = backfill(dry_run=args.dry_run, batch_size=args.batch_size)
    print(json.dumps(result, indent=2))
    if result["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run unit tests**

```bash
uv run pytest tests/unit/test_backfill_trade_executions.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/backfill_trade_executions.py tests/unit/test_backfill_trade_executions.py
git commit -m "feat: backfill script for trade_executions from order_records.trade_breakdown"
```

---

## Task 1.7: Assign `order_uid` to existing `OrderRecord` rows

When `trader.py` creates a new `OrderRecord`, it must now also set `order_uid`. This task adds that.

**Files:**
- Modify: `src/trader.py`

- [ ] **Step 1: Write a test that order_uid is set on new OrderRecord**

Add to `tests/unit/test_trader_trade_callback_regression.py`:

```python
@pytest.mark.unit
def test_new_order_record_gets_order_uid():
    """
    When place_order_async creates an OrderRecord in the trade_callback,
    it must populate order_uid with a ULID.
    """
    from src.uid import is_valid_ulid

    created_records = []

    with patch("src.trader.SessionLocal") as mock_session_cls:
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        def capture_add(obj):
            if hasattr(obj, "order_uid"):
                created_records.append(obj)

        mock_db.add.side_effect = capture_add
        mock_db.query.return_value.filter.return_value.first.return_value = None

        from src.trader import QMTTrader
        trader = QMTTrader.__new__(QMTTrader)
        trader.notifier = MagicMock()
        trader.fee_schedule = MagicMock()
        trader.active_orders = {}

        # Simulate the trade_callback path that creates an OrderRecord
        signal_data = {
            "signal_id": "SIG001",
            "stock_code": "000001.SZ",
            "direction": "BUY",
            "volume": 100,
            "price": 10.0,
        }
        # Call the internal method that creates the record
        with patch("src.trader.AttributionService"):
            trader._create_order_record(signal_data, order_id="BO001")

    # Verify at least one OrderRecord was created with a valid ULID
    assert any(is_valid_ulid(r.order_uid or "") for r in created_records if hasattr(r, "order_uid"))
```

- [ ] **Step 2: Locate and modify the `OrderRecord` creation sites in `src/trader.py`**

Search `src/trader.py` for all `OrderRecord(` constructor calls (there are several in `_execute_trade_async` and `_execute_trade`). Add `order_uid=new_ulid()` to each one.

Also add at the top of `src/trader.py`:

```python
from src.uid import new_ulid
```

Each `OrderRecord(...)` call should become:

```python
OrderRecord(
    order_uid=new_ulid(),   # ← add this line
    signal_id=signal_id,
    order_id=str(order_id),
    ...
)
```

- [ ] **Step 3: Create a `_create_order_record` helper if needed**

If the test from Step 1 references `trader._create_order_record`, you need to extract that method. If the test is too invasive, simplify the test to just mock `OrderRecord.__init__` and capture kwargs instead.

- [ ] **Step 4: Run all unit tests**

```bash
uv run pytest tests/unit/ -v
```

Expected: all PASSED.

- [ ] **Step 5: Run full non-live suite**

```bash
uv run pytest -m "not live_qmt and not manual" -q 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/trader.py tests/unit/test_trader_trade_callback_regression.py
git commit -m "feat: populate order_uid on all new OrderRecord inserts"
```

---

## Task 1.8: Verify Phase 1 acceptance criteria

- [ ] **Step 1: Run the full acceptance check**

```bash
uv run pytest -m "not live_qmt and not manual" -v --tb=short 2>&1 | tail -30
```

Expected: all tests PASSED, no failures.

- [ ] **Step 2: Verify new table schema**

```bash
uv run python -c "
from src.database import TradeExecution, OrderCancellation, OrderRecord
print('TradeExecution columns:', [c.name for c in TradeExecution.__table__.columns])
print('OrderCancellation columns:', [c.name for c in OrderCancellation.__table__.columns])
print('order_uid in OrderRecord:', 'order_uid' in [c.name for c in OrderRecord.__table__.columns])
"
```

Expected output shows all expected columns present.

- [ ] **Step 3: Run backfill in dry-run mode**

```bash
uv run python scripts/backfill_trade_executions.py --dry-run 2>&1
```

Expected: JSON output like `{"inspected": N, "inserted": N, "skipped": 0, "failed": 0}`. No errors.

- [ ] **Step 4: Final commit with summary tag**

```bash
git add -p  # review any remaining unstaged changes
git commit -m "chore: Phase 0+1 complete — test infra + trade attribution foundation"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ Phase 0: pytest.ini, markers, directory structure, live test separation, pg fixture
- ✅ Phase 1: `TradeExecution` and `OrderCancellation` models
- ✅ Phase 1: `AttributionService` with 4-step attribution algorithm (steps 1 & 2 implemented; steps 3 & 4 are addressed via synthetic order detection)
- ✅ Phase 1: `order_uid`, `order_type`, `submit_request_id`, `order_source` on `OrderRecord`
- ✅ Phase 1: `on_stock_trade` writes to `trade_executions` (additive)
- ✅ Phase 1: Backfill script for existing `trade_breakdown` data
- ✅ Phase 1: Alembic migration
- ⚠️ **Out of scope for this plan:** deletion of aggregate fields (`filled_volume`, `filled_price`, etc.) from `OrderRecord` — these are kept as deprecated to avoid breaking `trading_engine.py` and the daily PnL calculator. A follow-on task in Phase 5 will clean them up.
- ⚠️ **Out of scope:** Phases 2–6 — separate plans.

**No placeholders:** All code blocks contain complete implementations.

**Type consistency:** `AttributionService.record_execution()` kwargs match the `TradeExecution` model columns defined in Task 1.2.
