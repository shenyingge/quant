"""
pytest 配置文件
"""

import os
import sys

import pytest

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.fixture
def sample_signal_data():
    """测试用的交易信号数据"""
    return {
        "signal_id": "TEST_001",
        "stock_code": "000001",
        "direction": "BUY",
        "volume": 100,
        "price": 10.50,
    }


@pytest.fixture
def multiple_signal_data():
    """多个测试信号"""
    return [
        {
            "signal_id": "TEST_001",
            "stock_code": "000001",
            "direction": "BUY",
            "volume": 100,
            "price": 10.50,
        },
        {
            "signal_id": "TEST_002",
            "stock_code": "600000",
            "direction": "SELL",
            "volume": 200,
            "price": 8.20,
        },
        {
            "signal_id": "TEST_003",
            "stock_code": "300001",
            "direction": "BUY",
            "volume": 300,
            "price": 15.30,
        },
    ]


@pytest.fixture
def redis_config():
    """Redis配置"""
    return {"host": "localhost", "port": 6379, "password": None, "db": 0}


import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def _pg_test_url() -> str:
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
    """
    import uuid
    from sqlalchemy import MetaData
    from src.database import Base

    schema = f"test_{uuid.uuid4().hex[:8]}"

    with pg_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    test_metadata = MetaData(schema=schema)
    for table in Base.metadata.tables.values():
        table.to_metadata(test_metadata, schema=schema)

    with pg_engine.begin() as conn:
        test_metadata.create_all(conn)

    Session = sessionmaker(bind=pg_engine)
    session = Session()
    session.execute(text(f'SET search_path TO "{schema}"'))

    yield session

    session.close()
    with pg_engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
