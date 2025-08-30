#!/usr/bin/env python
"""
MiniQMT实盘Broker适配器
将统一Broker接口适配到MiniQMT实盘交易
"""
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

try:
    from xtquant import xtconstant, xtdata
    from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
    from xtquant.xttype import StockAccount

    XTQUANT_AVAILABLE = True
except ImportError:
    XTQUANT_AVAILABLE = False
    XtQuantTrader = None
    XtQuantTraderCallback = None
    xtdata = None
    xtconstant = None
    StockAccount = None

from ..qmt_constants import ACCOUNT_STATUS_MAP, ORDER_STATUS_MAP
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


class MiniQMTLiveBroker(BaseBroker):
    """
    MiniQMT实盘Broker适配器
    使用xtquant SDK进行实盘交易
    """

    def __init__(self, config: Dict):
        """
        初始化MiniQMT实盘Broker

        Args:
            config: 配置参数，应包含：
                - session_id: QMT会话ID
                - account_id: 资金账号
                - account_type: 账户类型（如'STOCK'）
                - qmt_path: QMT安装路径（可选）
        """
        super().__init__(config)

        if not XTQUANT_AVAILABLE:
            raise ImportError("xtquant not available. Please install xtquant SDK.")

        self.session_id = config.get("session_id")
        self.account_id = config.get("account_id")
        self.account_type = config.get("account_type", "STOCK")
        self.qmt_path = config.get("qmt_path", "")

        if not self.session_id or not self.account_id:
            raise ValueError("session_id and account_id are required")

        # 账户对象
        self.account = StockAccount(self.account_id, self.account_type)

        # QMT交易实例
        self.xt_trader = None

        # 订单监控
        self._order_callbacks = {}
        self._monitoring = False
        self._monitor_thread = None

        # 设置日志
        self.logger = logging.getLogger(__name__)

    def connect(self) -> bool:
        """
        连接到QMT

        Returns:
            bool: 连接是否成功
        """
        try:
            # 创建QMT交易实例
            self.xt_trader = XtQuantTrader(self.qmt_path, self.session_id)

            # 连接QMT
            connect_result = self.xt_trader.connect()

            if connect_result != 0:
                self.logger.error(f"Failed to connect to QMT: {connect_result}")
                return False

            # 订阅账户信息
            subscribe_result = self.xt_trader.subscribe(self.account)
            if subscribe_result != 0:
                self.logger.error(f"Failed to subscribe account: {subscribe_result}")
                return False

            # 检查账户状态
            account_status = self.xt_trader.query_stock_account_status(self.account)
            self.logger.info(f"Account status: {account_status}")

            if account_status != 0:  # 0表示正常状态
                status_desc = ACCOUNT_STATUS_MAP.get(account_status, f"Unknown({account_status})")
                self.logger.warning(f"Account status not normal: {status_desc}")

            self.is_connected = True

            # 启动订单监控
            self._start_order_monitoring()

            self.logger.info("Connected to QMT successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to connect to QMT: {e}")
            return False

    def disconnect(self) -> bool:
        """
        断开QMT连接

        Returns:
            bool: 断开是否成功
        """
        try:
            self._stop_order_monitoring()

            # 取消账户订阅和断开连接
            if self.is_connected and self.xt_trader:
                self.xt_trader.unsubscribe(self.account)
                self.xt_trader.disconnect()

            self.is_connected = False
            self.xt_trader = None
            self.logger.info("Disconnected from QMT")
            return True

        except Exception as e:
            self.logger.error(f"Error disconnecting from QMT: {e}")
            return False

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
        if not self.is_connected:
            raise RuntimeError("Broker not connected")

        # 转换订单类型
        if order_type == OrderType.MARKET:
            xt_order_type = xtconstant.MARKET_PRICE  # 市价单
            order_price = 0  # 市价单价格为0
        elif order_type == OrderType.LIMIT:
            if price is None:
                raise ValueError("Limit order requires price")
            xt_order_type = xtconstant.FIX_PRICE  # 限价单
            order_price = price
        else:
            raise ValueError(f"Unsupported order type for QMT: {order_type}")

        # 转换买卖方向
        if side == OrderSide.BUY:
            xt_side = xtconstant.STOCK_BUY
        else:
            xt_side = xtconstant.STOCK_SELL

        try:
            # 提交订单
            order_id = self.xt_trader.order_stock(
                account=self.account,
                stock_code=symbol,
                order_type=xt_side,
                order_volume=int(quantity),  # QMT要求整数股数
                price_type=xt_order_type,
                price=order_price,
                strategy_name=kwargs.get("strategy_name", "UnifiedBroker"),
                order_remark=kwargs.get("order_remark", ""),
            )

            if order_id < 0:
                raise RuntimeError(f"Order submission failed with code: {order_id}")

            # 生成统一订单ID
            unified_order_id = str(uuid.uuid4())

            # 创建OrderInfo
            order_info = OrderInfo(
                order_id=unified_order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                stop_price=stop_price,
                status=OrderStatus.SUBMITTED,
                created_time=datetime.now(),
                extra_params={**kwargs, "qmt_order_id": order_id},
            )

            self._orders[unified_order_id] = order_info

            # 注册订单回调
            self._order_callbacks[order_id] = unified_order_id

            self.logger.info(f"Order submitted: {unified_order_id} (QMT: {order_id})")
            return unified_order_id

        except Exception as e:
            self.logger.error(f"Failed to submit order: {e}")
            raise

    def cancel_order(self, order_id: str) -> bool:
        """
        取消订单

        Args:
            order_id: 订单ID

        Returns:
            bool: 是否成功取消
        """
        if not self.is_connected:
            return False

        order_info = self._orders.get(order_id)
        if not order_info:
            return False

        qmt_order_id = order_info.extra_params.get("qmt_order_id")
        if not qmt_order_id:
            return False

        try:
            result = self.xt_trader.cancel_order_stock(self.account, qmt_order_id)

            if result == 0:  # 取消成功
                order_info.status = OrderStatus.CANCELED
                order_info.updated_time = datetime.now()
                self.logger.info(f"Order canceled: {order_id}")
                return True
            else:
                self.logger.error(f"Failed to cancel order {order_id}: {result}")
                return False

        except Exception as e:
            self.logger.error(f"Error canceling order {order_id}: {e}")
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
        if not order_info:
            return None

        # 从QMT查询最新状态
        qmt_order_id = order_info.extra_params.get("qmt_order_id")
        if qmt_order_id and self.is_connected:
            try:
                orders = self.xt_trader.query_stock_orders(self.account, cancelable_only=False)

                for qmt_order in orders:
                    if qmt_order.order_id == qmt_order_id:
                        # 更新订单信息
                        order_info.status = self._convert_qmt_status(qmt_order.order_status)
                        order_info.filled_qty = qmt_order.traded_volume
                        order_info.avg_price = (
                            qmt_order.traded_price if qmt_order.traded_volume > 0 else 0
                        )
                        order_info.updated_time = datetime.now()
                        break

            except Exception as e:
                self.logger.error(f"Error querying order {order_id}: {e}")

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
        for order_id in list(self._orders.keys()):
            order_info = self.get_order(order_id)  # 获取最新状态
            if order_info and (symbol is None or order_info.symbol == symbol):
                orders.append(order_info)
        return orders

    def get_position(self, symbol: str) -> Optional[PositionInfo]:
        """
        获取持仓信息

        Args:
            symbol: 股票代码

        Returns:
            PositionInfo: 持仓信息，如果不存在返回None
        """
        if not self.is_connected:
            return None

        try:
            positions = self.xt_trader.query_stock_positions(self.account)

            for pos in positions:
                if pos.stock_code == symbol:
                    if pos.volume <= 0:
                        continue

                    # 获取当前价格用于计算市值和盈亏
                    current_price = self.get_current_price(symbol)
                    if not current_price:
                        current_price = pos.price  # 使用持仓价格作为fallback

                    market_value = pos.volume * current_price
                    pnl = (current_price - pos.price) * pos.volume
                    pnl_percent = (pnl / (pos.volume * pos.price)) * 100 if pos.price > 0 else 0

                    return PositionInfo(
                        symbol=symbol,
                        side=PositionSide.LONG,  # A股只有多头持仓
                        quantity=pos.volume,
                        avg_price=pos.price,
                        market_value=market_value,
                        pnl=pnl,
                        pnl_percent=pnl_percent,
                        available_qty=pos.can_use_volume,
                    )

            return None

        except Exception as e:
            self.logger.error(f"Error getting position for {symbol}: {e}")
            return None

    def get_positions(self) -> List[PositionInfo]:
        """
        获取所有持仓

        Returns:
            List[PositionInfo]: 持仓信息列表
        """
        positions = []

        if not self.is_connected:
            return positions

        try:
            qmt_positions = self.xt_trader.query_stock_positions(self.account)

            for pos in qmt_positions:
                if pos.volume <= 0:
                    continue

                position_info = self.get_position(pos.stock_code)
                if position_info:
                    positions.append(position_info)

        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")

        return positions

    def get_account_info(self) -> Optional[AccountInfo]:
        """
        获取账户信息

        Returns:
            AccountInfo: 账户信息
        """
        if not self.is_connected:
            return None

        try:
            assets = self.xt_trader.query_stock_asset(self.account)

            if not assets:
                return None

            asset = assets[0]  # 取第一个账户资产信息

            return AccountInfo(
                account_id=self.account_id,
                total_value=asset.total_asset,
                available_cash=asset.cash,
                market_value=asset.market_value,
                pnl=asset.total_asset - asset.cash - asset.market_value,  # 简单估算
                pnl_percent=0,  # QMT没有直接提供，可以根据需要计算
                buying_power=asset.cash,  # 买入能力等于可用资金
            )

        except Exception as e:
            self.logger.error(f"Error getting account info: {e}")
            return None

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        获取当前价格

        Args:
            symbol: 股票代码

        Returns:
            float: 当前价格，如果获取失败返回None
        """
        try:
            # 使用xtdata获取当前价格
            data = xtdata.get_full_tick([symbol])
            if data and symbol in data:
                return data[symbol]["lastPrice"]
            return None

        except Exception as e:
            self.logger.error(f"Error getting current price for {symbol}: {e}")
            return None

    def _convert_qmt_status(self, qmt_status: int) -> OrderStatus:
        """
        转换QMT订单状态到统一状态

        Args:
            qmt_status: QMT订单状态

        Returns:
            OrderStatus: 统一订单状态
        """
        return ORDER_STATUS_MAP.get(qmt_status, OrderStatus.FAILED)

    def _start_order_monitoring(self):
        """启动订单监控线程"""
        if self._monitoring:
            return

        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_orders, daemon=True)
        self._monitor_thread.start()
        self.logger.info("Order monitoring started")

    def _stop_order_monitoring(self):
        """停止订单监控线程"""
        self._monitoring = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)
        self.logger.info("Order monitoring stopped")

    def _monitor_orders(self):
        """监控订单状态变化"""
        while self._monitoring:
            try:
                # 每5秒检查一次订单状态
                time.sleep(5)

                if not self.is_connected:
                    continue

                # 更新所有活跃订单状态
                active_orders = [
                    order_id
                    for order_id, order_info in self._orders.items()
                    if order_info.status
                    in [OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL]
                ]

                for order_id in active_orders:
                    self.get_order(order_id)  # 这会自动更新状态

            except Exception as e:
                self.logger.error(f"Error in order monitoring: {e}")

    def is_market_open(self) -> bool:
        """
        检查市场是否开放

        Returns:
            bool: 市场是否开放
        """
        now = datetime.now()

        # 周末不开盘
        if now.weekday() >= 5:
            return False

        # 检查是否在交易时间内
        morning_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
        morning_end = now.replace(hour=11, minute=30, second=0, microsecond=0)
        afternoon_start = now.replace(hour=13, minute=0, second=0, microsecond=0)
        afternoon_end = now.replace(hour=15, minute=0, second=0, microsecond=0)

        return (morning_start <= now <= morning_end) or (afternoon_start <= now <= afternoon_end)
