# Watchdog Design

## Purpose

The watchdog is a Windows-friendly 24x7 supervisor for the `quant` runtime.

It is designed to answer:

- what should be running right now
- what should be started if missing
- what should be triggered once per day
- what should be stopped outside the allowed window

## Core Design

The watchdog is intentionally not a full service manager.

It uses:

- process inspection
- simple target metadata
- trading-day awareness
- time-window expectations
- cooldown-based restart protection
- optional stop enforcement outside window

This keeps it auditable and easy to reason about on Windows hosts that already use Task Scheduler.

## Managed Target Types

### Service Targets

Long-running processes expected to remain alive across a time window.

Current service targets:

- `healthcheck_service`
  - 24x7
  - launch path: `scripts/start_healthcheck_service.ps1`

- `trading_engine`
  - trading days only
  - default window: `08:35-21:05`
  - launch path: `scripts/task_runner.ps1 -Mode trading-service`

- `strategy_engine`
  - trading days only
  - default window: `09:20-15:05`
  - launch path: `scripts/task_runner.ps1 -Mode t0-daemon`

### Job Targets

One-shot processes expected once per trading day.

Current job targets:

- `t0_position_sync`
  - default schedule: `15:00`
  - launch path: `scripts/task_runner.ps1 -Mode t0-sync-position`

- `meta_db_sync`
  - default schedule: `15:10`
  - launch path: `scripts/task_runner.ps1 -Mode meta-db-sync`

## State Model

The watchdog stores minimal local state in `WATCHDOG_STATE_PATH`.

That state is used only for once-per-day jobs so they are not retriggered on every cycle after the scheduled time has passed.

This state is intentionally lightweight:

- no full process history
- no business data
- no long-term metrics

## Decision Loop

On each cycle:

1. determine trading-day status
2. inspect current processes
3. for each service target:
   - if expected and missing: launch
   - if not expected and running and stop enforcement is on: stop
4. for each job target:
   - if trading day and within trigger window and not yet triggered today: launch once

## Failure Handling

- Restart cooldown
  - prevents rapid launch loops if a process exits immediately

- Trigger-window cap for jobs
  - avoids replaying missed one-shot jobs deep into the evening

- Explicit non-ownership of QMT desktop client
  - the watchdog does not auto-start QMT itself
  - QMT is treated as an external dependency that must be available for broker work

## Windows Integration

The intended host model is:

- scheduled task name: `Quant_Watchdog_Service`
- trigger: `AtStartup`
- account: `SYSTEM`
- long execution limit
- auto restart on failure

The helper scripts are:

- `scripts/start_watchdog_service.ps1`
- `scripts/start_watchdog_service.bat`
- `scripts/register_watchdog_service_task.ps1`
- `scripts/unregister_watchdog_service_task.ps1`

## Safe Modification Rules

- If you add a new managed process, define whether it is a `service` or a `job`
- Keep launch commands routed through existing wrapper scripts when possible
- Update the time-window and documentation together
- Preserve cooldowns and one-shot state semantics
- Do not make the watchdog responsible for business retries that belong inside the service itself
