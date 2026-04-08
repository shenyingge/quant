# Watchdog Service

## Purpose

watchdog 是项目当前默认运行入口，面向 24x7 守护。

职责：

- 保持 `cms-server` 常驻
- 在交易日时间窗内保证交易引擎在线
- 按日触发分钟行情入库任务
- 在窗口外按配置停止受管长跑服务

QMT 是外部依赖，watchdog 不负责自动启动 QMT 客户端。

## Managed Targets

当前默认 target inventory：

- `cms_service`
  - command: `python main.py cms-server`
  - mode: always on
- `trading_engine`
  - command: `python main.py run`
  - expected window: `08:35-21:05` on trading days
- `minute_history_ingest_daily`
  - command: `python main.py ingest-minute-daily`
  - schedule: once per trading day

说明：

- 受管对象仅限上面的 CMS、交易引擎与分钟行情按日任务
- watchdog 不负责扩展型业务进程的拉起与编排

## Recommended Entrypoints

推荐操作方式：

```bash
make
make watchdog-bg
```

底层 CLI 仍可直接运行：

```bash
uv run python main.py watchdog
uv run python main.py watchdog --once
uv run python main.py watchdog --once --dry-run
```

说明：

- `make` 默认执行 `watchdog`
- `make watchdog` / `make watchdog-bg` 会先检查是否已有 watchdog 进程，避免重复拉起
- 直接运行 `python main.py watchdog` 时不带这层 Makefile 幂等保护

## Configuration

```env
WATCHDOG_ENABLED=true
WATCHDOG_CHECK_INTERVAL_SECONDS=30
WATCHDOG_MIN_RESTART_INTERVAL_SECONDS=120
WATCHDOG_STATE_PATH=./output/watchdog_state.json
WATCHDOG_ENFORCE_STOP_OUTSIDE_WINDOW=true
WATCHDOG_ENABLE_TRADING_SERVICE=true
WATCHDOG_TRADING_START_TIME=08:35
WATCHDOG_TRADING_STOP_TIME=21:05
WATCHDOG_JOB_MAX_DELAY_MINUTES=120
```

`WATCHDOG_STATE_PATH` 用来记录 once-per-day 任务是否已触发。

## Windows Registration

推荐注册为单一开机任务：

```powershell
.\scripts\register_watchdog_service_task.ps1
```

注册后的统一开机任务名：

```text
Quant_Watchdog_Service
```

## Verification

```bash
make cms-check
uv run python main.py watchdog --once --dry-run
```
