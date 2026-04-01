# API Design

## Purpose

The health/account API is a lightweight operator-facing HTTP surface, not a full application framework.

It serves three groups of use cases:

- system health checks
- operator/account inspection
- lightweight real-time quote subscription through WebSocket

## Startup Paths

Two paths host the same handler class:

- `serve_healthcheck(host, port, scope)`
  - standalone process path used by `main.py health-server`

- `start_healthcheck_server(host, port, scope)`
  - background-thread path used when another process embeds the server

Design rule:

- shared handler dependencies must be wired in both paths
- if WebSocket or API dependencies are only injected in one path, you have a latent production bug

## Endpoint Groups

### Health Endpoints

- `/health`
- `/healthz`

Behavior:

- returns a cached health snapshot
- returns `200` unless overall status is `down`
- returns `503` when health is `down`

### Ledger Endpoints

These are backed by local SQLite through `AccountDataService`.

- `/api/orders`
- `/api/signals`
- `/api/trades`
- `/api/pnl`
- `/api/strategy-pnl-summary`

Design rule:

- these endpoints are strategy/business history views
- they should not be rewritten to query QMT directly
- they should preserve pagination and explicit validation errors

### Live State Endpoints

- `/api/positions`
- `/api/account-overview`
- `/api/data-policy`

Design rule:

- these endpoints should expose the data-source decision instead of hiding it
- `positions` prefers live QMT and may fall back to local snapshots
- `account-overview` should remain useful even when part of the live state is unavailable

## Status-Code Semantics

- `200`
  - successful request, including empty datasets

- `400`
  - caller supplied an invalid parameter such as pagination or malformed date

- `503`
  - live dependency is unavailable for an endpoint that cannot safely fabricate data

- `500`
  - internal unhandled failure

## WebSocket Design

- path: `/ws`
- transport: same port as HTTP via protocol upgrade
- manager: `WebSocketManager`
- source: Redis `quote_stream`

Design rule:

- if `ws_manager` is unavailable, fail explicitly instead of crashing on missing attributes

## Pagination Rules

Common pagination policy:

- `page >= 1`
- `1 <= limit <= 500`

These guards should stay consistent across orders, signals, and trades.

## API Ownership

- request parsing, status codes, and transport concerns live in `healthcheck.py`
- data-source policy and response assembly for account data live in `account_data_service.py`
- raw broker access lives in `trader.py`

This separation is important. If handlers start embedding broker/DB policy ad hoc, API behavior will drift.
