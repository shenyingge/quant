#!/usr/bin/env python
"""
MiniQMT模拟Broker适配器
将统一Broker接口适配到MiniQMT模拟交易
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


class MiniQMTSimBroker(BaseBroker):
    """
    MiniQMT模拟Broker适配器
    使用xtquant SDK进行模拟交易
    """

    def __init__(self, config: Dict):
        """
        初始化MiniQMT模拟Broker

        Args:
            config: 配置参数，应包含：
                - session_id: QMT会话ID
                - account_id: 模拟资金账号
                - account_type: 账户类型（通常为'SIMULATION'或'STOCK'）
                - qmt_path: QMT安装路径（可选）
                - initial_cash: 初始资金（模拟账户专用）
                - commission_rate: 手续费率（模拟交易可配置）
                - slippage: 滑点设置（模拟交易可配置）
        """
        super().__init__(config)

        if not XTQUANT_AVAILABLE:
            raise ImportError("xtquant not available. Please install xtquant SDK.")

        self.session_id = config.get("session_id")
        self.account_id = config.get("account_id")
        self.account_type = config.get("account_type", "STOCK")  # 账户类型，即使是模拟也使用STOCK
        self.qmt_path = config.get("qmt_path", "")

        # 模拟交易专用配置
        self.initial_cash = config.get("initial_cash", 1000000)  # 默认100万初始资金
        self.commission_rate = config.get("commission_rate", 0.0003)  # 默认万分之3手续费
        self.slippage = config.get("slippage", 0.001)  # 默认0.1%滑点

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
        连接到QMT模拟环境

        Returns:
            bool: 连接是否成功
        """
        try:
            # 创建QMT交易实例
            self.xt_trader = XtQuantTrader(self.qmt_path, self.session_id)

            # 连接QMT
            connect_result = self.xt_trader.connect()

            if connect_result != 0:
                self.logger.error(f"Failed to connect to QMT simulation: {connect_result}")
                return False

            # 订阅模拟账户信息
            subscribe_result = self.xt_trader.subscribe(self.account)
            if subscribe_result != 0:
                self.logger.error(f"Failed to subscribe simulation account: {subscribe_result}")
                return False

            # 检查模拟账户状态
            account_status = self.xt_trader.query_stock_account_status(self.account)
            self.logger.info(f"Simulation account status: {account_status}")

            if account_status != 0:  # 0表示正常状态
                status_desc = ACCOUNT_STATUS_MAP.get(account_status, f"Unknown({account_status})")
                self.logger.warning(f"Simulation account status not normal: {status_desc}")
                # 模拟账户可能有不同的状态码，这里相对宽松处理

            self.is_connected = True

            # 启动订单监控
            self._start_order_monitoring()

            self.logger.info("Connected to QMT simulation successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to connect to QMT simulation: {e}")
            return False

    def disconnect(self) -> bool:
        """
        断开QMT模拟连接

        Returns:
            bool: 断开是否成功
        """
        try:
            self._stop_order_monitoring()

            # 取消模拟账户订阅和断开连接
            if self.is_connected and self.xt_trader:
                self.xt_trader.unsubscribe(self.account)
                self.xt_trader.disconnect()

            self.is_connected = False
            self.xt_trader = None
            self.logger.info("Disconnected from QMT simulation")
            return True

        except Exception as e:
            self.logger.error(f"Error disconnecting from QMT simulation: {e}")
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
        提交模拟订单

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
            raise RuntimeError("Simulation broker not connected")

        # 模拟交易中添加滑点处理
        effective_price = price
        if order_type == OrderType.MARKET:
            current_price = self.get_current_price(symbol)
            if current_price:
                # 模拟滑点
                slippage_amount = current_price * self.slippage
                if side == OrderSide.BUY:
                    effective_price = current_price + slippage_amount
                else:
                    effective_price = current_price - slippage_amount
            xt_order_type = xtconstant.MARKET_PRICE
        elif order_type == OrderType.LIMIT:
            if price is None:
                raise ValueError("Limit order requires price")
            xt_order_type = xtconstant.FIX_PRICE
            effective_price = price
        else:
            raise ValueError(f"Unsupported order type for QMT simulation: {order_type}")

        # 转换买卖方向
        if side == OrderSide.BUY:
            xt_side = xtconstant.STOCK_BUY
        else:
            xt_side = xtconstant.STOCK_SELL

        try:
            # 提交模拟订单
            order_id = self.xt_trader.order_stock(
                account=self.account,
                stock_code=symbol,
                order_type=xt_side,
                order_volume=int(quantity),  # QMT要求整数股数
                price_type=xt_order_type,
                price=effective_price if effective_price else 0,
                strategy_name=kwargs.get("strategy_name", "UnifiedBrokerSim"),
                order_remark=kwargs.get("order_remark", "Simulation"),
            )

            if order_id < 0:
                raise RuntimeError(f"Simulation order submission failed with code: {order_id}")

            # 生成统一订单ID
            unified_order_id = str(uuid.uuid4())

            # 创建OrderInfo，包含模拟特殊信息
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
                extra_params={
                    **kwargs,
                    "qmt_order_id": order_id,
                    "effective_price": effective_price,
                    "is_simulation": True,
                    "slippage_applied": self.slippage if order_type == OrderType.MARKET else 0,
                },
            )

            self._orders[unified_order_id] = order_info

            # 注册订单回调
            self._order_callbacks[order_id] = unified_order_id

            self.logger.info(f"Simulation order submitted: {unified_order_id} (QMT: {order_id})")
            return unified_order_id

        except Exception as e:
            self.logger.error(f"Failed to submit simulation order: {e}")
            raise

    def cancel_order(self, order_id: str) -> bool:
        """
        取消模拟订单

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
                self.logger.info(f"Simulation order canceled: {order_id}")
                return True
            else:
                self.logger.error(f"Failed to cancel simulation order {order_id}: {result}")
                return False

        except Exception as e:
            self.logger.error(f"Error canceling simulation order {order_id}: {e}")
            return False

    def get_order(self, order_id: str) -> Optional[OrderInfo]:
        """
        获取模拟订单信息

        Args:
            order_id: 订单ID

        Returns:
            OrderInfo: 订单信息，如果不存在返回None
        """
        order_info = self._orders.get(order_id)
        if not order_info:
            return None

        # 从QMT模拟环境查询最新状态
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

                        # 计算模拟手续费
                        if order_info.filled_qty > 0 and order_info.commission == 0:
                            order_info.commission = self._calculate_commission(
                                order_info.filled_qty, order_info.avg_price
                            )

                        order_info.updated_time = datetime.now()
                        break

            except Exception as e:
                self.logger.error(f"Error querying simulation order {order_id}: {e}")

        return order_info

    def get_orders(self, symbol: Optional[str] = None) -> List[OrderInfo]:
        """
        获取模拟订单列表

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
        获取模拟持仓信息

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
                        side=PositionSide.LONG,  # 模拟环境通常只支持多头
                        quantity=pos.volume,
                        avg_price=pos.price,
                        market_value=market_value,
                        pnl=pnl,
                        pnl_percent=pnl_percent,
                        available_qty=pos.can_use_volume,
                    )

            return None

        except Exception as e:
            self.logger.error(f"Error getting simulation position for {symbol}: {e}")
            return None

    def get_positions(self) -> List[PositionInfo]:
        """
        获取所有模拟持仓

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
            self.logger.error(f"Error getting simulation positions: {e}")

        return positions

    def get_account_info(self) -> Optional[AccountInfo]:
        """
        获取模拟账户信息

        Returns:
            AccountInfo: 账户信息
        """
        if not self.is_connected:
            return None

        try:
            assets = self.xt_trader.query_stock_asset(self.account)

            if not assets:
                # 如果查询不到资产信息，返回模拟的初始状态
                return AccountInfo(
                    account_id=f"{self.account_id}_SIM",
                    total_value=self.initial_cash,
                    available_cash=self.initial_cash,
                    market_value=0.0,
                    pnl=0.0,
                    pnl_percent=0.0,
                    buying_power=self.initial_cash,
                )

            asset = assets[0]  # 取第一个账户资产信息

            # 计算相对于初始资金的盈亏
            total_pnl = asset.total_asset - self.initial_cash
            pnl_percent = (total_pnl / self.initial_cash) * 100 if self.initial_cash > 0 else 0

            return AccountInfo(
                account_id=f"{self.account_id}_SIM",
                total_value=asset.total_asset,
                available_cash=asset.cash,
                market_value=asset.market_value,
                pnl=total_pnl,
                pnl_percent=pnl_percent,
                buying_power=asset.cash,
            )

        except Exception as e:
            self.logger.error(f"Error getting simulation account info: {e}")
            # 返回默认的模拟账户信息
            return AccountInfo(
                account_id=f"{self.account_id}_SIM",
                total_value=self.initial_cash,
                available_cash=self.initial_cash,
                market_value=0.0,
                pnl=0.0,
                pnl_percent=0.0,
                buying_power=self.initial_cash,
            )

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        获取当前价格（模拟环境）

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

            # 如果实时数据获取失败，尝试获取最近的历史数据
            market_data = xtdata.get_market_data(
                field_list=["close"], stock_list=[symbol], period="1d", count=1
            )

            if market_data and symbol in market_data:
                df = market_data[symbol]
                if not df.empty:
                    return float(df["close"].iloc[-1])

            return None

        except Exception as e:
            self.logger.error(f"Error getting current price for {symbol} in simulation: {e}")
            return None

    def _calculate_commission(self, volume: float, price: float) -> float:
        """
        计算模拟交易手续费

        Args:
            volume: 成交量
            price: 成交价格

        Returns:
            float: 手续费金额
        """
        turnover = volume * price
        commission = turnover * self.commission_rate
        # 设置最低手续费（通常为5元）
        min_commission = 5.0
        return max(commission, min_commission)

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
        self.logger.info("Simulation order monitoring started")

    def _stop_order_monitoring(self):
        """停止订单监控线程"""
        self._monitoring = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)
        self.logger.info("Simulation order monitoring stopped")

    def _monitor_orders(self):
        """监控订单状态变化"""
        while self._monitoring:
            try:
                # 每3秒检查一次订单状态（模拟环境可以更频繁）
                time.sleep(3)

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
                self.logger.error(f"Error in simulation order monitoring: {e}")

    def is_market_open(self) -> bool:
        """
        检查市场是否开放（模拟环境可以更宽松）

        Returns:
            bool: 市场是否开放
        """
        # 模拟环境可以24小时交易，或者按需配置
        if self.config.get("sim_24h_trading", False):
            return True

        # 否则按照正常交易时间
        return super().is_market_open()

    def reset_simulation(self):
        """
        重置模拟环境（清空持仓和订单，恢复初始资金）
        这是模拟环境特有的功能
        """
        self.logger.info("Resetting simulation environment")

        # 清空内存中的订单记录
        self._orders.clear()
        self._order_callbacks.clear()

        # 注意：QMT模拟环境的重置需要通过QMT客户端界面操作
        # 这里只能清空我们的内部状态
        self.logger.info(
            "Simulation state cleared. Please reset QMT simulation account manually if needed."
        )
