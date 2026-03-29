# Health Check Service

## Purpose

The project exposes a standalone health check service for operator monitoring.

- HTTP endpoint: `/health` and `/healthz`
- Default bind: `127.0.0.1:8780`
- Process model: independent of the trading engine and strategy engine
- Runtime model: 24x7 background service

The endpoint returns a standardized JSON payload with:

- top-level service metadata
- overall status
- summary counters
- per-check results

## Commands

Run a one-shot snapshot:

```powershell
.\.venv\Scripts\python.exe main.py health-check
```

Run the standalone HTTP service:

```powershell
.\.venv\Scripts\python.exe main.py health-server
```

Use the helper script:

```powershell
.\scripts\start_healthcheck_service.ps1
```

The helper script respects `.env` / `HEALTHCHECK_HOST`. If you set `HEALTHCHECK_HOST=tailscale`, it resolves that sentinel to the machine's current Tailscale IPv4 and binds the HTTP server to that address only.

## Default Checks

The current `/health` output includes:

- trading day status
- database connectivity
- Redis connectivity
- QMT client process presence
- trading engine process presence
- strategy engine process presence
- latest signal card file

Overall status rules:

- `down`: at least one critical check failed
- `degraded`: no critical failure, but at least one `warn` or noncritical `fail`
- `ok`: everything else

## Refresh Model

The HTTP server does not compute checks on every request.

- A background refresh thread rebuilds the snapshot periodically
- `/health` returns the latest cached snapshot
- This avoids slow requests caused by Tushare, QMT, or process inspection

Default refresh interval:

```env
HEALTHCHECK_REFRESH_INTERVAL_SECONDS=15
```

## Configuration

Relevant environment variables:

```env
HEALTHCHECK_HOST=127.0.0.1
HEALTHCHECK_PORT=8780
HEALTHCHECK_TIMEOUT_SECONDS=2
HEALTHCHECK_REFRESH_INTERVAL_SECONDS=15
```

`HEALTHCHECK_HOST` supports a special value:

- `tailscale`: auto-detect the current Tailscale IPv4 and bind to that interface only

Recommended usage:

- Keep `HEALTHCHECK_HOST=127.0.0.1` as the default safe setting
- Set `HEALTHCHECK_HOST=tailscale` only on hosts where you explicitly want Tailscale access

To add a Windows Firewall rule that allows only Tailscale CGNAT addresses to reach the port:

```powershell
.\scripts\configure_healthcheck_tailscale_firewall.ps1
```

## Windows Registration

Register the service as a startup scheduled task:

```powershell
.\scripts\register_healthcheck_service_task.ps1
```

Remove the scheduled task:

```powershell
.\scripts\unregister_healthcheck_service_task.ps1
```

Registered task name:

```text
Quant_Healthcheck_Service
```

## Verification

Check task state:

```powershell
schtasks /Query /TN Quant_Healthcheck_Service /V /FO LIST
```

Query the endpoint locally:

```powershell
curl http://127.0.0.1:8780/health
```

Query the endpoint over Tailscale from another node:

```powershell
curl http://100.x.y.z:8780/health
```

If local HTTP tooling is affected by system proxy settings, use a browser or a direct socket-based check instead.
