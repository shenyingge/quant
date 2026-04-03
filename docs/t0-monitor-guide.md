# T+0 策略监控界面

## 功能说明

实时展示 T+0 策略的运行状态，包括：
- 市场状态（regime、分支优先级）
- 特征计算（价格、VWAP、涨跌幅、评分等）
- 仓位状态（持仓、可卖、可买数量）
- 时间窗口检查（是否在交易时段）
- 策略条件检查（每个条件是否满足）

## 使用方法

### 1. 启动 CMS Server

```bash
uv run python main.py cms-server
```

默认监听地址：`http://127.0.0.1:8780`

### 2. 访问监控界面

在浏览器中打开：

```
http://127.0.0.1:8780/t0-monitor
```

或者直接访问根路径：

```
http://127.0.0.1:8780/
```

### 3. API 接口

如果需要直接获取 JSON 数据：

```bash
curl http://127.0.0.1:8780/api/t0-strategy-status
```

## API 响应格式

```json
{
  "status": "ok",
  "as_of_time": "2026-04-03 10:45:00",
  "stock_code": "601138.SH",
  "market": {
    "regime": "transition",
    "branch_priority": ["reverse_t", "positive_t"]
  },
  "features": {
    "day_open": 52.00,
    "current_close": 52.81,
    "high_so_far": 53.11,
    "low_so_far": 52.00,
    "vwap": 52.51,
    "rise_pct": 2.13,
    "pullback_pct": 0.56,
    "bounce_pct": 1.56,
    "close_vs_vwap_pct": 0.56,
    "fake_breakout_score": 0.60,
    "absorption_score": 0.60
  },
  "position": {
    "total": 4000,
    "available": 4000,
    "cost_price": 70.12,
    "base": 3100,
    "tactical": 900,
    "max": 4000,
    "t0_sell_available": 900,
    "t0_buy_capacity": 0
  },
  "time_windows": {
    "current_time": "10:45:00",
    "positive_sell": {
      "window": "09:45-11:20",
      "active": true
    },
    "positive_buyback": {
      "window": "13:30-14:56",
      "active": false
    },
    "reverse_buy": {
      "window": "09:50-13:20",
      "active": true
    },
    "reverse_sell": {
      "window": "13:20-14:56",
      "active": false
    }
  },
  "conditions": {
    "positive_t_sell": {
      "checks": [
        {
          "name": "时间窗口",
          "passed": true,
          "value": "10:45:00"
        },
        {
          "name": "涨幅 >= 1.0%",
          "passed": true,
          "value": 2.13
        },
        {
          "name": "回撤 >= 0.5%",
          "passed": true,
          "value": 0.56
        },
        {
          "name": "价格 < VWAP",
          "passed": false,
          "value": "52.81 vs 52.51"
        },
        {
          "name": "T+0可卖 > 0",
          "passed": true,
          "value": 900
        }
      ],
      "all_passed": false
    },
    "reverse_t_buy": {
      "checks": [
        {
          "name": "时间窗口",
          "passed": true,
          "value": "10:45:00"
        },
        {
          "name": "反弹 >= 0.4%",
          "passed": true,
          "value": 1.56
        },
        {
          "name": "价格 vs VWAP >= -0.5%",
          "passed": true,
          "value": 0.56
        },
        {
          "name": "吸收分数 >= 0.6",
          "passed": true,
          "value": 0.60
        },
        {
          "name": "T+0可买 > 0",
          "passed": false,
          "value": 0
        }
      ],
      "all_passed": false
    }
  }
}
```

## 界面特性

- **自动刷新**：每 5 秒自动更新数据
- **条件高亮**：
  - ✓ 绿色：条件满足
  - ✗ 红色：条件不满足
- **时间窗口**：
  - 蓝色徽章：在窗口内
  - 灰色徽章：不在窗口内
- **策略摘要**：
  - 绿色：所有条件满足，可以执行
  - 橙色：条件未完全满足

## 配置

如果需要修改 CMS Server 的监听地址和端口，可以在 `.env` 文件中配置：

```bash
CMS_SERVER_HOST=127.0.0.1
CMS_SERVER_PORT=8780
```

或者使用 Tailscale IP：

```bash
CMS_SERVER_HOST=tailscale
CMS_SERVER_PORT=8780
```

## 故障排查

### 1. 无法访问界面

检查 CMS Server 是否正常运行：

```bash
curl http://127.0.0.1:8780/health
```

### 2. 数据显示错误

检查 API 响应：

```bash
curl http://127.0.0.1:8780/api/t0-strategy-status
```

如果返回错误，查看日志：

```bash
tail -f logs/current/cms_server.log
```

### 3. 数据不更新

- 确认 t0-daemon 正在运行
- 检查 QMT 连接是否正常
- 查看策略引擎日志：`logs/current/strategy_engine.log`
