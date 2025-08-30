#!/usr/bin/env python
"""
统一Broker抽象接口
支持BackTrader回测、MiniQMT实盘交易、MiniQMT模拟交易
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union

import pandas as pd


class OrderType(Enum):
    """订单类型枚举"""

    MARKET = "market"  # 市价单
    LIMIT = "limit"  # 限价单
    STOP = "stop"  # 止损单
    STOP_LIMIT = "stop_limit"  # 止损限价单


class OrderSide(Enum):
    """订单方向枚举"""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """订单状态枚举"""

    PENDING = "pending"  # 待报
    SUBMITTED = "submitted"  # 已提交
    PARTIAL = "partial"  # 部分成交
    FILLED = "filled"  # 全部成交
    CANCELED = "canceled"  # 已撤销
    REJECTED = "rejected"  # 已拒绝
    FAILED = "failed"  # 失败


class PositionSide(Enum):
    """持仓方向枚举"""

    LONG = "long"
    SHORT = "short"


@dataclass
class OrderInfo:
    """订单信息数据类"""

    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: float = 0.0
    avg_price: float = 0.0
    commission: float = 0.0
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None
    extra_params: Dict = None

    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}


@dataclass
class PositionInfo:
    """持仓信息数据类"""

    symbol: str
    side: PositionSide
    quantity: float
    avg_price: float
    market_value: float
    pnl: float
    pnl_percent: float
    available_qty: float = None  # 可用数量（可卖出）

    def __post_init__(self):
        if self.available_qty is None:
            self.available_qty = self.quantity


@dataclass
class AccountInfo:
    """账户信息数据类"""

    account_id: str
    total_value: float
    available_cash: float
    market_value: float
    pnl: float
    pnl_percent: float
    buying_power: float = None

    def __post_init__(self):
        if self.buying_power is None:
            self.buying_power = self.available_cash


class BaseBroker(ABC):
    """
    统一Broker抽象基类
    定义所有Broker实现必须遵循的接口
    """

    def __init__(self, config: Dict):
        """
        初始化Broker

        Args:
            config: 配置参数字典
        """
        self.config = config
        self.is_connected = False
        self._orders: Dict[str, OrderInfo] = {}
        self._positions: Dict[str, PositionInfo] = {}
        self._account_info: Optional[AccountInfo] = None

    @abstractmethod
    def connect(self) -> bool:
        """
        连接到Broker

        Returns:
            bool: 连接是否成功
        """
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """
        断开Broker连接

        Returns:
            bool: 断开是否成功
        """
        pass

    @abstractmethod
    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        **kwargs,
    ) -> str:
        """
        提交订单

        Args:
            symbol: 股票代码
            side: 买卖方向
            quantity: 数量
            order_type: 订单类型
            price: 价格（限价单必需）
            stop_price: 止损价（止损单必需）
            **kwargs: 其他参数

        Returns:
            str: 订单ID
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        取消订单

        Args:
            order_id: 订单ID

        Returns:
            bool: 是否成功取消
        """
        pass

    @abstractmethod
    def get_order(self, order_id: str) -> Optional[OrderInfo]:
        """
        获取订单信息

        Args:
            order_id: 订单ID

        Returns:
            OrderInfo: 订单信息，如果不存在返回None
        """
        pass

    @abstractmethod
    def get_orders(self, symbol: Optional[str] = None) -> List[OrderInfo]:
        """
        获取订单列表

        Args:
            symbol: 股票代码，为None时返回所有订单

        Returns:
            List[OrderInfo]: 订单信息列表
        """
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[PositionInfo]:
        """
        获取持仓信息

        Args:
            symbol: 股票代码

        Returns:
            PositionInfo: 持仓信息，如果不存在返回None
        """
        pass

    @abstractmethod
    def get_positions(self) -> List[PositionInfo]:
        """
        获取所有持仓

        Returns:
            List[PositionInfo]: 持仓信息列表
        """
        pass

    @abstractmethod
    def get_account_info(self) -> Optional[AccountInfo]:
        """
        获取账户信息

        Returns:
            AccountInfo: 账户信息
        """
        pass

    @abstractmethod
    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        获取当前价格

        Args:
            symbol: 股票代码

        Returns:
            float: 当前价格，如果获取失败返回None
        """
        pass

    def get_portfolio_value(self) -> float:
        """
        获取投资组合总价值

        Returns:
            float: 投资组合总价值
        """
        account = self.get_account_info()
        return account.total_value if account else 0.0

    def get_cash(self) -> float:
        """
        获取可用现金

        Returns:
            float: 可用现金
        """
        account = self.get_account_info()
        return account.available_cash if account else 0.0

    def get_position_size(self, symbol: str) -> float:
        """
        获取持仓数量

        Args:
            symbol: 股票代码

        Returns:
            float: 持仓数量，正数表示多头，负数表示空头，0表示无持仓
        """
        position = self.get_position(symbol)
        if not position:
            return 0.0

        return position.quantity if position.side == PositionSide.LONG else -position.quantity

    def get_position_value(self, symbol: str) -> float:
        """
        获取持仓市值

        Args:
            symbol: 股票代码

        Returns:
            float: 持仓市值
        """
        position = self.get_position(symbol)
        return position.market_value if position else 0.0

    # 便捷方法
    def buy(self, symbol: str, quantity: float, price: Optional[float] = None, **kwargs) -> str:
        """
        买入股票的便捷方法

        Args:
            symbol: 股票代码
            quantity: 数量
            price: 价格，为None时使用市价单
            **kwargs: 其他参数

        Returns:
            str: 订单ID
        """
        order_type = OrderType.LIMIT if price is not None else OrderType.MARKET
        return self.submit_order(symbol, OrderSide.BUY, quantity, order_type, price, **kwargs)

    def sell(self, symbol: str, quantity: float, price: Optional[float] = None, **kwargs) -> str:
        """
        卖出股票的便捷方法

        Args:
            symbol: 股票代码
            quantity: 数量
            price: 价格，为None时使用市价单
            **kwargs: 其他参数

        Returns:
            str: 订单ID
        """
        order_type = OrderType.LIMIT if price is not None else OrderType.MARKET
        return self.submit_order(symbol, OrderSide.SELL, quantity, order_type, price, **kwargs)

    def close_position(self, symbol: str, price: Optional[float] = None, **kwargs) -> Optional[str]:
        """
        平仓的便捷方法

        Args:
            symbol: 股票代码
            price: 价格，为None时使用市价单
            **kwargs: 其他参数

        Returns:
            str: 订单ID，如果无持仓返回None
        """
        position = self.get_position(symbol)
        if not position or position.available_qty <= 0:
            return None

        # 平仓总是卖出
        return self.sell(symbol, position.available_qty, price, **kwargs)

    def is_market_open(self) -> bool:
        """
        检查市场是否开放

        Returns:
            bool: 市场是否开放
        """
        # 默认实现，子类可以重写
        now = datetime.now()
        # 简单判断：工作日的9:30-15:00
        if now.weekday() >= 5:  # 周末
            return False

        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)

        return market_open <= now <= market_close

    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect()
