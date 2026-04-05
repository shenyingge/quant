# 每日持仓与成交导出

## 功能说明

收盘后从 QMT 查询当日持仓和委托成交数据，并执行两件事：

- 导出 CSV 到 `data/daily_export/`
- 通过 `rsync` 同步到 NS 主机的 `~/data/trade/YYYYMMDD/`

## 使用方式

```bash
uv run python main.py export-daily
```

服务运行时会在每天 `15:20` 自动调度执行。

## 导出文件

### `positions_YYYYMMDD.csv`

字段：

- `stock_code`
- `volume`
- `can_use_volume`
- `avg_price`
- `last_price`
- `market_value`
- `float_profit`
- `profit_rate`

### `trades_YYYYMMDD.csv`

字段：

- `order_id`
- `stock_code`
- `order_type`
- `order_volume`
- `price`
- `traded_volume`
- `traded_price`
- `order_status`
- `order_time`
- `status_desc`

## rsync 同步

导出完成后，程序会自动执行 `rsync`，按日期子目录上传。

远端目录结构示例：

```text
~/data/trade/
  20260312/
    positions_20260312.csv
    trades_20260312.csv
  20260313/
    positions_20260313.csv
    trades_20260313.csv
```

## 配置

```bash
NS_HOST=ns
NS_SCP_REMOTE_DIR=~/data/trade

# 当 NS_HOST 不是 ssh config 别名时可显式指定
NS_SSH_USERNAME=shen
NS_SSH_KEY_FILE=C:/Users/shen/.ssh/trading_backup_key
NS_SSH_PORT=22

RSYNC_BIN=rsync
SSH_BIN=ssh
```

`rsync`/`ssh` 会直接复用本机的 `~/.ssh/config`、agent 和密钥配置；如果 `NS_HOST` 是别名，通常不需要再在 `.env` 里重复填写用户名或密钥。

## 注意事项

- `rsync` 失败不会阻塞 CSV 导出，只会记录 warning 日志。
- 同一天重复执行会覆盖远端和本地同名文件。
- 运行机器需要能直接执行 `rsync` 和 `ssh`。
