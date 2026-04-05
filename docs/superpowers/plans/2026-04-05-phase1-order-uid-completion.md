# Phase 1 Order UID Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every production-created `OrderRecord` gets a valid ULID `order_uid`, then finish the remaining Phase 1 acceptance checks.

**Architecture:** Generate `order_uid` exactly where new `OrderRecord` instances are constructed. Keep the trade-callback fallback in `QMTCallback._create_order_record_from_trade()` explicit, and add a single `TradingEngine` helper so the synchronous submit path, asynchronous submit path, and both failure branches all share one ULID-populating builder.

**Tech Stack:** Python, SQLAlchemy ORM, pytest, uv, QMT runtime code

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/trader.py` | Modify | Populate `order_uid` for synthetic `OrderRecord` rows created from unmatched trade callbacks. |
| `tests/unit/test_trader_trade_callback_regression.py` | Modify | Lock the trade-callback fallback behavior with a targeted ULID regression test. |
| `src/trading_engine.py` | Modify | Centralize production `OrderRecord` creation behind one helper that always sets `order_uid`. |
| `tests/unit/test_trading_engine_order_uid.py` | Create | Verify sync submit, sync failure, async submit, and async failure insert paths all write valid ULIDs. |

## Scope Notes

- The old progress note only called out `src/trader.py`, but the current codebase also creates production `OrderRecord` rows in `src/trading_engine.py`. This plan covers both so Phase 1 actually finishes the intended `order_uid` rollout.
- Do not touch test-only factory helpers unless a failing test proves they now need `order_uid`. The requirement is production insert paths.

### Task 1: Cover the trade-callback fallback path

**Files:**
- Modify: `tests/unit/test_trader_trade_callback_regression.py`
- Modify: `src/trader.py`
- Test: `tests/unit/test_trader_trade_callback_regression.py`

- [ ] **Step 1: Write the failing regression test**

Add to `tests/unit/test_trader_trade_callback_regression.py`:

```python
@pytest.mark.unit
def test_create_order_record_from_trade_populates_order_uid():
    from src.trader import QMTCallback
    from src.uid import is_valid_ulid

    callback = QMTCallback.__new__(QMTCallback)
    callback._extract_trade_timestamp = MagicMock(
        return_value=datetime(2026, 4, 4, 10, 30, 0)
    )
    callback._infer_signal_id_from_active_orders = MagicMock(
        return_value="SIG-CALLBACK-1"
    )
    callback._infer_trade_direction = MagicMock(return_value="BUY")
    callback._build_trade_order_id = MagicMock(return_value="BO-CALLBACK-1")
    callback._append_trade_leg_to_order_record = MagicMock()
    callback._apply_trade_costs_to_order_record = MagicMock()

    order_record = callback._create_order_record_from_trade(
        trade=MagicMock(),
        stock_code="000001.SZ",
        raw_order_id="BO-CALLBACK-1",
        trade_id="TID-CALLBACK-1",
        traded_volume=100,
        traded_price=10.5,
    )

    assert order_record.order_uid is not None
    assert is_valid_ulid(order_record.order_uid)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/unit/test_trader_trade_callback_regression.py -k order_uid -v
```

Expected: FAIL on `assert order_record.order_uid is not None` because the synthetic callback-created row still leaves `order_uid` empty.

- [ ] **Step 3: Write the minimal implementation**

Update `src/trader.py`:

```python
from src.uid import new_ulid
```

and in `QMTCallback._create_order_record_from_trade()` change the constructor to:

```python
order_record = OrderRecord(
    signal_id=signal_id,
    order_uid=new_ulid(),
    order_id=order_id,
    stock_code=stock_code,
    direction=direction,
    volume=int(traded_volume or 0),
    price=float(traded_price or 0.0),
    order_status="FILLED",
    order_time=filled_time,
    filled_price=0.0,
    filled_volume=0,
    filled_time=None,
    fill_notified=False,
    error_message="Created from QMT trade callback without a matching order record",
)
```

- [ ] **Step 4: Run the regression file to verify it passes**

Run:

```bash
uv run pytest tests/unit/test_trader_trade_callback_regression.py -v
```

Expected: PASS with 3 passing tests in this file.

- [ ] **Step 5: Commit**

```bash
git add src/trader.py tests/unit/test_trader_trade_callback_regression.py
git commit -m "feat: assign order_uid to callback-created order records" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Cover every `TradingEngine` insert path

**Files:**
- Create: `tests/unit/test_trading_engine_order_uid.py`
- Modify: `src/trading_engine.py`
- Test: `tests/unit/test_trading_engine_order_uid.py`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/unit/test_trading_engine_order_uid.py`:

```python
from types import SimpleNamespace

import pytest

from src.database import OrderRecord, TradingSignal
from src.trading_engine import TradingEngine
from src.uid import is_valid_ulid


class DummyNotifier:
    def __init__(self):
        self.placed = []
        self.errors = []

    def notify_order_placed(self, signal_data, order_id):
        self.placed.append((signal_data["signal_id"], order_id))
        return True

    def notify_error(self, error_message, context=""):
        self.errors.append((error_message, context))
        return True


class DummyQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class DummySession:
    def __init__(self, signal_record=None, existing_order=None):
        self.signal_record = signal_record
        self.existing_order = existing_order
        self.added = []
        self.commit_count = 0
        self.closed = False

    def query(self, model):
        if model is TradingSignal:
            return DummyQuery(self.signal_record)
        if model is OrderRecord:
            return DummyQuery(self.existing_order)
        return DummyQuery(None)

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        raise AssertionError("rollback should not be called in this test")

    def close(self):
        self.closed = True


def make_engine():
    engine = TradingEngine.__new__(TradingEngine)
    engine.notifier = DummyNotifier()
    return engine


@pytest.mark.unit
@pytest.mark.parametrize(
    ("place_order_result", "expected_status"),
    [("BO-SYNC-1", "PENDING"), (None, "FAILED")],
)
def test_execute_trade_assigns_order_uid(place_order_result, expected_status):
    engine = make_engine()
    engine.trader = SimpleNamespace(
        place_order=lambda signal_data: place_order_result
    )
    session = DummySession()
    signal_data = {
        "signal_id": "SIG-SYNC-1",
        "stock_code": "000001.SZ",
        "direction": "BUY",
        "volume": 100,
        "price": 10.5,
    }

    engine._execute_trade(signal_data, session)

    assert len(session.added) == 1
    order_record = session.added[0]
    assert order_record.order_status == expected_status
    assert order_record.order_uid is not None
    assert is_valid_ulid(order_record.order_uid)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("callback_order_id", "callback_error", "expected_status"),
    [("BO-ASYNC-1", None, "PENDING"), (None, "broker rejected", "FAILED")],
)
def test_execute_trade_async_assigns_order_uid(
    monkeypatch, callback_order_id, callback_error, expected_status
):
    engine = make_engine()
    signal_record = SimpleNamespace(processed=False, error_message=None)
    session = DummySession(signal_record=signal_record, existing_order=None)
    monkeypatch.setattr("src.trading_engine.SessionLocal", lambda: session)

    def fake_place_order_async(signal_data, callback):
        callback(callback_order_id, callback_error)

    engine.trader = SimpleNamespace(place_order_async=fake_place_order_async)
    signal_data = {
        "signal_id": "SIG-ASYNC-1",
        "stock_code": "000001.SZ",
        "direction": "BUY",
        "volume": 100,
        "price": 10.5,
    }

    engine._execute_trade_async(signal_data, signal_record)

    assert len(session.added) == 1
    order_record = session.added[0]
    assert order_record.order_status == expected_status
    assert order_record.order_uid is not None
    assert is_valid_ulid(order_record.order_uid)
```

- [ ] **Step 2: Run the file to verify it fails**

Run:

```bash
uv run pytest tests/unit/test_trading_engine_order_uid.py -v
```

Expected: FAIL on the `order_uid` assertions in both parametrized tests because each `TradingEngine` insert path still builds rows without a ULID.

- [ ] **Step 3: Write the minimal implementation**

Update the imports in `src/trading_engine.py`:

```python
from src.uid import new_ulid
```

Add this helper near the other private methods on `TradingEngine`:

```python
def _build_order_record(
    self,
    *,
    signal_id: str,
    order_id: str,
    stock_code: str,
    direction: str,
    volume: int,
    price: Optional[float],
    order_status: str,
    error_message: Optional[str] = None,
) -> OrderRecord:
    return OrderRecord(
        signal_id=signal_id,
        order_uid=new_ulid(),
        order_id=order_id,
        stock_code=stock_code,
        direction=direction,
        volume=volume,
        price=price,
        order_status=order_status,
        error_message=error_message,
    )
```

Replace the four inline constructors in `_execute_trade()` and `_execute_trade_async()` with the helper:

```python
order_record = self._build_order_record(
    signal_id=signal_data["signal_id"],
    order_id=order_id,
    stock_code=signal_data["stock_code"],
    direction=signal_data["direction"],
    volume=signal_data["volume"],
    price=signal_data.get("price"),
    order_status="PENDING",
)
```

```python
order_record = self._build_order_record(
    signal_id=signal_data["signal_id"],
    order_id=f"FAILED_{int(time.time())}",
    stock_code=signal_data["stock_code"],
    direction=signal_data["direction"],
    volume=signal_data["volume"],
    price=signal_data.get("price"),
    order_status="FAILED",
    error_message="委托失败",
)
```

```python
order_record = self._build_order_record(
    signal_id=signal_id,
    order_id=str(order_id),
    stock_code=signal_data["stock_code"],
    direction=signal_data["direction"],
    volume=signal_data["volume"],
    price=signal_data.get("price"),
    order_status="PENDING",
)
```

```python
order_record = self._build_order_record(
    signal_id=signal_id,
    order_id=f"FAILED_{int(time.time())}_{signal_id}",
    stock_code=signal_data["stock_code"],
    direction=signal_data["direction"],
    volume=signal_data["volume"],
    price=signal_data.get("price"),
    order_status="FAILED",
    error_message=str(error) if error else "异步委托失败",
)
```

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```bash
uv run pytest tests/unit/test_trading_engine_order_uid.py -v
```

Expected: PASS with 4 passing tests in this file.

- [ ] **Step 5: Run the combined regression slice**

Run:

```bash
uv run pytest tests/unit/test_trader_trade_callback_regression.py tests/unit/test_trading_engine_order_uid.py -v
```

Expected: PASS with 7 passing tests across both files.

- [ ] **Step 6: Commit**

```bash
git add src/trading_engine.py tests/unit/test_trading_engine_order_uid.py
git commit -m "feat: assign order_uid on trading engine order inserts" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Run Phase 1 acceptance checks

**Files:**
- Test: `tests/unit/test_trader_trade_callback_regression.py`
- Test: `tests/unit/test_trading_engine_order_uid.py`
- Test: `tests/unit/test_uid.py`
- Test: `tests/unit/test_attribution_service.py`
- Test: `tests/integration/test_trade_execution_model.py`
- Test: `tests/unit/test_backfill_trade_executions.py`
- Verify runtime script: `scripts/backfill_trade_executions.py`
- Verify ORM schema: `src/database.py`

- [ ] **Step 1: Run the non-live test suite for Phase 1**

Run:

```bash
uv run pytest -m "not live_qmt and not manual" -v --tb=short
```

Expected: PASS with no failed tests.

- [ ] **Step 2: Verify the ORM schema still exposes the new Phase 1 fields**

Run:

```bash
uv run python -c "from src.database import TradeExecution, OrderCancellation, OrderRecord; print('TradeExecution columns:', [c.name for c in TradeExecution.__table__.columns]); print('OrderCancellation columns:', [c.name for c in OrderCancellation.__table__.columns]); print('OrderRecord columns:', [c.name for c in OrderRecord.__table__.columns]); print('order_uid present:', 'order_uid' in [c.name for c in OrderRecord.__table__.columns])"
```

Expected: Output lists the `trade_executions` and `order_cancellations` fields and ends with `order_uid present: True`.

- [ ] **Step 3: Run the backfill script in dry-run mode**

Run:

```bash
uv run python scripts/backfill_trade_executions.py --dry-run
```

Expected: JSON output with integer `inspected`, `inserted`, `skipped`, and `failed` keys, and `failed` equal to `0`.

- [ ] **Step 4: Commit only if this task required code changes**

If acceptance exposed an implementation issue and you had to patch code, commit that fix with:

```bash
git add <exact files you changed>
git commit -m "fix: resolve phase 1 acceptance regression" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

If all acceptance steps pass without new edits, do not create an extra commit for this task.

---

## Self-Review

1. **Spec coverage:** The remaining work from `docs/superpowers/progress-2026-04-05.md` is Task 1.7 (`order_uid` population) and Task 1.8 (acceptance). This plan covers the callback fallback path, the additional `TradingEngine` production insert paths discovered during review, and the acceptance commands already called out by the progress note.
2. **Placeholder scan:** No `TODO`, `TBD`, or “similar to above” instructions remain. Every code-changing step includes concrete code or exact commands.
3. **Type consistency:** The plan uses the existing `order_uid: String(50)` field on `OrderRecord`, reuses `new_ulid()` / `is_valid_ulid()` from `src.uid`, and keeps `TradingEngine` signatures aligned with the current `signal_data` dict shape and callback arguments.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-05-phase1-order-uid-completion.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
