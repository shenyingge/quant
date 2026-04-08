"""测试策略配置加载器。"""

import tempfile
from pathlib import Path

import pytest
import yaml

from src.strategy.config_loader import get_strategy_config_path, load_t0_strategy_config


def test_load_t0_strategy_config_basic():
    """测试基本配置加载。"""
    config = {
        "strategy_type": "t0",
        "stock_code": "601138.SH",
        "enabled": True,
        "signal_thresholds": {
            "positive_sell": {"min_rise": 1.5, "min_pullback": 0.6},
            "reverse_buy": {"min_drop": 2.0, "min_bounce": 0.5},
        },
        "position_management": {
            "min_hold_minutes": 30,
            "carry": {
                "reverse_sell": {"max_carry_days": 3, "take_profit_after_carry_days": 2}
            },
        },
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config, f)
        config_path = f.name

    try:
        params = load_t0_strategy_config(config_path)
        assert params.t0_positive_sell_min_rise == 1.5
        assert params.t0_positive_sell_min_pullback == 0.6
        assert params.t0_reverse_buy_min_drop == 2.0
        assert params.t0_reverse_buy_min_bounce == 0.5
        assert params.t0_min_hold_minutes == 30
        assert params.t0_reverse_sell_max_carry_days == 3
        assert params.t0_reverse_sell_take_profit_after_carry_days == 2
    finally:
        Path(config_path).unlink()


def test_load_t0_strategy_config_file_not_found():
    """测试配置文件不存在。"""
    with pytest.raises(FileNotFoundError):
        load_t0_strategy_config("nonexistent.yaml")


def test_load_t0_strategy_config_invalid_type():
    """测试无效的策略类型。"""
    config = {"strategy_type": "invalid"}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config, f)
        config_path = f.name

    try:
        with pytest.raises(ValueError, match="Invalid strategy_type"):
            load_t0_strategy_config(config_path)
    finally:
        Path(config_path).unlink()


def test_get_strategy_config_path():
    """测试配置文件路径生成。"""
    path = get_strategy_config_path("601138.SH")
    assert path == Path("configs/strategies/t0_601138_SH.yaml")

    path = get_strategy_config_path("600519.SH", config_dir="/tmp/configs")
    assert path == Path("/tmp/configs/t0_600519_SH.yaml")
