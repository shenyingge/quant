# Quick Roll 策略 - 牛市板块快速轮动

基于聚宽平台的板块轮动策略，实盘版本通过 Redis 发送交易信号。

## 策略说明

### 核心逻辑
- **选股周期**：每周一调仓
- **持仓数量**：最多 10 只
- **选股因子**：ROA、留存收益、非线性市值
- **止损机制**：跌幅超过 10% 触发止损
- **涨停处理**：11:00 检查涨停板，打开则卖出

### 文件说明

```
quick_roll/
├── quick_roll.py           # 原始策略（回测用）
├── quick_roll_live.py      # 实盘策略（Redis 信号版本）
├── redis_signal_sender.py  # Redis 信号发送模块
└── README.md              # 本文档
```

## 使用方法

### 1. 回测模式

使用 `quick_roll.py`，正常在聚宽平台运行即可。

### 2. 实盘模式

使用 `quick_roll_live.py`，需要配置以下内容：

#### 环境变量配置（.env）
```env
# Redis 配置
REDIS_HOST=10.0.12.2
REDIS_PORT=30102
REDIS_SIGNAL_CHANNEL=trading_signals
REDIS_TRADE_RECORDS_PREFIX=trade_record:
```

#### 策略配置
```python
# 在 initialize 函数中设置
g.is_live_trading = True  # 开启实盘模式
```

### 3. 实盘运行流程

```
9:05  -> 准备股票池
9:40  -> 周一执行调仓（发送买卖信号到 Redis）
11:00 -> 检查涨停板
14:30 -> 止损检查
15:10 -> 从 Redis 读取实际成交记录，更新虚拟持仓
15:20 -> 打印持仓信息
```

## 实盘特性

### 1. Redis 信号发送

当策略需要下单时，会发送 JSON 格式的信号到 Redis：

```json
{
    "signal_id": "quick_roll_20250810_094000_abc123",
    "stock_code": "000001",
    "direction": "BUY",
    "volume": 1000,
    "price": 10.50,
    "order_type": 23,
    "strategy_name": "quick_roll",
    "extra": {
        "target_value": 10000,
        "strategy": "牛市板块快速轮动"
    }
}
```

### 2. 虚拟持仓管理

实盘模式下，策略维护虚拟持仓 `g.virtual_positions`：
- 发送买入信号时，预先记录虚拟持仓
- 15:10 从 Redis 读取实际成交，更新为真实数据
- 未成交的信号会被清理

### 3. 成交记录更新

每天 15:10 执行 `update_from_redis`：
1. 从 Redis 获取当日所有成交记录
2. 根据 signal_id 匹配原始信号
3. 更新虚拟持仓的成交价格和数量
4. 清理未成交的虚拟持仓

### 4. 状态同步

虚拟持仓状态：
- `pending: True` - 待成交（今日发出信号但未确认）
- `pending: False` - 已成交（确认成交或从 Redis 同步的昨日持仓）
- `signal_id: None` - 昨日持仓（从 Redis 同步，无今日信号）

## 与 QMT 交易服务配合

### 工作流程

1. **策略发信号** -> Redis 频道
2. **QMT 服务监听** -> 接收信号
3. **QMT 执行交易** -> 实际下单
4. **QMT 记录成交** -> 存入 Redis
5. **策略读取成交** -> 更新持仓

### 部署架构

```
聚宽策略 (quick_roll_live.py)
    ↓ 发送信号
Redis Server
    ↓ 监听信号
QMT 交易服务 (main.py)
    ↓ 执行交易
QMT 客户端
    ↓ 返回成交
Redis (trade_records)
    ↓ 读取成交
聚宽策略 (15:10 更新)
```

## 注意事项

1. **时间同步**：确保聚宽和 QMT 服务器时间一致
2. **Redis 连接**：确保 Redis 服务稳定可访问
3. **信号去重**：signal_id 包含时间戳和 UUID，避免重复
4. **持仓同步**：9:05 从 Redis 同步昨日持仓，避免聚宽和 QMT 数据不一致
5. **成交确认**：15:10 只处理今日信号的成交情况
6. **未成交处理**：未成交的今日信号会被自动清理
7. **代码格式转换**：自动处理聚宽格式（如 000001.XSHE）和 QMT 格式（如 000001.SZ）的转换

## 监控和调试

### 查看 Redis 信号
```bash
redis-cli -h 10.0.12.2 -p 30102
> SUBSCRIBE trading_signals
```

### 查看成交记录
```bash
redis-cli -h 10.0.12.2 -p 30102
> KEYS trade_record:*
> GET trade_record:ORDER_ID_TRADE_ID
```

### 日志位置
- 策略日志：聚宽平台查看
- QMT 服务日志：`logs/trading_service.log`
- 任务执行日志：`logs/task_execution.log`

## 风险提示

1. **网络延迟**：Redis 信号传输可能有延迟
2. **成交差异**：实际成交价格可能与发送价格不同
3. **部分成交**：可能出现部分成交的情况
4. **系统故障**：任一环节故障都会影响交易

## 版本历史

- 2025-08-01：原始版本，集成飞书通知
- 2025-08-10：实盘版本，支持 Redis 信号发送和成交同步
- 2025-08-11：增加 9:05 持仓同步，避免聚宽和 QMT 数据不一致
- 2025-08-11：增加股票代码格式自动转换（聚宽 <-> QMT）