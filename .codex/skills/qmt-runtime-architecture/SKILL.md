---
name: qmt-runtime-architecture
description: Understand, modify, or debug the quant runtime architecture around the Windows watchdog, health/account API, WebSocket endpoint, and QMT-vs-local data source policy. Use when working on `src/watchdog_service.py`, `src/healthcheck.py`, `src/account_data_service.py`, startup scripts in `scripts/`, or architecture docs for watchdogs, APIs, account data, and source-of-truth decisions.
---

# QMT Runtime Architecture

Use this skill when the task is about runtime architecture rather than one narrow implementation detail.

Start with [references/runtime-topology.md](references/runtime-topology.md) for the end-to-end process graph. Then load the focused reference you need:

- [references/watchdog-design.md](references/watchdog-design.md) for the 24x7 watchdog and Windows startup model
- [references/api-design.md](references/api-design.md) for the health/account API, WebSocket path, and failure semantics
- [references/data-source-policy.md](references/data-source-policy.md) for QMT vs local DB responsibilities

## Workflow

1. Identify whether the change is about process lifecycle, API shape, account data sourcing, or Windows operator workflow.
2. Trace the CLI entry in `main.py` before editing internals.
3. For watchdog work, follow `main.py` -> `src/watchdog_service.py` -> `scripts/start_watchdog_service.ps1` / scheduled task registration.
4. For API work, follow `main.py health-server` -> `src/healthcheck.py` -> `src/account_data_service.py`.
5. For source-of-truth questions, preserve the rule: QMT is authoritative for live account state; local storage is authoritative for strategy business history.
6. When changing API behavior, verify both background-thread startup (`start_healthcheck_server`) and standalone process startup (`serve_healthcheck`).

## Safety Rules

- Treat QMT access as production-sensitive. Read-only queries are safer than order placement, but still assume the broker is real.
- Do not silently replace live QMT state with invented defaults for positions or funds.
- If live QMT state is unavailable, prefer explicit fallback metadata or a clear service error over pretending the account is empty.
- Preserve pagination validation and explicit HTTP status codes; do not collapse operator-facing failures into ambiguous `200` responses.
- Keep watchdog restarts rate-limited and avoid loops that can thrash trading processes.

## Editing Guidance

- When changing the managed target list, update both `src/watchdog_service.py` and the architecture/docs that describe the target inventory.
- When changing account data policy, update `src/account_data_service.py` first, then keep `/api/data-policy` and `/api/account-overview` aligned.
- When changing WebSocket behavior, inspect both handler wiring and whichever startup path (`serve_healthcheck` or `start_healthcheck_server`) is relevant.
- Prefer adding metadata that explains source/fallback behavior in API responses instead of hiding it.
- Keep the architecture docs accurate enough that a future agent can answer "where does this data come from?" without rediscovering it from scratch.

## References

- `references/runtime-topology.md`: runtime process graph, ownership boundaries, and code entrypoints
- `references/watchdog-design.md`: watchdog responsibilities, managed targets, scheduling model, and failure handling
- `references/api-design.md`: HTTP/WebSocket design, endpoint contracts, and startup-path differences
- `references/data-source-policy.md`: source-of-truth policy for positions, orders, trades, and PnL
