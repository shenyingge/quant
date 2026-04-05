"""Test database module migration maintains backward compatibility."""

import pytest


def test_database_import_backward_compatibility():
    """Old import path still works."""
    from src.database import Base, OrderRecord, TradeExecution
    assert Base is not None
    assert OrderRecord is not None
    assert TradeExecution is not None


def test_new_infrastructure_db_imports():
    """New infrastructure.db path works."""
    from src.infrastructure.db.models import Base, OrderRecord, TradeExecution
    assert Base is not None
    assert OrderRecord is not None
    assert TradeExecution is not None


def test_models_identical_in_both_paths():
    """Models from both paths reference same class."""
    from src.database import OrderRecord as OldOrderRecord
    from src.infrastructure.db.models import OrderRecord as NewOrderRecord
    assert OldOrderRecord is NewOrderRecord


def test_import_database_session():
    """Database session utilities can be imported."""
    from src.infrastructure.db.session import get_db_session, SessionLocal
    assert get_db_session is not None
    assert SessionLocal is not None


def test_backward_compat_session_import():
    """Session imports work from old path too."""
    from src.database import get_db_session, SessionLocal
    assert get_db_session is not None
    assert SessionLocal is not None
