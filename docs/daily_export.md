# 每日持仓与成交记录导出

## 功能说明

每日收盘后从 QMT 查询当日持仓和委托成交数据：
- CSV 文件导出到 `data/daily_export/` 目录
- 通过 SCP 上传到 NS 主机 (`~/data/trade/YYYYMMDD/`)

## 使用方式

```bash
# 手动执行导出
uv run python main.py export-daily
```

服务运行时自动调度于每天 15:20 执行导出。

## 导出文件

### positions_YYYYMMDD.csv — 持仓数据

| 字段 | 说明 |
|------|------|
| stock_code | 股票代码 |
| volume | 持仓数量 |
| can_use_volume | 可用数量 |
| avg_price | 成本价 |
| last_price | 最新价 |
| market_value | 市值 |
| float_profit | 浮动盈亏 |
| profit_rate | 盈亏比例 |

### trades_YYYYMMDD.csv — 委托成交数据

| 字段 | 说明 |
|------|------|
| order_id | 委托编号 |
| stock_code | 股票代码 |
| order_type | 委托类型 |
| order_volume | 委托数量 |
| price | 委托价格 |
| traded_volume | 成交数量 |
| traded_price | 成交价格 |
| order_status | 委托状态码 |
| order_time | 委托时间 |
| status_desc | 状态描述 |

## SCP 上传

导出完成后自动通过 `scp` 命令上传到 NS 主机，按日期子目录组织。

### 远程目录结构

```
~/data/trade/
├── 20260312/
│   ├── positions_20260312.csv
│   └── trades_20260312.csv
├── 20260313/
│   ├── positions_20260313.csv
│   └── trades_20260313.csv
```

### 配置 (.env)

```bash
NS_HOST=ns                        # SSH config 别名
NS_SCP_REMOTE_DIR=~/data/trade    # 远程基础目录
```

`scp` 命令直接读取 `~/.ssh/config` 中的 Host、User、IdentityFile 等配置，无需在 `.env` 中重复设置。

### 注意事项

- SCP 上传失败不会阻塞 CSV 导出，仅记录警告日志
- 同一天重复执行会覆盖远程和本地的同名文件
- 需确保 `~/.ssh/config` 中已配置 `ns` 主机的连接信息
