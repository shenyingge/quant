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
