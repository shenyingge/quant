#!/usr/bin/env python
"""
统一Broker接口测试
验证Broker接口的基本功能
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from src.broker import (
    AccountInfo,
    BaseBroker,
    BrokerConfig,
    BrokerFactory,
    BrokerType,
    OrderInfo,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionInfo,
    PositionSide,
    create_backtrader_broker,
)


class TestBrokerDataTypes(unittest.TestCase):
    """测试Broker数据类型"""

    def test_order_info_creation(self):
        """测试OrderInfo创建"""
        order = OrderInfo(
            order_id="12345",
            symbol="600519.SH",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            price=2100.0,
            status=OrderStatus.PENDING,
        )

        self.assertEqual(order.order_id, "12345")
        self.assertEqual(order.symbol, "600519.SH")
        self.assertEqual(order.side, OrderSide.BUY)
        self.assertEqual(order.quantity, 100)
        self.assertEqual(order.price, 2100.0)

    def test_position_info_creation(self):
        """测试PositionInfo创建"""
        position = PositionInfo(
            symbol="600519.SH",
            side=PositionSide.LONG,
            quantity=100,
            avg_price=2100.0,
            market_value=210000.0,
            pnl=5000.0,
            pnl_percent=2.38,
        )

        self.assertEqual(position.symbol, "600519.SH")
        self.assertEqual(position.side, PositionSide.LONG)
        self.assertEqual(position.quantity, 100)
        self.assertEqual(position.market_value, 210000.0)
        self.assertEqual(position.available_qty, 100)  # 默认值

    def test_account_info_creation(self):
        """测试AccountInfo创建"""
        account = AccountInfo(
            account_id="TEST001",
            total_value=1050000.0,
            available_cash=850000.0,
            market_value=200000.0,
            pnl=50000.0,
            pnl_percent=5.0,
        )

        self.assertEqual(account.account_id, "TEST001")
        self.assertEqual(account.total_value, 1050000.0)
        self.assertEqual(account.buying_power, 850000.0)  # 默认值


class TestBrokerFactory(unittest.TestCase):
    """测试Broker工厂"""

    def test_create_backtrader_broker(self):
        """测试创建BackTrader Broker"""
        config = {"cash": 100000, "commission": 0.001}

        try:
            broker = BrokerFactory.create_broker(BrokerType.BACKTRADER, config)
            self.assertIsNotNone(broker)
            self.assertEqual(broker.config["cash"], 100000)
            self.assertEqual(broker.config["commission"], 0.001)
        except ImportError:
            # 如果BackTrader不可用，跳过测试
            self.skipTest("BackTrader not available")

    def test_unsupported_broker_type(self):
        """测试不支持的Broker类型"""
        with self.assertRaises(ValueError):
            BrokerFactory.create_broker("unsupported_type", {})

    def test_convenience_functions(self):
        """测试便捷函数"""
        try:
            broker = create_backtrader_broker(cash=200000, commission=0.002)
            self.assertIsNotNone(broker)
            self.assertEqual(broker.config["cash"], 200000)
            self.assertEqual(broker.config["commission"], 0.002)
        except ImportError:
            # 如果BackTrader不可用，跳过测试
            self.skipTest("BackTrader not available")

    def test_get_supported_types(self):
        """测试获取支持的类型"""
        types = BrokerFactory.get_supported_types()

        self.assertIn("backtrader", types)
        self.assertIn("qmt_live", types)
        self.assertIn("qmt_sim", types)


class TestBrokerConfig(unittest.TestCase):
    """测试Broker配置"""

    def test_backtrader_config_template(self):
        """测试BackTrader配置模板"""
        config = BrokerConfig.get_backtrader_config(cash=150000, commission=0.0008, slip_perc=0.005)

        expected = {
            "cash": 150000,
            "commission": 0.0008,
            "slip_perc": 0.005,
            "slip_fixed": 0.0,
            "slip_open": False,
            "slip_match": False,
        }

        self.assertEqual(config, expected)

    def test_qmt_live_config_template(self):
        """测试QMT实盘配置模板"""
        config = BrokerConfig.get_qmt_live_config(
            session_id=123456, account_id="LIVE001", account_type="STOCK"
        )

        expected = {
            "session_id": 123456,
            "account_id": "LIVE001",
            "account_type": "STOCK",
            "qmt_path": "",
        }

        self.assertEqual(config, expected)

    def test_qmt_sim_config_template(self):
        """测试QMT模拟配置模板"""
        config = BrokerConfig.get_qmt_sim_config(
            session_id=123456, account_id="SIM001", initial_cash=500000
        )

        self.assertEqual(config["session_id"], 123456)
        self.assertEqual(config["account_id"], "SIM001")
        self.assertEqual(config["initial_cash"], 500000)
        self.assertIn("commission_rate", config)
        self.assertIn("slippage", config)

    def test_config_validation_success(self):
        """测试配置验证成功"""
        config = {"cash": 100000, "commission": 0.001}

        # 应该不抛出异常
        result = BrokerConfig.validate_config(BrokerType.BACKTRADER, config)
        self.assertTrue(result)

    def test_config_validation_failure(self):
        """测试配置验证失败"""
        config = {"commission": 0.001}  # 缺少cash

        with self.assertRaises(ValueError):
            BrokerConfig.validate_config(BrokerType.BACKTRADER, config)

    def test_qmt_config_validation(self):
        """测试QMT配置验证"""
        # 有效配置
        valid_config = {"session_id": 123456, "account_id": "TEST001"}
        result = BrokerConfig.validate_config(BrokerType.QMT_LIVE, valid_config)
        self.assertTrue(result)

        # 无效配置 - 缺少session_id
        invalid_config = {"account_id": "TEST001"}
        with self.assertRaises(ValueError):
            BrokerConfig.validate_config(BrokerType.QMT_LIVE, invalid_config)

        # 无效配置 - session_id不是数字
        invalid_config2 = {"session_id": "invalid", "account_id": "TEST001"}
        with self.assertRaises(ValueError):
            BrokerConfig.validate_config(BrokerType.QMT_LIVE, invalid_config2)


class MockBroker(BaseBroker):
    """用于测试的模拟Broker"""

    def __init__(self, config):
        super().__init__(config)
        self._mock_orders = {}
        self._mock_positions = {}
        self._mock_account = None

    def connect(self):
        self.is_connected = True
        return True

    def disconnect(self):
        self.is_connected = False
        return True

    def submit_order(
        self,
        symbol,
        side,
        quantity,
        order_type=OrderType.MARKET,
        price=None,
        stop_price=None,
        **kwargs,
    ):
        order_id = f"ORDER_{len(self._mock_orders) + 1}"

        order = OrderInfo(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            status=OrderStatus.SUBMITTED,
            created_time=datetime.now(),
        )

        self._mock_orders[order_id] = order
        return order_id

    def cancel_order(self, order_id):
        if order_id in self._mock_orders:
            self._mock_orders[order_id].status = OrderStatus.CANCELED
            return True
        return False

    def get_order(self, order_id):
        return self._mock_orders.get(order_id)

    def get_orders(self, symbol=None):
        orders = list(self._mock_orders.values())
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    def get_position(self, symbol):
        return self._mock_positions.get(symbol)

    def get_positions(self):
        return list(self._mock_positions.values())

    def get_account_info(self):
        if self._mock_account is None:
            self._mock_account = AccountInfo(
                account_id="MOCK_ACCOUNT",
                total_value=100000.0,
                available_cash=50000.0,
                market_value=50000.0,
                pnl=0.0,
                pnl_percent=0.0,
            )
        return self._mock_account

    def get_current_price(self, symbol):
        return 2100.0  # 模拟价格


class TestBaseBrokerInterface(unittest.TestCase):
    """测试基础Broker接口"""

    def setUp(self):
        """设置测试"""
        self.broker = MockBroker({"test": True})
        self.broker.connect()

    def tearDown(self):
        """清理测试"""
        self.broker.disconnect()

    def test_connection(self):
        """测试连接"""
        self.assertTrue(self.broker.is_connected)

        self.broker.disconnect()
        self.assertFalse(self.broker.is_connected)

        self.broker.connect()
        self.assertTrue(self.broker.is_connected)

    def test_submit_order(self):
        """测试提交订单"""
        order_id = self.broker.submit_order(
            symbol="600519.SH",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            price=2100.0,
        )

        self.assertIsNotNone(order_id)

        order = self.broker.get_order(order_id)
        self.assertIsNotNone(order)
        self.assertEqual(order.symbol, "600519.SH")
        self.assertEqual(order.side, OrderSide.BUY)
        self.assertEqual(order.quantity, 100)
        self.assertEqual(order.price, 2100.0)
        self.assertEqual(order.status, OrderStatus.SUBMITTED)

    def test_cancel_order(self):
        """测试取消订单"""
        order_id = self.broker.submit_order("600519.SH", OrderSide.BUY, 100)

        result = self.broker.cancel_order(order_id)
        self.assertTrue(result)

        order = self.broker.get_order(order_id)
        self.assertEqual(order.status, OrderStatus.CANCELED)

    def test_get_orders(self):
        """测试获取订单列表"""
        # 提交几个订单
        order1 = self.broker.submit_order("600519.SH", OrderSide.BUY, 100)
        order2 = self.broker.submit_order("000001.SZ", OrderSide.SELL, 200)
        order3 = self.broker.submit_order("600519.SH", OrderSide.SELL, 50)

        # 获取所有订单
        all_orders = self.broker.get_orders()
        self.assertEqual(len(all_orders), 3)

        # 获取特定股票的订单
        sh_orders = self.broker.get_orders("600519.SH")
        self.assertEqual(len(sh_orders), 2)

        sz_orders = self.broker.get_orders("000001.SZ")
        self.assertEqual(len(sz_orders), 1)

    def test_account_info(self):
        """测试账户信息"""
        account = self.broker.get_account_info()

        self.assertIsNotNone(account)
        self.assertEqual(account.account_id, "MOCK_ACCOUNT")
        self.assertEqual(account.total_value, 100000.0)
        self.assertEqual(account.available_cash, 50000.0)

    def test_convenience_methods(self):
        """测试便捷方法"""
        # 测试买入
        order_id1 = self.broker.buy("600519.SH", 100, 2100.0)
        order1 = self.broker.get_order(order_id1)

        self.assertEqual(order1.side, OrderSide.BUY)
        self.assertEqual(order1.order_type, OrderType.LIMIT)
        self.assertEqual(order1.price, 2100.0)

        # 测试卖出
        order_id2 = self.broker.sell("600519.SH", 100)
        order2 = self.broker.get_order(order_id2)

        self.assertEqual(order2.side, OrderSide.SELL)
        self.assertEqual(order2.order_type, OrderType.MARKET)
        self.assertIsNone(order2.price)

    def test_portfolio_methods(self):
        """测试投资组合方法"""
        portfolio_value = self.broker.get_portfolio_value()
        self.assertEqual(portfolio_value, 100000.0)

        cash = self.broker.get_cash()
        self.assertEqual(cash, 50000.0)

        position_size = self.broker.get_position_size("600519.SH")
        self.assertEqual(position_size, 0.0)  # 没有持仓

        position_value = self.broker.get_position_value("600519.SH")
        self.assertEqual(position_value, 0.0)  # 没有持仓

    def test_context_manager(self):
        """测试上下文管理器"""
        broker = MockBroker({"test": True})

        with broker as b:
            self.assertTrue(b.is_connected)

        self.assertFalse(broker.is_connected)


def run_tests():
    """运行测试"""
    print("运行统一Broker接口测试...")

    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestBrokerDataTypes))
    suite.addTests(loader.loadTestsFromTestCase(TestBrokerFactory))
    suite.addTests(loader.loadTestsFromTestCase(TestBrokerConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestBaseBrokerInterface))

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 返回测试结果
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()

    if success:
        print("\n✅ 所有测试通过！")
    else:
        print("\n❌ 部分测试失败！")
        sys.exit(1)
