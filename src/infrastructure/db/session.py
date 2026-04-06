"""Database session management (migrated from src/database.py)."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.infrastructure.db.models import Base, TRADING_SCHEMA
from src.infrastructure.db.meta_db import get_meta_db_details, get_meta_db_sync_url

engine = create_engine(get_meta_db_sync_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    """Create all tables and schema."""
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{TRADING_SCHEMA}"'))
        Base.metadata.create_all(bind=connection)
        from src.trading.costs.order_record_costs import ensure_order_record_cost_columns

        ensure_order_record_cost_columns(connection)


def get_database_details():
    """Get database connection details."""
    details = get_meta_db_details()
    details["url"] = get_meta_db_sync_url(hide_password=True)
    return details


def get_db_session():
    """Get a new database session."""
    return SessionLocal()


def get_db():
    """Dependency injection generator for FastAPI-style usage."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
