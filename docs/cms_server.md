# CMS Server

## Purpose

The project exposes a standalone CMS server for operator monitoring and account-facing APIs.

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
.\.venv\Scripts\python.exe main.py cms-check
```

Run the standalone HTTP service:

```powershell
.\.venv\Scripts\python.exe main.py cms-server
```

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
CMS_SERVER_REFRESH_INTERVAL_SECONDS=15
```

## Configuration

Relevant environment variables:

```env
CMS_SERVER_HOST=127.0.0.1
CMS_SERVER_PORT=8780
CMS_SERVER_TIMEOUT_SECONDS=2
CMS_SERVER_REFRESH_INTERVAL_SECONDS=15
```

`CMS_SERVER_HOST` supports a special value:

- `tailscale`: auto-detect the current Tailscale IPv4 and bind to that interface only

Recommended usage:

- Keep `CMS_SERVER_HOST=127.0.0.1` as the default safe setting
- Set `CMS_SERVER_HOST=tailscale` only on hosts where you explicitly want Tailscale access

To add a Windows Firewall rule that allows only Tailscale CGNAT addresses to reach the port:

```powershell
.\scripts\configure_cms_tailscale_firewall.ps1
```

## Windows Registration

Direct startup registration for `cms-server` is deprecated in single-entry mode.

Use the watchdog startup task instead:

```powershell
.\scripts\register_watchdog_service_task.ps1
```

Remove the single startup task through the watchdog unregistration script:

```powershell
.\\scripts\\unregister_watchdog_service_task.ps1
```

## Verification

Check the watchdog task state:

```powershell
schtasks /Query /TN Quant_Watchdog_Service /V /FO LIST
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
