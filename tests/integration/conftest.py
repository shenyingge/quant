# tests/integration/conftest.py
"""
Integration test conftest - provides cleanup for ORM tests that write
to the real trading schema (since ORM models use explicit schema qualifiers
that bypass the pg_session fixture's search_path isolation).
"""
import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True)
def cleanup_integration_orm_rows(pg_engine):
    """
    Auto-cleanup for rows inserted into the trading schema by ORM tests.
    Runs after every integration test to remove test data.
    """
    yield
    try:
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM trading.trade_executions WHERE execution_uid LIKE '01JRF6Z%'"))
            conn.execute(text("DELETE FROM trading.order_cancellations WHERE order_uid LIKE '01JRF6Z%'"))
    except Exception:
        pass
