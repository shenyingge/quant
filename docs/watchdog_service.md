# Watchdog Service

## Purpose

The project now includes a dedicated watchdog service that is meant to run 24x7 on the Windows host.

Its responsibilities are:

- keep the CMS HTTP service online all day
- on trading days, ensure the core trading processes are running inside their expected windows
- trigger end-of-day one-shot jobs once per day
- optionally stop managed long-running services after their window closes

On Windows, the watchdog now inspects processes through Python's native `psutil` path first, which avoids the slow `Get-CimInstance Win32_Process` polling cost during every cycle.

## Managed Targets

Current default target inventory:

- `cms-server`
  - command: `python main.py cms-server`
  - mode: always on
- `trading engine`
  - command: `python main.py run`
  - expected window: `08:35-21:05` on trading days
- `T0 strategy daemon`
  - command: `python main.py t0-daemon`
  - expected window: `09:20-15:05` on trading days
  - only managed when `T0_STRATEGY_ENABLED=true`
- `T0 position sync`
  - command: `python main.py t0-sync-position`
  - schedule: `15:00` once per trading day
  - only managed when `T0_STRATEGY_ENABLED=true`

External prerequisite that is monitored indirectly by downstream startup logic:

- QMT client process

The watchdog does not auto-launch QMT itself. The current design treats QMT as an external dependency that should already be available on the machine.

## Commands

Run the watchdog normally:

```powershell
.\.venv\Scripts\python.exe main.py watchdog
```

Run one inspection cycle only:

```powershell
.\.venv\Scripts\python.exe main.py watchdog --once
```

Run one dry-run inspection cycle without starting or stopping anything:

```powershell
.\.venv\Scripts\python.exe main.py watchdog --once --dry-run
```

## Configuration

Relevant `.env` settings:

```env
WATCHDOG_ENABLED=true
WATCHDOG_CHECK_INTERVAL_SECONDS=30
WATCHDOG_MIN_RESTART_INTERVAL_SECONDS=120
WATCHDOG_STATE_PATH=./output/watchdog_state.json
WATCHDOG_ENFORCE_STOP_OUTSIDE_WINDOW=true
WATCHDOG_ENABLE_TRADING_SERVICE=true
WATCHDOG_ENABLE_T0_DAEMON=true
WATCHDOG_ENABLE_T0_SYNC=true
WATCHDOG_TRADING_START_TIME=08:35
WATCHDOG_TRADING_STOP_TIME=21:05
WATCHDOG_T0_START_TIME=09:20
WATCHDOG_T0_STOP_TIME=15:05
WATCHDOG_T0_SYNC_TIME=15:00
```

`WATCHDOG_STATE_PATH` is used to remember which once-per-day jobs were already triggered.

## Windows Registration

Register the watchdog as the single auto-start scheduled task:

```powershell
.\scripts\register_watchdog_service_task.ps1
```

The scheduled task now launches `python main.py watchdog` directly and no longer depends on a PowerShell startup wrapper.

Remove it:

```powershell
.\scripts\unregister_watchdog_service_task.ps1
```

Registered task name:

```text
Quant_Watchdog_Service
```

Single-entry deployment rule:

- keep `Quant_Watchdog_Service`
- do not keep a separate `Quant_CMS_Service`
- the watchdog is responsible for keeping `cms-server` alive

## Verification

Check the task:

```powershell
schtasks /Query /TN Quant_Watchdog_Service /V /FO LIST
```

Run a safe dry-run cycle:

```powershell
.\.venv\Scripts\python.exe main.py watchdog --once --dry-run
```

Check the CMS service:

```powershell
curl http://127.0.0.1:8780/health
```
