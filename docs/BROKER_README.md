# 统一Broker接口

## 项目概述

统一Broker接口是一个抽象化的交易执行层，允许策略在不同的交易环境（BackTrader回测、MiniQMT实盘交易、MiniQMT模拟交易）中无缝切换，而无需修改策略代码。

## 核心特性

- ✅ **统一接口**: 所有Broker都实现相同的接口，确保策略代码的一致性
- ✅ **多环境支持**: 支持BackTrader回测、MiniQMT实盘和模拟交易
- ✅ **类型安全**: 使用类型注解和枚举提高代码可靠性
- ✅ **配置灵活**: 支持直接配置、配置文件、环境变量等多种配置方式
- ✅ **便捷工厂**: 提供工厂类和便捷函数简化Broker创建
- ✅ **完整测试**: 包含全面的单元测试和使用示例

## 架构设计

```
src/broker/
├── __init__.py                 # 统一导出
├── base_broker.py             # 抽象基类和数据类型
├── backtrader_broker.py       # BackTrader适配器
├── miniqmt_live_broker.py     # MiniQMT实盘适配器
├── miniqmt_sim_broker.py      # MiniQMT模拟适配器
└── broker_factory.py          # 工厂类和配置管理

examples/
├── universal_strategy_example.py   # 通用策略示例
├── backtrader_strategy_example.py  # BackTrader集成示例
├── config_examples.py             # 配置示例
└── simple_demo.py                 # 简单演示

tests/
└── test_unified_broker.py      # 单元测试

docs/
└── unified_broker_guide.md     # 详细使用指南
```

## 快速开始

### 1. 基本使用

```python
from src.broker import create_qmt_sim_broker, OrderSide

# 创建QMT模拟Broker
broker = create_qmt_sim_broker(
    session_id=123456,
    account_id="SIM001",
    initial_cash=1000000
)

# 连接并使用
with broker:
    # 买入股票
    order_id = broker.buy("600519.SH", 100, 2100.0)

    # 查询账户
    account = broker.get_account_info()
    print(f"总资产: {account.total_value}")

    # 查询订单
    orders = broker.get_orders()
    print(f"订单数: {len(orders)}")
```

### 2. 环境切换

```python
# 方法1：根据环境变量选择
import os

env = os.getenv('TRADING_ENV', 'simulation')

if env == 'backtest':
    broker = create_backtrader_broker(cash=100000)
elif env == 'simulation':
    broker = create_qmt_sim_broker(session_id=123456, account_id="SIM001")
elif env == 'live':
    broker = create_qmt_live_broker(session_id=123456, account_id="LIVE001")

# 方法2：使用工厂模式
from src.broker import BrokerFactory, BrokerType

broker = BrokerFactory.create_broker(
    BrokerType.QMT_SIM,
    {'session_id': 123456, 'account_id': 'SIM001'}
)
```

### 3. 策略示例

```python
class SimpleStrategy:
    def __init__(self, broker):
        self.broker = broker

    def run(self):
        # 策略逻辑与Broker类型无关
        account = self.broker.get_account_info()

        if account.available_cash > 10000:
            order_id = self.broker.buy("600519.SH", 100)
            print(f"买入订单: {order_id}")

# 同一策略可以在不同环境运行
# strategy = SimpleStrategy(backtrader_broker)    # 回测
# strategy = SimpleStrategy(qmt_sim_broker)       # 模拟
# strategy = SimpleStrategy(qmt_live_broker)      # 实盘
```

## 支持的Broker类型

| Broker类型 | 环境 | 依赖 | 状态 |
|-----------|------|------|------|
| BackTraderBroker | 回测 | backtrader | ✅ 已实现 |
| MiniQMTLiveBroker | 实盘 | xtquant | ✅ 已实现 |
| MiniQMTSimBroker | 模拟 | xtquant | ✅ 已实现 |

## 核心接口

### BaseBroker抽象接口

```python
# 连接管理
broker.connect() -> bool
broker.disconnect() -> bool

# 订单管理
broker.submit_order(symbol, side, quantity, order_type, price) -> str
broker.cancel_order(order_id) -> bool
broker.get_order(order_id) -> OrderInfo
broker.get_orders(symbol=None) -> List[OrderInfo]

# 持仓管理
broker.get_position(symbol) -> PositionInfo
broker.get_positions() -> List[PositionInfo]

# 账户管理
broker.get_account_info() -> AccountInfo
broker.get_current_price(symbol) -> float

# 便捷方法
broker.buy(symbol, quantity, price=None) -> str
broker.sell(symbol, quantity, price=None) -> str
broker.close_position(symbol, price=None) -> str
```

### 数据类型

```python
# 订单信息
@dataclass
class OrderInfo:
    order_id: str
    symbol: str
    side: OrderSide          # BUY, SELL
    order_type: OrderType    # MARKET, LIMIT, STOP, STOP_LIMIT
    quantity: float
    price: Optional[float]
    status: OrderStatus      # PENDING, SUBMITTED, FILLED, CANCELED
    # ... 更多字段

# 持仓信息
@dataclass
class PositionInfo:
    symbol: str
    side: PositionSide       # LONG, SHORT
    quantity: float
    avg_price: float
    market_value: float
    pnl: float
    pnl_percent: float

# 账户信息
@dataclass
class AccountInfo:
    account_id: str
    total_value: float
    available_cash: float
    market_value: float
    pnl: float
    pnl_percent: float
```

## 配置方式

### 1. 直接配置

```python
config = {
    'session_id': 123456,
    'account_id': 'SIM001',
    'initial_cash': 1000000
}
broker = BrokerFactory.create_broker(BrokerType.QMT_SIM, config)
```

### 2. 配置模板

```python
config = BrokerConfig.get_qmt_sim_config(
    session_id=123456,
    account_id="SIM001",
    initial_cash=500000
)
broker = BrokerFactory.create_broker(BrokerType.QMT_SIM, config)
```

### 3. 配置文件

```ini
[broker]
type = qmt_sim
session_id = 123456
account_id = SIM001
initial_cash = 1000000
```

```python
broker = BrokerFactory.create_from_config_file('config.ini', 'broker')
```

### 4. 环境变量

```bash
export BROKER_TYPE=qmt_sim
export BROKER_SESSION_ID=123456
export BROKER_ACCOUNT_ID=SIM001
```

```python
broker = BrokerFactory.create_from_env('BROKER_')
```

## 运行测试

```bash
# 运行单元测试
uv run python tests/test_unified_broker.py

# 运行演示
uv run python examples/simple_demo.py

# 运行配置示例
uv run python examples/config_examples.py
```

## 依赖安装

```bash
# BackTrader支持
pip install backtrader

# MiniQMT支持（需要从官方获取）
# 安装xtquant SDK
```

## 扩展性

系统设计为可扩展的，可以轻松添加新的Broker支持：

```python
from src.broker import BaseBroker, BrokerFactory

class CustomBroker(BaseBroker):
    def connect(self):
        # 实现连接逻辑
        pass

    def submit_order(self, ...):
        # 实现订单提交逻辑
        pass

    # 实现其他必需方法...

# 注册新Broker
BrokerFactory.register_broker_class(BrokerType.CUSTOM, CustomBroker)
```

## 最佳实践

1. **环境隔离**: 使用环境变量区分开发/测试/生产环境
2. **配置验证**: 使用`BrokerConfig.validate_config()`验证配置
3. **资源管理**: 使用上下文管理器确保连接正确关闭
4. **错误处理**: 妥善处理网络异常、API限制等错误
5. **日志记录**: 记录关键操作和错误信息

## 注意事项

- **实盘风险**: 实盘交易会产生真实的资金损失，请谨慎使用
- **依赖管理**: 某些Broker需要特定的SDK，缺失时会抛出ImportError
- **会话管理**: QMT Broker需要有效的会话ID和账户配置
- **数据权限**: 某些功能可能需要特定的数据权限

## 技术支持

- 详细文档: `docs/unified_broker_guide.md`
- 示例代码: `examples/` 目录
- 单元测试: `tests/test_unified_broker.py`

## 更新日志

### v1.0.0 (2024-08-24)
- ✅ 实现统一Broker抽象接口
- ✅ 支持BackTrader、MiniQMT实盘、MiniQMT模拟
- ✅ 完整的工厂模式和配置系统
- ✅ 全面的测试覆盖和文档
- ✅ 多种使用示例和演示

---

通过统一Broker接口，你的策略代码可以在不同环境间无缝切换，大大提高了代码的复用性和可维护性！
