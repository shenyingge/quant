# Scripts

This directory contains operational helpers, registration scripts, and a few
repository maintenance utilities.

## Runtime Scripts

- `start_watchdog_service.bat`
  - Manual launcher for the watchdog service.
- `register_watchdog_service_task.ps1`
  - Registers the single `Quant_Watchdog_Service` startup task.
- `unregister_watchdog_service_task.ps1`
  - Removes the watchdog task and related leftovers.
- `start_cms_service.bat`
  - Manual launcher for the standalone CMS HTTP server.
- `run_console.bat`
  - Manual console entry for the trading runtime.
- `stop_trading_service.bat`
  - Stops the trading service process.
- `stop_python_by_command.ps1`
  - Shared stop helper used by the BAT wrappers.

## Scheduled Task Helpers

- `setup_minute_history_task.bat`
  - Registers the standalone minute-history export task.
- `task_wrapper_minute_history.bat`
  - Wrapper used by the minute-history scheduled task.
- `export_minute_history_bundle.py`
  - Helper for bundling minute-history exports.

## Repo Maintenance Helpers

- `run_tests.py`
  - Direct-file smoke runner for the reorganized `tests/` tree.

## Network Helper

- `configure_cms_tailscale_firewall.ps1`
  - Adds a firewall rule for Tailscale-only CMS access.
