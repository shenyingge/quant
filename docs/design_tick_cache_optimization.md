# T+0 策略行情更新优化方案

## 问题描述

配置了 `T0_POLL_INTERVAL_SECONDS=5` 和 `T0_INTRADAY_BAR_PERIOD=5s`，期望每5秒更新一次。
但实际更新远慢于5秒，因为 `StrategyEngine.run_once()` 每次执行都做了大量重复数据拉取。

## 瓶颈分析

每次 `run_once()` 调用链：

1. `fetch_minute_data()` → `_fetch_minute_data_from_local_cache()` 调用 `xtdata.download_history_data()`（网络下载）
   + `_fetch_recent_tick_data()` 拉取 20000 条 tick → 聚合成5s K线
2. `fetch_daily_data()` → 有1小时内存缓存，首次后OK
3. `_warn_if_minute_data_is_stale()` → 调用 `fetch_realtime_snapshot()`（第1次）
4. `run_once()` 第69行 → 再次调用 `fetch_realtime_snapshot()`（第2次，重复）
5. `_finalize_signal_card()` → 每次都发飞书通知（网络请求）

## Redis 环境约束

- 现有 Redis: `10.0.12.2:30102`，db 0 用于交易信号和交易记录
- tick 缓存必须使用独立的 db（db 1），不能和下单系统共用

## 实施方案

### 1. 新建 Redis Tick 缓存客户端

**新文件:** `src/strategy/tick_cache.py`

创建独立的 Redis tick 缓存客户端，使用 db 1：

```python
class RedisTickCache:
    """Redis tick数据缓存，使用独立db避免影响交易系统"""

    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            db=settings.redis_tick_cache_db,  # db=1，独立于交易db=0
            decode_responses=False,  # 二进制存储，性能更好
            socket_connect_timeout=3,
            socket_timeout=3,
        )

    def get_cached_ticks(self, stock_code: str, trade_date: date) -> Optional[pd.DataFrame]
    def save_ticks(self, stock_code: str, trade_date: date, df: pd.DataFrame) -> None
    def get_last_tick_time(self, stock_code: str, trade_date: date) -> Optional[datetime]
```

**缓存策略:**
- Key 格式: `tick:{stock_code}:{trade_date}` → 存储序列化的 DataFrame（pickle）
- Key 格式: `tick_meta:{stock_code}:{trade_date}` → 存储最后一条 tick 的时间戳
- TTL: 配置项 `REDIS_TICK_CACHE_TTL`，默认 28800 秒（8小时，覆盖一个交易日）
- 每次只追加新 tick，不重写全量

### 2. 添加配置项

**文件:** `src/config.py` (第25行附近)

```python
redis_tick_cache_db: int = Field(default=1, env="REDIS_TICK_CACHE_DB")
redis_tick_cache_ttl: int = Field(default=28800, env="REDIS_TICK_CACHE_TTL")
```

**文件:** `.env.example` 添加：

```bash
# Redis Tick缓存配置（使用独立db，不影响交易系统）
REDIS_TICK_CACHE_DB=1
REDIS_TICK_CACHE_TTL=28800
```

### 3. 改造 DataFetcher 使用 Redis 缓存

**文件:** `src/strategy/data_fetcher.py`

**3a. `__init__()` (第27行):**
- 引入 `RedisTickCache` 实例
- 添加快照缓存变量 `_snapshot_cache` / `_snapshot_cache_time`

**3b. `_fetch_recent_tick_data()` (第114行) — 核心改造:**

改为增量拉取逻辑：

```
1. 从 Redis 读取已缓存的 tick DataFrame
2. 如果有缓存：
   - 获取缓存中最后一条 tick 的时间戳
   - 只拉取少量最新 tick（count=500）
   - 过滤出时间戳 > 缓存最后时间的新 tick
   - 追加到缓存 DataFrame，去重
   - 写回 Redis
3. 如果无缓存（首次/新交易日）：
   - 全量拉取 20000 条 tick
   - 写入 Redis 缓存
4. 返回完整 tick DataFrame
```

**3c. `fetch_minute_data()` (第35行):**
- 添加 `realtime: bool = False` 参数
- 当 `realtime=True` 时，跳过 `_fetch_minute_data_from_local_cache()`（避免 `download_history_data` 网络下载）
- 只走 `_fetch_recent_minute_data()` 路径

**3d. `fetch_realtime_snapshot()` (第200行):**
- 添加短 TTL 内存缓存（同一轮询周期内复用）
- 缓存有效期 = `settings.t0_poll_interval_seconds` 秒

**3e. `_warn_if_minute_data_is_stale()` (第477行):**
- 改为接受 `snapshot` 参数，不再内部调用 `fetch_realtime_snapshot()`

### 4. 改造 StrategyEngine

**文件:** `src/strategy/strategy_engine.py`

**4a. `run_once()` (第35行):**
- 调用 `fetch_minute_data(stock_code, trade_date, realtime=True)`
- 添加 `time.time()` 计时，记录执行耗时

**4b. `_finalize_signal_card()` (第172行):**
- 添加 `self._last_notified_action` 实例变量
- 只在信号动作变化时发送飞书通知

## 修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/strategy/tick_cache.py` | 新建 | Redis tick 缓存客户端 |
| `src/config.py` | 修改 | 添加 `redis_tick_cache_db`, `redis_tick_cache_ttl` |
| `src/strategy/data_fetcher.py` | 修改 | 增量 tick 拉取、跳过 download、快照缓存 |
| `src/strategy/strategy_engine.py` | 修改 | realtime 模式、条件通知、性能日志 |
| `.env.example` | 修改 | 添加新配置项 |

## 安全保障

- tick 缓存使用 Redis db 1，交易信号/记录在 db 0，完全隔离
- `RedisTickCache` 连接失败时静默降级，回退到全量拉取（不影响实盘）
- `realtime=False` 为默认值，现有调用方（如 backtest）行为不变
- 飞书通知条件化只影响 observe 信号的重复发送，action 变化时仍然通知

## 验证方式

1. 启动 `python main.py t0-daemon`，观察日志中 "耗时" 字段，应 < 3秒
2. 检查 `output/live_signal_card.json` 的 `as_of_time` 间隔，应接近5秒
3. 用 `redis-cli -n 1 keys "tick:*"` 确认 tick 缓存写入正常
4. 确认飞书只在信号变化时收到通知
