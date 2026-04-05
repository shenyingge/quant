# 市场数据格式规范

本文档说明策略在回测和QMT实盘交易中接收的市场数据格式。

## 1. 数据源类型

### 1.1 回测数据
- **数据源**: 历史行情数据（Tushare、Wind等）
- **频率**: 分钟级、日级
- **格式**: pandas DataFrame

### 1.2 QMT实盘数据
- **数据源**: QMT实时行情推送
- **频率**: 实时Tick、分钟K线
- **格式**: pandas DataFrame（统一格式）

## 2. DataFrame格式规范

### 2.1 基础行情数据格式

所有传入策略的市场数据都应该是pandas DataFrame，包含以下标准列：

```python
import pandas as pd
from datetime import datetime

# 示例数据格式
market_data = pd.DataFrame({
    'datetime': pd.to_datetime([
        '2024-01-02 09:30:00',
        '2024-01-02 09:31:00',
        '2024-01-02 09:32:00'
    ]),
    'open': [10.50, 10.52, 10.51],      # 开盘价
    'high': [10.55, 10.54, 10.53],      # 最高价
    'low': [10.48, 10.50, 10.49],       # 最低价
    'close': [10.52, 10.51, 10.52],     # 收盘价
    'volume': [1000000, 800000, 1200000], # 成交量（股）
    'amount': [10520000, 8408000, 12624000], # 成交额（元）
})

# 设置datetime为索引
market_data.set_index('datetime', inplace=True)
```

### 2.2 必需字段

| 字段名 | 类型 | 说明 | 单位 |
|--------|------|------|------|
| `datetime` | datetime64 | 时间戳（索引） | - |
| `open` | float | 开盘价 | 元 |
| `high` | float | 最高价 | 元 |
| `low` | float | 最低价 | 元 |
| `close` | float | 收盘价 | 元 |
| `volume` | int64 | 成交量 | 股 |
| `amount` | float | 成交额 | 元 |

### 2.3 可选字段

| 字段名 | 类型 | 说明 | 用途 |
|--------|------|------|------|
| `pre_close` | float | 前收盘价 | 计算涨跌幅 |
| `high_limit` | float | 涨停价 | 涨停判断 |
| `low_limit` | float | 跌停价 | 跌停判断 |
| `turnover_rate` | float | 换手率 | 流动性分析 |
| `pe_ratio` | float | 市盈率 | 基本面分析 |
| `pb_ratio` | float | 市净率 | 基本面分析 |

## 3. 时间格式规范

### 3.1 回测时间格式

```python
# 标准格式：北京时间
datetime_format = "YYYY-MM-DD HH:MM:SS"

# 示例
examples = [
    "2024-01-02 09:30:00",  # 开盘
    "2024-01-02 11:30:00",  # 上午收盘
    "2024-01-02 13:00:00",  # 下午开盘
    "2024-01-02 15:00:00",  # 收盘
]
```

### 3.2 交易时间段

```python
# A股交易时间
TRADING_SESSIONS = {
    "morning": ("09:30", "11:30"),    # 上午交易
    "afternoon": ("13:00", "15:00"),  # 下午交易
}

# 集合竞价时间
AUCTION_SESSIONS = {
    "morning_auction": ("09:15", "09:25"),  # 开盘集合竞价
    "afternoon_auction": ("14:57", "15:00"), # 收盘集合竞价
}
```

## 4. 策略数据接收接口

### 4.1 on_market_data回调

策略通过`on_market_data`方法接收行情数据：

```python
def on_market_data(self, symbol: str, data: pd.DataFrame) -> None:
    """
    市场数据更新回调

    Args:
        symbol: 股票代码，如 "000001.SZ", "600036.SH"
        data: 市场数据DataFrame，格式如上所述
    """
    # 数据校验
    required_columns = ['open', 'high', 'low', 'close', 'volume', 'amount']
    if not all(col in data.columns for col in required_columns):
        self.logger.error(f"行情数据缺少必需字段", symbol=symbol,
                         missing=set(required_columns) - set(data.columns))
        return

    # 存储数据
    self.market_data[symbol] = data

    # 更新当前价格
    if not data.empty:
        self.current_prices[symbol] = data['close'].iloc[-1]
```

### 4.2 数据存储格式

策略内部存储格式：

```python
# 策略内部的数据存储
self.market_data: Dict[str, pd.DataFrame] = {
    "000001.SZ": DataFrame,  # 平安银行行情数据
    "600036.SH": DataFrame,  # 招商银行行情数据
    # ...
}

# 当前价格缓存
self.current_prices: Dict[str, float] = {
    "000001.SZ": 12.35,
    "600036.SH": 45.67,
    # ...
}
```

## 5. 基本面数据格式

### 5.1 基本面数据结构

基本面数据通过`update_fundamental_data`方法传入：

```python
# 基本面数据示例
fundamental_data = pd.DataFrame({
    'datetime': pd.to_datetime(['2024-01-01', '2024-04-01', '2024-07-01']),
    'pe': [15.5, 16.2, 14.8],                    # 市盈率
    'pb': [1.2, 1.3, 1.1],                      # 市净率
    'roa': [0.08, 0.09, 0.07],                  # 总资产收益率
    'roe': [0.15, 0.16, 0.14],                  # 净资产收益率
    'current_ratio': [1.8, 1.9, 1.7],           # 流动比率
    'debt_to_assets': [0.4, 0.42, 0.38],        # 资产负债率
    'retained_earnings_per_share': [2.5, 2.8, 2.3], # 每股留存收益
    'circulating_market_cap': [50e8, 52e8, 48e8],   # 流通市值
    'gross_margin': [0.25, 0.27, 0.24],         # 毛利率
})

fundamental_data.set_index('datetime', inplace=True)
```

### 5.2 基本面字段说明

| 字段名 | 说明 | 单位 | 用途 |
|--------|------|------|------|
| `pe` | 市盈率 | 倍 | 估值分析 |
| `pb` | 市净率 | 倍 | 估值分析 |
| `roa` | 总资产收益率 | 小数 | 盈利能力 |
| `roe` | 净资产收益率 | 小数 | 盈利能力 |
| `current_ratio` | 流动比率 | 倍 | 流动性分析 |
| `debt_to_assets` | 资产负债率 | 小数 | 财务健康度 |
| `retained_earnings_per_share` | 每股留存收益 | 元 | 成长性分析 |
| `circulating_market_cap` | 流通市值 | 元 | 规模分析 |
| `gross_margin` | 毛利率 | 小数 | 盈利质量 |

## 6. QMT实盘数据转换

### 6.1 QMT数据转换函数

```python
def convert_qmt_to_standard(qmt_data: dict) -> pd.DataFrame:
    """
    将QMT行情数据转换为标准格式

    Args:
        qmt_data: QMT原始数据

    Returns:
        标准格式的DataFrame
    """
    # QMT数据字段映射
    field_mapping = {
        'time': 'datetime',
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'lastPrice': 'close',
        'volume': 'volume',
        'turnover': 'amount',
        'preClose': 'pre_close',
        'upperLimit': 'high_limit',
        'lowerLimit': 'low_limit',
    }

    # 转换数据
    converted_data = {}
    for qmt_field, std_field in field_mapping.items():
        if qmt_field in qmt_data:
            converted_data[std_field] = qmt_data[qmt_field]

    # 创建DataFrame
    df = pd.DataFrame([converted_data])

    # 处理时间字段
    if 'datetime' in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index('datetime', inplace=True)

    return df
```

### 6.2 实时数据推送处理

```python
class StrategyEngine:
    """策略引擎示例"""

    def on_qmt_tick(self, symbol: str, tick_data: dict):
        """处理QMT实时tick数据"""
        # 转换为标准格式
        standard_data = convert_qmt_to_standard(tick_data)

        # 推送给策略
        for strategy in self.strategies:
            strategy.on_market_data(symbol, standard_data)

    def on_qmt_kline(self, symbol: str, kline_data: dict):
        """处理QMT K线数据"""
        # 转换为标准格式
        standard_data = convert_qmt_to_standard(kline_data)

        # 推送给策略
        for strategy in self.strategies:
            strategy.on_market_data(symbol, standard_data)
```

## 7. 数据质量检查

### 7.1 数据完整性检查

```python
def validate_market_data(data: pd.DataFrame, symbol: str) -> bool:
    """
    验证市场数据完整性

    Args:
        data: 市场数据
        symbol: 股票代码

    Returns:
        是否通过验证
    """
    # 检查必需字段
    required_fields = ['open', 'high', 'low', 'close', 'volume', 'amount']
    missing_fields = set(required_fields) - set(data.columns)
    if missing_fields:
        logger.error(f"数据缺少必需字段", symbol=symbol, missing=missing_fields)
        return False

    # 检查数据类型
    if not pd.api.types.is_datetime64_any_dtype(data.index):
        logger.error(f"时间索引类型错误", symbol=symbol)
        return False

    # 检查价格逻辑
    invalid_rows = data[(data['high'] < data['low']) |
                       (data['close'] < data['low']) |
                       (data['close'] > data['high'])]
    if not invalid_rows.empty:
        logger.warning(f"发现价格逻辑错误", symbol=symbol, count=len(invalid_rows))

    # 检查负值
    price_cols = ['open', 'high', 'low', 'close']
    negative_prices = data[price_cols] <= 0
    if negative_prices.any().any():
        logger.warning(f"发现负价格或零价格", symbol=symbol)

    return True
```

### 7.2 数据时间对齐

```python
def align_data_timestamps(data: pd.DataFrame) -> pd.DataFrame:
    """
    对齐数据时间戳到交易时间

    Args:
        data: 原始数据

    Returns:
        对齐后的数据
    """
    # 过滤交易时间
    trading_mask = (
        ((data.index.time >= pd.to_datetime("09:30").time()) &
         (data.index.time <= pd.to_datetime("11:30").time())) |
        ((data.index.time >= pd.to_datetime("13:00").time()) &
         (data.index.time <= pd.to_datetime("15:00").time()))
    )

    return data[trading_mask]
```

## 8. 使用示例

### 8.1 完整示例：板块轮动策略

```python
# 在策略中使用标准格式数据
class SectorRotationStrategy(FundamentalStrategy):

    def on_market_data(self, symbol: str, data: pd.DataFrame):
        """接收标准格式的市场数据"""
        # 数据验证
        if not validate_market_data(data, symbol):
            return

        # 时间对齐
        aligned_data = align_data_timestamps(data)

        # 存储数据
        self.market_data[symbol] = aligned_data

        # 更新当前价格
        if not aligned_data.empty:
            self.current_prices[symbol] = aligned_data['close'].iloc[-1]

        self.logger.debug("接收市场数据",
                         symbol=symbol,
                         data_points=len(aligned_data),
                         latest_price=self.current_prices.get(symbol))
```

### 8.2 回测数据加载示例

```python
def load_backtest_data(symbols: List[str], start_date: str, end_date: str):
    """加载回测数据"""
    market_data = {}

    for symbol in symbols:
        # 从数据源加载（示例使用tushare）
        df = ts.get_hist_data(
            symbol,
            start=start_date,
            end=end_date,
            ktype='1'  # 1分钟数据
        )

        # 转换为标准格式
        standard_df = convert_to_standard_format(df)
        market_data[symbol] = standard_df

    return market_data
```

## 9. 注意事项

### 9.1 性能优化
- 避免在`on_market_data`中执行耗时操作
- 使用增量数据更新而非全量替换
- 合理设置数据缓存大小

### 9.2 内存管理
- 定期清理历史数据
- 使用滑动窗口保存必要的历史数据
- 避免重复存储相同数据

### 9.3 异常处理
- 处理网络连接中断
- 处理数据格式异常
- 处理时间戳不连续的情况

### 9.4 时区处理
- 统一使用北京时间（UTC+8）
- 注意夏令时对海外市场的影响
- 回测与实盘时间保持一致

---

**更新日期**: 2024-12-26
**版本**: v1.0
**维护者**: s-quant开发团队
