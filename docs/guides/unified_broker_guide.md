# 统一Broker接口使用指南

## 概述

统一Broker接口是一个抽象层，允许策略在不同的交易环境（BackTrader回测、QMT实盘交易、QMT模拟交易）中无缝切换，而无需修改策略代码。

## 主要特性

- **统一接口**: 所有Broker都实现相同的接口，确保策略代码的一致性
- **多环境支持**: 支持BackTrader回测、QMT实盘和模拟交易
- **类型安全**: 使用类型注解和枚举提高代码可靠性
- **配置灵活**: 支持多种配置方式，包括直接配置、配置文件、环境变量
- **便捷工厂**: 提供工厂类和便捷函数简化Broker创建

## 核心组件

### 1. 基础接口 (`BaseBroker`)

所有Broker实现都继承自`BaseBroker`，提供统一的接口：

```python
from src.broker import BaseBroker, OrderType, OrderSide

# 基本操作
broker.connect()                    # 连接
broker.submit_order(...)           # 提交订单
broker.cancel_order(order_id)      # 取消订单
broker.get_positions()             # 获取持仓
broker.get_account_info()          # 获取账户信息
broker.disconnect()                # 断开连接

# 便捷方法
broker.buy(symbol, quantity, price)    # 买入
broker.sell(symbol, quantity, price)   # 卖出
broker.close_position(symbol)          # 平仓
```

### 2. 数据类型

```python
from src.broker import OrderInfo, PositionInfo, AccountInfo

# 订单信息
order_info = OrderInfo(
    order_id="12345",
    symbol="600519.SH",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    quantity=100,
    price=2100.0,
    status=OrderStatus.FILLED
)

# 持仓信息
position_info = PositionInfo(
    symbol="600519.SH",
    side=PositionSide.LONG,
    quantity=100,
    avg_price=2100.0,
    market_value=210000.0,
    pnl=5000.0,
    pnl_percent=2.38
)

# 账户信息
account_info = AccountInfo(
    account_id="ACCOUNT001",
    total_value=1050000.0,
    available_cash=850000.0,
    market_value=200000.0,
    pnl=50000.0,
    pnl_percent=5.0
)
```

### 3. 枚举类型

```python
from src.broker import OrderType, OrderSide, OrderStatus, PositionSide

# 订单类型
OrderType.MARKET      # 市价单
OrderType.LIMIT       # 限价单
OrderType.STOP        # 止损单
OrderType.STOP_LIMIT  # 止损限价单

# 订单方向
OrderSide.BUY         # 买入
OrderSide.SELL        # 卖出

# 订单状态
OrderStatus.PENDING    # 待报
OrderStatus.SUBMITTED  # 已提交
OrderStatus.PARTIAL    # 部分成交
OrderStatus.FILLED     # 全部成交
OrderStatus.CANCELED   # 已撤销

# 持仓方向
PositionSide.LONG     # 多头
PositionSide.SHORT    # 空头
```

## Broker类型

### 1. BackTrader Broker (`BackTraderBroker`)

用于BackTrader回测环境：

```python
from src.broker import create_backtrader_broker

# 创建BackTrader Broker
broker = create_backtrader_broker(
    cash=100000,        # 初始资金
    commission=0.001,   # 手续费率
    slip_perc=0.01     # 滑点百分比
)

# 需要设置Cerebro实例
import backtrader as bt
cerebro = bt.Cerebro()
broker.set_cerebro(cerebro)
```

### 2. QMT实盘Broker (`MiniQMTLiveBroker`)

用于QMT实盘交易：

```python
from src.broker import create_qmt_live_broker

# 创建QMT实盘Broker
broker = create_qmt_live_broker(
    session_id=123456,         # QMT会话ID
    account_id="LIVE001",      # 资金账号
    account_type="STOCK",      # 账户类型
    qmt_path="C:/QMT"         # QMT路径（可选）
)
```

### 3. QMT模拟Broker (`MiniQMTSimBroker`)

用于QMT模拟交易：

```python
from src.broker import create_qmt_sim_broker

# 创建QMT模拟Broker
broker = create_qmt_sim_broker(
    session_id=123456,           # QMT会话ID
    account_id="SIM001",         # 模拟账号
    initial_cash=1000000,        # 初始资金
    commission_rate=0.0003,      # 手续费率
    slippage=0.001,             # 滑点
    sim_24h_trading=False       # 是否24小时交易
)
```

## 配置方式

### 1. 直接配置

```python
from src.broker import BrokerFactory, BrokerType

# 直接创建配置
config = {
    'session_id': 123456,
    'account_id': 'TEST001',
    'initial_cash': 500000
}

broker = BrokerFactory.create_broker(BrokerType.QMT_SIM, config)
```

### 2. 配置模板

```python
from src.broker import BrokerConfig

# 使用配置模板
config = BrokerConfig.get_qmt_sim_config(
    session_id=123456,
    account_id="SIM001",
    initial_cash=1000000,
    commission_rate=0.0003
)

broker = BrokerFactory.create_broker(BrokerType.QMT_SIM, config)
```

### 3. 配置文件

创建`broker_config.ini`文件：

```ini
[broker]
type = qmt_sim
session_id = 123456
account_id = SIM001
initial_cash = 1000000
commission_rate = 0.0003
slippage = 0.001
```

使用配置文件：

```python
broker = BrokerFactory.create_from_config_file('broker_config.ini', 'broker')
```

### 4. 环境变量

设置环境变量：

```bash
export BROKER_TYPE=qmt_sim
export BROKER_SESSION_ID=123456
export BROKER_ACCOUNT_ID=SIM001
export BROKER_INITIAL_CASH=1000000
```

使用环境变量：

```python
broker = BrokerFactory.create_from_env('BROKER_')
```

## 策略示例

### 简单均线交叉策略

```python
from src.broker import BaseBroker, OrderSide
from datetime import datetime
import numpy as np

class SimpleStrategy:
    def __init__(self, broker: BaseBroker, symbol: str = "600519.SH"):
        self.broker = broker
        self.symbol = symbol
        self.price_history = []
        self.short_ma_period = 5
        self.long_ma_period = 20

    def initialize(self):
        """初始化策略"""
        if not self.broker.connect():
            raise RuntimeError("Failed to connect to broker")

    def on_price(self, price: float):
        """处理新价格数据"""
        self.price_history.append(price)

        # 保持历史数据长度
        if len(self.price_history) > self.long_ma_period + 10:
            self.price_history = self.price_history[-self.long_ma_period-10:]

        # 检查交易信号
        signal = self.get_signal()
        if signal:
            self.execute_trade(signal)

    def get_signal(self):
        """生成交易信号"""
        if len(self.price_history) < self.long_ma_period:
            return None

        short_ma = np.mean(self.price_history[-self.short_ma_period:])
        long_ma = np.mean(self.price_history[-self.long_ma_period:])

        # 简单交叉策略
        if short_ma > long_ma and len(self.price_history) > self.long_ma_period:
            prev_short = np.mean(self.price_history[-self.short_ma_period-1:-1])
            prev_long = np.mean(self.price_history[-self.long_ma_period-1:-1])

            if prev_short <= prev_long:  # 金叉
                return 'BUY'

        return None

    def execute_trade(self, signal):
        """执行交易"""
        position_size = self.broker.get_position_size(self.symbol)

        if signal == 'BUY' and position_size == 0:
            order_id = self.broker.buy(
                symbol=self.symbol,
                quantity=100,
                price=None  # 市价单
            )
            print(f"买入订单已提交: {order_id}")

    def finalize(self):
        """策略结束"""
        account = self.broker.get_account_info()
        if account:
            print(f"最终账户价值: {account.total_value}")

        self.broker.disconnect()

# 使用示例
def main():
    # 根据需要选择不同的Broker
    # broker = create_backtrader_broker(cash=100000)
    # broker = create_qmt_live_broker(session_id=123456, account_id="LIVE001")
    broker = create_qmt_sim_broker(session_id=123456, account_id="SIM001")

    strategy = SimpleStrategy(broker)
    strategy.initialize()

    # 模拟价格数据
    prices = [2100, 2105, 2110, 2108, 2115, 2120, 2125, 2130]
    for price in prices:
        strategy.on_price(price)

    strategy.finalize()

if __name__ == "__main__":
    main()
```

## BackTrader集成

### 在BackTrader策略中使用统一Broker接口

```python
import backtrader as bt
from src.broker import create_backtrader_broker

class UnifiedBackTraderStrategy(bt.Strategy):
    def __init__(self):
        # 创建统一Broker接口
        self.unified_broker = create_backtrader_broker(
            cash=self.broker.getcash(),
            commission=0.001
        )
        self.unified_broker.set_cerebro(self.cerebro)
        self.unified_broker.connect()

        # BackTrader指标
        self.sma = bt.indicators.SimpleMovingAverage(period=20)

    def next(self):
        """策略逻辑"""
        # 使用统一接口获取信息
        account = self.unified_broker.get_account_info()
        position = self.unified_broker.get_position_size(self.data._name)

        # 交易逻辑
        if not self.position and self.data.close[0] > self.sma[0]:
            # 使用统一接口下单
            order_id = self.unified_broker.buy(
                symbol=self.data._name,
                quantity=100
            )

    def stop(self):
        """策略结束"""
        self.unified_broker.disconnect()
```

## 错误处理

```python
from src.broker import BrokerFactory, BrokerType
import logging

def create_broker_with_error_handling():
    try:
        broker = BrokerFactory.create_broker(
            BrokerType.QMT_LIVE,
            {
                'session_id': 123456,
                'account_id': 'LIVE001'
            }
        )

        if not broker.connect():
            logging.error("Failed to connect to broker")
            return None

        return broker

    except ImportError:
        logging.error("QMT SDK not available")
        return None
    except Exception as e:
        logging.error(f"Failed to create broker: {e}")
        return None

def safe_order_submission(broker, symbol, quantity):
    try:
        order_id = broker.buy(symbol=symbol, quantity=quantity)

        # 检查订单状态
        order_info = broker.get_order(order_id)
        if order_info and order_info.status == OrderStatus.REJECTED:
            logging.error(f"Order rejected: {order_id}")
            return None

        return order_id

    except Exception as e:
        logging.error(f"Order submission failed: {e}")
        return None
```

## 最佳实践

### 1. 环境切换

```python
import os
from src.broker import BrokerFactory, BrokerType

def create_broker_by_environment():
    """根据环境变量选择Broker类型"""
    env = os.getenv('TRADING_ENV', 'backtest')

    if env == 'backtest':
        return BrokerFactory.create_broker(
            BrokerType.BACKTRADER,
            {'cash': 100000, 'commission': 0.001}
        )
    elif env == 'simulation':
        return BrokerFactory.create_broker(
            BrokerType.QMT_SIM,
            {
                'session_id': int(os.getenv('QMT_SESSION_ID')),
                'account_id': os.getenv('QMT_ACCOUNT_ID'),
                'initial_cash': 1000000
            }
        )
    elif env == 'live':
        return BrokerFactory.create_broker(
            BrokerType.QMT_LIVE,
            {
                'session_id': int(os.getenv('QMT_SESSION_ID')),
                'account_id': os.getenv('QMT_ACCOUNT_ID')
            }
        )
    else:
        raise ValueError(f"Unknown trading environment: {env}")
```

### 2. 资源管理

```python
from src.broker import BaseBroker

def run_strategy_with_context_manager(broker: BaseBroker):
    """使用上下文管理器确保资源正确释放"""
    with broker:  # 自动连接和断开
        # 策略逻辑
        account = broker.get_account_info()
        print(f"账户价值: {account.total_value}")

        # 执行交易
        order_id = broker.buy("600519.SH", 100)

        # 监控订单
        order_info = broker.get_order(order_id)
        print(f"订单状态: {order_info.status}")
```

### 3. 配置验证

```python
from src.broker import BrokerConfig, BrokerType

def validate_and_create_broker(broker_type, config):
    """验证配置后创建Broker"""
    try:
        # 验证配置
        BrokerConfig.validate_config(broker_type, config)

        # 创建Broker
        broker = BrokerFactory.create_broker(broker_type, config)

        return broker

    except ValueError as e:
        print(f"配置验证失败: {e}")
        return None
    except Exception as e:
        print(f"Broker创建失败: {e}")
        return None
```

## 注意事项

1. **QMT依赖**: QMT相关的Broker需要安装xtquant SDK
2. **会话管理**: QMT Broker需要有效的会话ID和账户ID
3. **实盘风险**: 实盘交易会产生真实的交易，请谨慎使用
4. **资源释放**: 使用完毕后记得调用`disconnect()`释放资源
5. **异常处理**: 网络问题、API限制等可能导致操作失败，需要适当的错误处理

## 扩展性

如果需要支持新的交易平台，可以继承`BaseBroker`实现新的Broker类：

```python
from src.broker import BaseBroker

class CustomBroker(BaseBroker):
    def __init__(self, config):
        super().__init__(config)
        # 自定义初始化

    def connect(self):
        # 实现连接逻辑
        pass

    def submit_order(self, symbol, side, quantity, order_type, price, **kwargs):
        # 实现订单提交逻辑
        pass

    # 实现其他必需方法...

# 注册到工厂
from src.broker import BrokerFactory, BrokerType

# 定义新的Broker类型
class CustomBrokerType(Enum):
    CUSTOM = "custom"

# 注册
BrokerFactory.register_broker_class(CustomBrokerType.CUSTOM, CustomBroker)
```
