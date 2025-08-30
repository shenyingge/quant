#!/usr/bin/env python
"""
Broker工厂类和配置管理
统一创建和管理不同类型的Broker实例
"""
import logging
import os
from enum import Enum
from typing import Dict, Optional, Type, Union

from .base_broker import BaseBroker

# 条件导入Broker实现
try:
    from .backtrader_broker import BackTraderBroker

    BACKTRADER_AVAILABLE = True
except ImportError:
    BackTraderBroker = None
    BACKTRADER_AVAILABLE = False

try:
    from .miniqmt_live_broker import MiniQMTLiveBroker
    from .miniqmt_sim_broker import MiniQMTSimBroker

    QMT_AVAILABLE = True
except ImportError:
    MiniQMTLiveBroker = None
    MiniQMTSimBroker = None
    QMT_AVAILABLE = False


class BrokerType(Enum):
    """Broker类型枚举"""

    BACKTRADER = "backtrader"  # BackTrader回测
    QMT_LIVE = "qmt_live"  # QMT实盘交易
    QMT_SIM = "qmt_sim"  # QMT模拟交易


class BrokerFactory:
    """
    Broker工厂类
    根据配置创建相应的Broker实例
    """

    # 动态构建Broker类映射
    _broker_classes = {}

    @classmethod
    def _init_broker_classes(cls):
        """初始化Broker类映射"""
        if cls._broker_classes:
            return  # 已经初始化

        if BACKTRADER_AVAILABLE and BackTraderBroker:
            cls._broker_classes[BrokerType.BACKTRADER] = BackTraderBroker

        if QMT_AVAILABLE and MiniQMTLiveBroker:
            cls._broker_classes[BrokerType.QMT_LIVE] = MiniQMTLiveBroker

        if QMT_AVAILABLE and MiniQMTSimBroker:
            cls._broker_classes[BrokerType.QMT_SIM] = MiniQMTSimBroker

    @classmethod
    def create_broker(
        cls, broker_type: Union[str, BrokerType], config: Optional[Dict] = None, **kwargs
    ) -> BaseBroker:
        """
        创建Broker实例

        Args:
            broker_type: Broker类型
            config: 配置字典
            **kwargs: 额外的配置参数，会覆盖config中的同名参数

        Returns:
            BaseBroker: Broker实例

        Raises:
            ValueError: 不支持的Broker类型
            ImportError: 缺少必要的依赖
        """
        # 初始化Broker类映射
        cls._init_broker_classes()

        if isinstance(broker_type, str):
            try:
                broker_type = BrokerType(broker_type)
            except ValueError:
                raise ValueError(f"Unsupported broker type: {broker_type}")

        if broker_type not in cls._broker_classes:
            if broker_type == BrokerType.BACKTRADER and not BACKTRADER_AVAILABLE:
                raise ImportError(
                    "BackTrader not available. Please install with: pip install backtrader"
                )
            elif broker_type in [BrokerType.QMT_LIVE, BrokerType.QMT_SIM] and not QMT_AVAILABLE:
                raise ImportError("xtquant not available. Please install xtquant SDK")
            else:
                raise ValueError(f"Broker type {broker_type} not registered")

        # 合并配置
        final_config = config.copy() if config else {}
        final_config.update(kwargs)

        # 创建Broker实例
        broker_class = cls._broker_classes[broker_type]

        try:
            return broker_class(final_config)
        except ImportError as e:
            raise ImportError(f"Failed to create {broker_type.value} broker: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to create {broker_type.value} broker: {e}")

    @classmethod
    def create_from_config_file(cls, config_file: str, section: str = "broker") -> BaseBroker:
        """
        从配置文件创建Broker实例

        Args:
            config_file: 配置文件路径
            section: 配置文件中的section名称

        Returns:
            BaseBroker: Broker实例
        """
        import configparser

        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")

        config = configparser.ConfigParser()
        config.read(config_file, encoding="utf-8")

        if section not in config:
            raise ValueError(f"Section '{section}' not found in config file")

        section_config = dict(config[section])
        broker_type = section_config.pop("type", "backtrader")

        return cls.create_broker(broker_type, section_config)

    @classmethod
    def create_from_env(cls, prefix: str = "BROKER_") -> BaseBroker:
        """
        从环境变量创建Broker实例

        Args:
            prefix: 环境变量前缀

        Returns:
            BaseBroker: Broker实例
        """
        config = {}

        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix) :].lower()
                config[config_key] = value

        broker_type = config.pop("type", "backtrader")
        return cls.create_broker(broker_type, config)

    @classmethod
    def register_broker_class(cls, broker_type: BrokerType, broker_class: Type[BaseBroker]):
        """
        注册新的Broker类

        Args:
            broker_type: Broker类型
            broker_class: Broker类
        """
        cls._broker_classes[broker_type] = broker_class

    @classmethod
    def get_supported_types(cls) -> list[str]:
        """
        获取支持的Broker类型列表

        Returns:
            List[str]: 支持的Broker类型列表
        """
        cls._init_broker_classes()
        return [broker_type.value for broker_type in cls._broker_classes.keys()]


class BrokerConfig:
    """
    Broker配置管理类
    提供常用的配置模板和验证
    """

    @staticmethod
    def get_backtrader_config(
        cash: float = 100000, commission: float = 0.001, slip_perc: float = 0.0, **kwargs
    ) -> Dict:
        """
        获取BackTrader配置模板

        Args:
            cash: 初始资金
            commission: 手续费率
            slip_perc: 滑点百分比
            **kwargs: 其他参数

        Returns:
            Dict: BackTrader配置
        """
        config = {
            "cash": cash,
            "commission": commission,
            "slip_perc": slip_perc,
            "slip_fixed": 0.0,
            "slip_open": False,
            "slip_match": False,
        }
        config.update(kwargs)
        return config

    @staticmethod
    def get_qmt_live_config(
        session_id: int, account_id: str, account_type: str = "STOCK", qmt_path: str = "", **kwargs
    ) -> Dict:
        """
        获取QMT实盘配置模板

        Args:
            session_id: QMT会话ID
            account_id: 资金账号
            account_type: 账户类型
            qmt_path: QMT路径
            **kwargs: 其他参数

        Returns:
            Dict: QMT实盘配置
        """
        config = {
            "session_id": session_id,
            "account_id": account_id,
            "account_type": account_type,
            "qmt_path": qmt_path,
        }
        config.update(kwargs)
        return config

    @staticmethod
    def get_qmt_sim_config(
        session_id: int,
        account_id: str,
        initial_cash: float = 1000000,
        commission_rate: float = 0.0003,
        slippage: float = 0.001,
        account_type: str = "STOCK",
        qmt_path: str = "",
        sim_24h_trading: bool = False,
        **kwargs,
    ) -> Dict:
        """
        获取QMT模拟配置模板

        Args:
            session_id: QMT会话ID
            account_id: 模拟账号
            initial_cash: 初始资金
            commission_rate: 手续费率
            slippage: 滑点
            account_type: 账户类型
            qmt_path: QMT路径
            sim_24h_trading: 是否支持24小时交易
            **kwargs: 其他参数

        Returns:
            Dict: QMT模拟配置
        """
        config = {
            "session_id": session_id,
            "account_id": account_id,
            "account_type": account_type,
            "qmt_path": qmt_path,
            "initial_cash": initial_cash,
            "commission_rate": commission_rate,
            "slippage": slippage,
            "sim_24h_trading": sim_24h_trading,
        }
        config.update(kwargs)
        return config

    @staticmethod
    def validate_config(broker_type: Union[str, BrokerType], config: Dict) -> bool:
        """
        验证配置是否完整

        Args:
            broker_type: Broker类型
            config: 配置字典

        Returns:
            bool: 配置是否有效

        Raises:
            ValueError: 配置无效时抛出异常
        """
        if isinstance(broker_type, str):
            broker_type = BrokerType(broker_type)

        if broker_type == BrokerType.BACKTRADER:
            required_fields = ["cash"]
            for field in required_fields:
                if field not in config:
                    raise ValueError(f"BackTrader config missing required field: {field}")

        elif broker_type in [BrokerType.QMT_LIVE, BrokerType.QMT_SIM]:
            required_fields = ["session_id", "account_id"]
            for field in required_fields:
                if field not in config:
                    raise ValueError(f"QMT config missing required field: {field}")

            # 验证session_id是数字
            try:
                int(config["session_id"])
            except (ValueError, TypeError):
                raise ValueError("session_id must be a valid integer")

        return True


# 便捷函数
def create_backtrader_broker(cash: float = 100000, commission: float = 0.001, **kwargs):
    """
    创建BackTrader Broker的便捷函数

    Args:
        cash: 初始资金
        commission: 手续费率
        **kwargs: 其他参数

    Returns:
        BackTraderBroker: BackTrader Broker实例
    """
    if not BACKTRADER_AVAILABLE:
        raise ImportError("BackTrader not available. Please install with: pip install backtrader")

    config = BrokerConfig.get_backtrader_config(cash, commission, **kwargs)
    return BrokerFactory.create_broker(BrokerType.BACKTRADER, config)


def create_qmt_live_broker(session_id: int, account_id: str, **kwargs):
    """
    创建QMT实盘Broker的便捷函数

    Args:
        session_id: QMT会话ID
        account_id: 资金账号
        **kwargs: 其他参数

    Returns:
        MiniQMTLiveBroker: QMT实盘Broker实例
    """
    if not QMT_AVAILABLE:
        raise ImportError("xtquant not available. Please install xtquant SDK")

    config = BrokerConfig.get_qmt_live_config(session_id, account_id, **kwargs)
    return BrokerFactory.create_broker(BrokerType.QMT_LIVE, config)


def create_qmt_sim_broker(
    session_id: int, account_id: str, initial_cash: float = 1000000, **kwargs
):
    """
    创建QMT模拟Broker的便捷函数

    Args:
        session_id: QMT会话ID
        account_id: 模拟账号
        initial_cash: 初始资金
        **kwargs: 其他参数

    Returns:
        MiniQMTSimBroker: QMT模拟Broker实例
    """
    if not QMT_AVAILABLE:
        raise ImportError("xtquant not available. Please install xtquant SDK")

    config = BrokerConfig.get_qmt_sim_config(session_id, account_id, initial_cash, **kwargs)
    return BrokerFactory.create_broker(BrokerType.QMT_SIM, config)
