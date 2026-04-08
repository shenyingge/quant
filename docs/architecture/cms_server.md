# CMS Server

## Purpose

项目提供独立的 CMS 服务，面向运维健康检查和账户类读取接口。

- HTTP endpoint: `/health` / `/healthz`
- 默认绑定: `127.0.0.1:8780`
- 进程模型: 可独立运行，也可由 watchdog 长期守护
- 运行模型: 24x7 后台服务

## Commands

推荐入口：

```bash
make cms-check
make cms-server
```

底层 CLI：

```bash
uv run python main.py cms-check
uv run python main.py cms-server
```

## Default Checks

当前 `/health` 聚焦以下检查项：

- trading day status
- database connectivity
- Redis connectivity
- QMT client process presence
- trading engine process presence
- watchdog process presence

说明：

- `/health` 只覆盖当前运行中的核心依赖与进程
- CMS 自身健康由 `/health` 端点可访问性体现，而不是单独的检查项

总体状态规则：

- `down`: 至少一个 critical check failed
- `degraded`: 没有 critical failure，但存在 `warn` 或非 critical `fail`
- `ok`: 其余情况

## Refresh Model

- 后台刷新线程周期性重建快照
- `/health` 返回缓存中的最新快照
- 避免每个请求都直接触发慢检查

默认刷新间隔：

```env
CMS_SERVER_REFRESH_INTERVAL_SECONDS=15
```

## Configuration

```env
CMS_SERVER_HOST=127.0.0.1
CMS_SERVER_PORT=8780
CMS_SERVER_TIMEOUT_SECONDS=2
CMS_SERVER_REFRESH_INTERVAL_SECONDS=15
```

`CMS_SERVER_HOST` 支持特殊值：

- `tailscale`: 自动探测当前 Tailscale IPv4 并只绑定该网卡

## Windows Registration

单独注册 `cms-server` 开机任务已不是推荐模式。

推荐使用 watchdog 单入口：

```powershell
.\scripts\register_watchdog_service_task.ps1
```

## Verification

```bash
make cms-check
curl http://127.0.0.1:8780/health
```

如需经 Tailscale 访问，再额外配置防火墙与绑定地址。
