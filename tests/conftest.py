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
