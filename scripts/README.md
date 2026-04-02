# Scripts Directory

This directory now follows a single-entry runtime model on Windows:

- `Quant_Watchdog_Service` is the only startup scheduled task.
- The watchdog keeps `cms-server` alive 24x7.
- On trading days, the watchdog manages `run`, `t0-daemon`, and the end-of-day `t0-reconcile` job.
- Minute-history export remains an optional separate daily task.

## Current Scripts

### Startup And Registration

- `start_watchdog_service.bat`
  - Lightweight manual launcher for the watchdog.
- `register_watchdog_service_task.ps1`
  - Registers `Quant_Watchdog_Service` to launch `python main.py watchdog` directly and cleans up legacy standalone CMS tasks.
- `unregister_watchdog_service_task.ps1`
  - Removes the watchdog startup task and any leftover legacy standalone CMS task.

### Runtime Helpers

- `start_cms_service.bat`
  - Lightweight manual launcher for the standalone CMS HTTP server.
- `run_console.bat`
  - Manual console entry for the trading service.
- `run_t0_daemon.bat`
  - Manual console entry for the T+0 daemon.
- `stop_trading_service.bat`
  - Stops the trading service process.
- `stop_t0_daemon.bat`
  - Stops the T+0 daemon process.
- `stop_python_by_command.ps1`
  - Utility used by stop scripts to terminate specific Python commands.

### Optional Daily Task

- `setup_minute_history_task.bat`
  - Registers the standalone minute-history export task.
- `task_wrapper_minute_history.bat`
  - Wrapper used by the minute-history scheduled task; launches `python main.py export-minute-daily` directly.
- `export_minute_history_bundle.py`
  - Export helper for minute-history workflows.

### Network Helper

- `configure_cms_tailscale_firewall.ps1`
  - Adds a firewall rule for Tailscale-only CMS server access.

## Removed Legacy Scripts

The following paths were removed because they duplicated the watchdog runtime model or depended on an old MSYS shell path:

- Per-service scheduled-task installers for trading, T+0, and meta-db sync
- Old watchdog BAT installers
- Legacy shell task runner and `.env` loader
- Old task wrappers that only existed to support the removed installers

## Recommended Operator Commands

Register the single startup task:

```powershell
.\scripts\register_watchdog_service_task.ps1
```

Run a safe watchdog dry-run:

```powershell
.\.venv\Scripts\python.exe main.py watchdog --once --dry-run
```

Register the optional minute-history task:

```cmd
scripts\setup_minute_history_task.bat
```
