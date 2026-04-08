"""策略配置加载器。

支持从 YAML 文件加载策略参数，优先级：
1. YAML 配置文件
2. 环境变量
3. 代码默认值
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from src.infrastructure.config import settings
from src.infrastructure.logger_config import configured_logger as logger
from src.strategy.core.params import T0StrategyParams


def load_t0_strategy_config(config_path: str | Path) -> T0StrategyParams:
    """从 YAML 文件加载 T+0 策略配置。

    Args:
        config_path: 配置文件路径

    Returns:
        T0StrategyParams 实例

    Raises:
        FileNotFoundError: 配置文件不存在
        ValueError: 配置格式错误
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Strategy config not found: {config_path}")

    logger.info(f"Loading strategy config from {config_path}")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    if not config:
        raise ValueError(f"Empty config file: {config_path}")

    if config.get("strategy_type") != "t0":
        raise ValueError(f"Invalid strategy_type: {config.get('strategy_type')}, expected 't0'")

    # 提取配置
    signal_thresholds = config.get("signal_thresholds", {})
    position_mgmt = config.get("position_management", {})
    carry_config = position_mgmt.get("carry", {})
    time_windows = config.get("time_windows", {})

    # 构建参数（YAML 优先，环境变量兜底）
    params = T0StrategyParams(
        # 基本信息
        t0_base_position=settings.t0_base_position,
        t0_tactical_position=settings.t0_tactical_position,
        t0_trade_unit=settings.t0_trade_unit,
        t0_max_trade_value=settings.t0_max_trade_value,
        # 费用
        t0_commission_rate=settings.t0_commission_rate,
        t0_min_commission=settings.t0_min_commission,
        t0_transfer_fee_rate=settings.t0_transfer_fee_rate,
        t0_stamp_duty_rate=settings.t0_stamp_duty_rate,
        # 持仓管理
        t0_min_hold_minutes=position_mgmt.get("min_hold_minutes", settings.t0_min_hold_minutes),
        # 时间窗口
        t0_positive_sell_start_time=time_windows.get("positive_sell", {}).get(
            "start", settings.t0_positive_sell_start_time
        ),
        t0_positive_sell_end_time=time_windows.get("positive_sell", {}).get(
            "end", settings.t0_positive_sell_end_time
        ),
        t0_positive_buyback_start_time=time_windows.get("positive_buyback", {}).get(
            "start", settings.t0_positive_buyback_start_time
        ),
        t0_positive_buyback_end_time=time_windows.get("positive_buyback", {}).get(
            "end", settings.t0_positive_buyback_end_time
        ),
        t0_reverse_buy_start_time=time_windows.get("reverse_buy", {}).get(
            "start", settings.t0_reverse_buy_start_time
        ),
        t0_reverse_buy_end_time=time_windows.get("reverse_buy", {}).get(
            "end", settings.t0_reverse_buy_end_time
        ),
        t0_reverse_sell_start_time=time_windows.get("reverse_sell", {}).get(
            "start", settings.t0_reverse_sell_start_time
        ),
        t0_reverse_sell_end_time=time_windows.get("reverse_sell", {}).get(
            "end", settings.t0_reverse_sell_end_time
        ),
        # 正T信号阈值
        t0_positive_sell_min_rise=signal_thresholds.get("positive_sell", {}).get(
            "min_rise", settings.t0_positive_sell_min_rise
        ),
        t0_positive_sell_min_pullback=signal_thresholds.get("positive_sell", {}).get(
            "min_pullback", settings.t0_positive_sell_min_pullback
        ),
        t0_positive_sell_gap_down_limit=signal_thresholds.get("positive_sell", {}).get(
            "gap_down_limit", settings.t0_positive_sell_gap_down_limit
        ),
        # 反T信号阈值
        t0_reverse_buy_min_drop=signal_thresholds.get("reverse_buy", {}).get(
            "min_drop", settings.t0_reverse_buy_min_drop
        ),
        t0_reverse_buy_min_bounce=signal_thresholds.get("reverse_buy", {}).get(
            "min_bounce", settings.t0_reverse_buy_min_bounce
        ),
        t0_reverse_sell_min_profit=signal_thresholds.get("reverse_sell", {}).get(
            "min_profit", settings.t0_reverse_sell_min_profit
        ),
        t0_reverse_sell_max_vwap_distance=signal_thresholds.get("reverse_sell", {}).get(
            "max_vwap_distance", settings.t0_reverse_sell_max_vwap_distance
        ),
        # 跨日持仓
        t0_positive_buyback_max_carry_days=carry_config.get("positive_buyback", {}).get(
            "max_carry_days", settings.t0_positive_buyback_max_carry_days
        ),
        t0_positive_buyback_stop_loss_pct=carry_config.get("positive_buyback", {}).get(
            "stop_loss_pct", settings.t0_positive_buyback_stop_loss_pct
        ),
        t0_reverse_sell_max_carry_days=carry_config.get("reverse_sell", {}).get(
            "max_carry_days", settings.t0_reverse_sell_max_carry_days
        ),
        t0_reverse_sell_stop_loss_pct=carry_config.get("reverse_sell", {}).get(
            "stop_loss_pct", settings.t0_reverse_sell_stop_loss_pct
        ),
        t0_reverse_sell_take_profit_after_carry_days=carry_config.get("reverse_sell", {}).get(
            "take_profit_after_carry_days", settings.t0_reverse_sell_take_profit_after_carry_days
        ),
    )

    logger.info(f"Loaded strategy config: stock_code={config.get('stock_code')}, enabled={config.get('enabled')}")
    return params


def get_strategy_config_path(stock_code: str, config_dir: str | Path = "configs/strategies") -> Path:
    """获取策略配置文件路径。

    Args:
        stock_code: 股票代码（如 601138.SH）
        config_dir: 配置目录

    Returns:
        配置文件路径
    """
    config_dir = Path(config_dir)
    # 移除股票代码中的点号，如 601138.SH -> 601138_SH
    safe_code = stock_code.replace(".", "_")
    return config_dir / f"t0_{safe_code}.yaml"
