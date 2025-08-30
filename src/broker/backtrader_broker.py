#!/usr/bin/env python
"""
BackTrader Broker适配器
将统一Broker接口适配到BackTrader的Broker
"""
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Union

try:
    import backtrader as bt

    BACKTRADER_AVAILABLE = True
except ImportError:
    BACKTRADER_AVAILABLE = False
    bt = None

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


class BackTraderBroker(BaseBroker):
    """
    BackTrader Broker适配器
    将BackTrader的Broker接口适配为统一接口
    """

    def __init__(self, config: Dict):
        """
        初始化BackTrader Broker适配器

        Args:
            config: 配置参数，应包含：
                - cash: 初始资金
                - commission: 手续费率
                - slip_perc: 滑点百分比
                - slip_fixed: 固定滑点
                - slip_open: 开盘滑点
                - slip_match: 滑点匹配
        """
        if not BACKTRADER_AVAILABLE:
            raise ImportError(
                "BackTrader not available. Please install with: pip install backtrader"
            )

        super().__init__(config)
        self.cerebro = None
        self.bt_broker = None
        self._order_mapping: Dict[str, object] = {}  # 我们的order_id -> bt.Order
        self._bt_order_mapping: Dict[object, str] = {}  # bt.Order -> 我们的order_id

    def set_cerebro(self, cerebro):
        """
        设置Cerebro实例

        Args:
            cerebro: BackTrader的Cerebro实例
        """
        self.cerebro = cerebro
        self.bt_broker = cerebro.broker

        # 配置Broker参数
        if "cash" in self.config:
            self.bt_broker.setcash(self.config["cash"])

        if "commission" in self.config:
            self.bt_broker.setcommission(commission=self.config["commission"])

        # 设置滑点
        if "slip_perc" in self.config:
            self.bt_broker.set_slippage_perc(
                perc=self.config.get("slip_perc", 0.0),
                slip_open=self.config.get("slip_open", False),
                slip_match=self.config.get("slip_match", True),
            )
        elif "slip_fixed" in self.config:
            self.bt_broker.set_slippage_fixed(
                fixed=self.config.get("slip_fixed", 0.0),
                slip_open=self.config.get("slip_open", False),
                slip_match=self.config.get("slip_match", True),
            )

    def connect(self) -> bool:
        """
        连接到Broker（BackTrader中无需显式连接）

        Returns:
            bool: 连接是否成功
        """
        self.is_connected = self.bt_broker is not None
        return self.is_connected

    def disconnect(self) -> bool:
        """
        断开Broker连接（BackTrader中无需显式断开）

        Returns:
            bool: 断开是否成功
        """
        self.is_connected = False
        return True

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
        if not self.is_connected or not self.bt_broker:
            raise RuntimeError("Broker not connected")

        # 获取数据源
        data = None
        for d in self.cerebro.datas:
            if hasattr(d, "_name") and d._name == symbol:
                data = d
                break

        if data is None:
            raise ValueError(f"Data for symbol {symbol} not found")

        # 转换订单参数
        size = quantity if side == OrderSide.BUY else -quantity

        # 根据订单类型创建订单
        if order_type == OrderType.MARKET:
            bt_order = (
                self.bt_broker.buy(data=data, size=size)
                if side == OrderSide.BUY
                else self.bt_broker.sell(data=data, size=abs(size))
            )
        elif order_type == OrderType.LIMIT:
            if price is None:
                raise ValueError("Limit order requires price")
            bt_order = (
                self.bt_broker.buy(data=data, size=size, price=price)
                if side == OrderSide.BUY
                else self.bt_broker.sell(data=data, size=abs(size), price=price)
            )
        elif order_type == OrderType.STOP:
            if stop_price is None:
                raise ValueError("Stop order requires stop_price")
            # BackTrader中止损单使用exectype=bt.Order.Stop
            bt_order = (
                self.bt_broker.buy(data=data, size=size, price=stop_price, exectype=bt.Order.Stop)
                if side == OrderSide.BUY
                else self.bt_broker.sell(
                    data=data, size=abs(size), price=stop_price, exectype=bt.Order.Stop
                )
            )
        elif order_type == OrderType.STOP_LIMIT:
            if price is None or stop_price is None:
                raise ValueError("Stop limit order requires both price and stop_price")
            # BackTrader中止损限价单使用exectype=bt.Order.StopLimit
            bt_order = (
                self.bt_broker.buy(
                    data=data,
                    size=size,
                    price=price,
                    plimit=stop_price,
                    exectype=bt.Order.StopLimit,
                )
                if side == OrderSide.BUY
                else self.bt_broker.sell(
                    data=data,
                    size=abs(size),
                    price=price,
                    plimit=stop_price,
                    exectype=bt.Order.StopLimit,
                )
            )
        else:
            raise ValueError(f"Unsupported order type: {order_type}")

        # 生成订单ID并建立映射
        order_id = str(uuid.uuid4())
        self._order_mapping[order_id] = bt_order
        self._bt_order_mapping[bt_order] = order_id

        # 创建OrderInfo
        order_info = OrderInfo(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            status=self._convert_bt_status(bt_order.status),
            created_time=datetime.now(),
            extra_params=kwargs,
        )

        self._orders[order_id] = order_info
        return order_id

    def cancel_order(self, order_id: str) -> bool:
        """
        取消订单

        Args:
            order_id: 订单ID

        Returns:
            bool: 是否成功取消
        """
        if not self.is_connected or not self.bt_broker:
            return False

        bt_order = self._order_mapping.get(order_id)
        if not bt_order:
            return False

        try:
            self.bt_broker.cancel(bt_order)
            # 更新订单状态
            if order_id in self._orders:
                self._orders[order_id].status = OrderStatus.CANCELED
                self._orders[order_id].updated_time = datetime.now()
            return True
        except Exception:
            return False

    def get_order(self, order_id: str) -> Optional[OrderInfo]:
        """
        获取订单信息

        Args:
            order_id: 订单ID

        Returns:
            OrderInfo: 订单信息，如果不存在返回None
        """
        order_info = self._orders.get(order_id)
        if order_info and order_id in self._order_mapping:
            # 更新状态
            bt_order = self._order_mapping[order_id]
            order_info.status = self._convert_bt_status(bt_order.status)
            order_info.filled_qty = bt_order.executed.size
            order_info.avg_price = bt_order.executed.price
            order_info.commission = bt_order.executed.comm
            order_info.updated_time = datetime.now()

        return order_info

    def get_orders(self, symbol: Optional[str] = None) -> List[OrderInfo]:
        """
        获取订单列表

        Args:
            symbol: 股票代码，为None时返回所有订单

        Returns:
            List[OrderInfo]: 订单信息列表
        """
        orders = []
        for order_id, order_info in self._orders.items():
            if symbol is None or order_info.symbol == symbol:
                # 更新状态
                updated_order = self.get_order(order_id)
                if updated_order:
                    orders.append(updated_order)
        return orders

    def get_position(self, symbol: str) -> Optional[PositionInfo]:
        """
        获取持仓信息

        Args:
            symbol: 股票代码

        Returns:
            PositionInfo: 持仓信息，如果不存在返回None
        """
        if not self.is_connected or not self.bt_broker:
            return None

        # 找到对应的数据源
        data = None
        for d in self.cerebro.datas:
            if hasattr(d, "_name") and d._name == symbol:
                data = d
                break

        if data is None:
            return None

        position = self.bt_broker.getposition(data)
        if position.size == 0:
            return None

        current_price = data.close[0] if len(data.close) > 0 else 0.0
        market_value = abs(position.size) * current_price
        pnl = (current_price - position.price) * position.size
        pnl_percent = (
            (pnl / (abs(position.size) * position.price)) * 100 if position.price > 0 else 0
        )

        return PositionInfo(
            symbol=symbol,
            side=PositionSide.LONG if position.size > 0 else PositionSide.SHORT,
            quantity=abs(position.size),
            avg_price=position.price,
            market_value=market_value,
            pnl=pnl,
            pnl_percent=pnl_percent,
            available_qty=abs(position.size),  # BackTrader中可用数量等于持仓数量
        )

    def get_positions(self) -> List[PositionInfo]:
        """
        获取所有持仓

        Returns:
            List[PositionInfo]: 持仓信息列表
        """
        positions = []
        if not self.is_connected or not self.bt_broker:
            return positions

        for data in self.cerebro.datas:
            symbol = getattr(data, "_name", str(data))
            position = self.get_position(symbol)
            if position:
                positions.append(position)

        return positions

    def get_account_info(self) -> Optional[AccountInfo]:
        """
        获取账户信息

        Returns:
            AccountInfo: 账户信息
        """
        if not self.is_connected or not self.bt_broker:
            return None

        cash = self.bt_broker.getcash()
        value = self.bt_broker.getvalue()
        market_value = value - cash
        pnl = value - self.config.get("cash", 100000)  # 与初始资金比较
        pnl_percent = (pnl / self.config.get("cash", 100000)) * 100

        return AccountInfo(
            account_id="backtrader",
            total_value=value,
            available_cash=cash,
            market_value=market_value,
            pnl=pnl,
            pnl_percent=pnl_percent,
            buying_power=cash,  # BackTrader中买入能力等于现金
        )

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        获取当前价格

        Args:
            symbol: 股票代码

        Returns:
            float: 当前价格，如果获取失败返回None
        """
        if not self.cerebro:
            return None

        for data in self.cerebro.datas:
            if hasattr(data, "_name") and data._name == symbol:
                return data.close[0] if len(data.close) > 0 else None

        return None

    def _convert_bt_status(self, bt_status: int) -> OrderStatus:
        """
        转换BackTrader订单状态到统一状态

        Args:
            bt_status: BackTrader订单状态

        Returns:
            OrderStatus: 统一订单状态
        """
        status_mapping = {
            bt.Order.Created: OrderStatus.PENDING,
            bt.Order.Submitted: OrderStatus.SUBMITTED,
            bt.Order.Accepted: OrderStatus.SUBMITTED,
            bt.Order.Partial: OrderStatus.PARTIAL,
            bt.Order.Completed: OrderStatus.FILLED,
            bt.Order.Canceled: OrderStatus.CANCELED,
            bt.Order.Expired: OrderStatus.CANCELED,
            bt.Order.Margin: OrderStatus.REJECTED,
            bt.Order.Rejected: OrderStatus.REJECTED,
        }

        return status_mapping.get(bt_status, OrderStatus.FAILED)
