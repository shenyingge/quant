"""
统一Broker接口模块
"""

from .base_broker import (
    AccountInfo,
    BaseBroker,
    OrderInfo,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionInfo,
    PositionSide,
)

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
from .broker_factory import (
    BrokerConfig,
    BrokerFactory,
    BrokerType,
    create_backtrader_broker,
    create_qmt_live_broker,
    create_qmt_sim_broker,
)

# 构建__all__列表
__all__ = [
    "BaseBroker",
    "OrderType",
    "OrderSide",
    "OrderStatus",
    "PositionSide",
    "OrderInfo",
    "PositionInfo",
    "AccountInfo",
    "BrokerFactory",
    "BrokerConfig",
    "BrokerType",
]

# 条件添加可用的组件
if BACKTRADER_AVAILABLE:
    __all__.extend(["BackTraderBroker", "create_backtrader_broker"])

if QMT_AVAILABLE:
    __all__.extend(
        ["MiniQMTLiveBroker", "MiniQMTSimBroker", "create_qmt_live_broker", "create_qmt_sim_broker"]
    )
