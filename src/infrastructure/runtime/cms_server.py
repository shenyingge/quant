"""CMS server and standardized project runtime checks."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import threading
import time as time_module
from dataclasses import asdict, dataclass, field
from datetime import datetime, time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse, parse_qs
import hashlib
import base64
import struct

import psutil
import redis
from sqlalchemy import desc, text
from sqlalchemy.orm import sessionmaker

from src.trading.account.account_data_service import AccountDataService, parse_pagination
from src.infrastructure.config import settings
from src.infrastructure.db import OrderRecord, TradingSignal, engine as application_db_engine, get_database_details
from src.infrastructure.logger_config import configured_logger as logger
from src.infrastructure.redis.connection import build_redis_client_kwargs
from src.infrastructure.runtime.process_utils import find_matching_processes
from src.market_data.streaming.quote_stream_service import normalize_stock_code
from src.trading.account.account_position_sync import sync_account_positions_via_qmt
from src.trading.calendar.trading_day_checker import is_trading_day

_server_lock = threading.Lock()
_server_instance: Optional[ThreadingHTTPServer] = None
_server_thread: Optional[threading.Thread] = None
_snapshot_store: Optional["CmsSnapshotStore"] = None
_ws_manager: Optional["WebSocketManager"] = None
_TAILSCALE_HOST_SENTINEL = "tailscale"


def _list_runtime_processes() -> List[Dict[str, Any]]:
    return ProjectCmsChecker(scope="project")._list_processes()


def _is_trading_engine_process_running(processes: Optional[List[Dict[str, Any]]] = None) -> bool:
    runtime_processes = processes if processes is not None else _list_runtime_processes()
    matches = find_matching_processes(runtime_processes, ("main.py run", "main.py test-run"))
    return bool(matches)


def _bootstrap_account_positions_snapshot_if_needed() -> None:
    account_data_service = AccountDataService()

    try:
        snapshot = account_data_service.get_positions_snapshot()
    except Exception as exc:
        logger.warning("Skipping CMS position snapshot bootstrap because snapshot check failed: {}", exc)
        return

    if snapshot.get("available"):
        return

    try:
        runtime_processes = _list_runtime_processes()
    except Exception as exc:
        logger.warning("Skipping CMS position snapshot bootstrap because process inspection failed: {}", exc)
        return

    if _is_trading_engine_process_running(runtime_processes):
        logger.info("Skipping CMS position snapshot bootstrap because trading engine is already running")
        return

    try:
        synced_rows = sync_account_positions_via_qmt(source="cms_startup_bootstrap")
    except Exception as exc:
        logger.warning("CMS position snapshot bootstrap failed: {}", exc)
        return

    if synced_rows is None:
        logger.warning("CMS position snapshot bootstrap did not produce a Meta DB snapshot")
        return

    logger.info(
        "CMS position snapshot bootstrap refreshed {} row(s) into Meta DB",
        synced_rows,
    )


class WebSocketManager:
    def __init__(self, account_data_service: Optional[AccountDataService] = None):
        self.clients: Dict[str, Set[Any]] = {}
        self.redis_client = redis.Redis(**build_redis_client_kwargs(decode_responses=True))
        self.account_data_service = account_data_service or AccountDataService()
        self.running = False
        self.thread = None
        self._positions_cache_lock = threading.Lock()
        self._positions_cache_by_stock: Dict[str, Dict[str, Any]] = {}
        self._positions_cache_as_of: Optional[str] = None
        self._positions_cache_expire_at = 0.0

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.running = True
        self.thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.clients.clear()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        self.thread = None

    def subscribe(self, stock_code: str, client):
        stock_code = normalize_stock_code(stock_code)
        if not stock_code:
            return None
        was_empty = stock_code not in self.clients or not self.clients[stock_code]
        if stock_code not in self.clients:
            self.clients[stock_code] = set()
        self.clients[stock_code].add(client)
        if was_empty:
            self._sync_quote_subscription(stock_code, subscribe=True)
        return self._get_latest_quote_payload(stock_code)

    def unsubscribe(self, stock_code: str, client):
        stock_code = normalize_stock_code(stock_code)
        if not stock_code:
            return
        if stock_code in self.clients:
            self.clients[stock_code].discard(client)
            if not self.clients[stock_code]:
                del self.clients[stock_code]
                self._sync_quote_subscription(stock_code, subscribe=False)

    def remove_client(self, client):
        for stock_code in list(self.clients.keys()):
            self.clients[stock_code].discard(client)
            if not self.clients[stock_code]:
                del self.clients[stock_code]
                self._sync_quote_subscription(stock_code, subscribe=False)

    def _sync_quote_subscription(self, stock_code: str, *, subscribe: bool) -> None:
        try:
            if subscribe:
                self.redis_client.sadd(settings.redis_quote_subscriptions_key, stock_code)
            else:
                self.redis_client.srem(settings.redis_quote_subscriptions_key, stock_code)

            self.redis_client.publish(
                settings.redis_quote_control_channel,
                json.dumps(
                    {
                        "action": "subscribe" if subscribe else "unsubscribe",
                        "stock_code": stock_code,
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            logger.warning(
                "Failed to sync Redis quote subscription for {} (subscribe={}): {}",
                stock_code,
                subscribe,
                exc,
            )

    def _get_latest_quote_payload(self, stock_code: str) -> Optional[str]:
        try:
            payload = self.redis_client.get(
                f"{settings.redis_quote_enriched_latest_prefix}{stock_code}"
            )
            if payload:
                return payload

            raw_payload = self.redis_client.get(f"{settings.redis_quote_latest_prefix}{stock_code}")
            if not raw_payload:
                return None

            enriched_payload = self._enrich_quote_payload(json.loads(raw_payload))
            if enriched_payload is None:
                return raw_payload

            payload_json = json.dumps(enriched_payload, ensure_ascii=False)
            self._store_enriched_quote_payload(stock_code, payload_json)
            return payload_json
        except Exception as exc:
            logger.warning("Failed to load latest quote payload for {}: {}", stock_code, exc)
            return None

    def _broadcast_loop(self):
        pubsub = self.redis_client.pubsub()
        pubsub.subscribe(settings.redis_quote_stream_channel)
        while self.running:
            try:
                message = pubsub.get_message(timeout=1)
                if message and message["type"] == "message":
                    quote_data = json.loads(message["data"])
                    enriched_payload = self._enrich_quote_payload(quote_data)
                    if enriched_payload is None:
                        continue
                    stock_code = normalize_stock_code(enriched_payload.get("stock_code"))
                    payload_json = json.dumps(enriched_payload, ensure_ascii=False)
                    self._store_enriched_quote_payload(stock_code, payload_json)
                    if stock_code in self.clients:
                        disconnected = set()
                        for client in list(self.clients[stock_code]):
                            try:
                                client.send_message(payload_json)
                            except:
                                disconnected.add(client)
                        for client in disconnected:
                            self.remove_client(client)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
                time_module.sleep(1)

    def _store_enriched_quote_payload(self, stock_code: str, payload_json: str) -> None:
        if not stock_code:
            return

        self.redis_client.publish(settings.redis_quote_enriched_stream_channel, payload_json)
        latest_key = f"{settings.redis_quote_enriched_latest_prefix}{stock_code}"
        latest_ttl = int(settings.redis_quote_enriched_latest_ttl_seconds)
        if latest_ttl > 0:
            self.redis_client.setex(latest_key, latest_ttl, payload_json)
        else:
            self.redis_client.set(latest_key, payload_json)

    def _enrich_quote_payload(self, quote_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        stock_code = normalize_stock_code(quote_data.get("stock_code"))
        if not stock_code:
            return None

        last_price = self._to_optional_float(
            quote_data.get("last_price")
            or quote_data.get("price")
            or self._extract_from_quote(quote_data.get("quote"), "lastPrice", "last_price", "price", "last")
        )
        quote_volume = self._to_optional_float(
            quote_data.get("volume")
            or self._extract_from_quote(quote_data.get("quote"), "volume", "vol")
        )
        position = self._get_position_for_stock(stock_code)

        position_payload = None
        pnl_payload = None
        timestamps = {
            "quote_time": quote_data.get("quote_time"),
            "published_at": quote_data.get("published_at"),
            "cms_enriched_at": _timestamp_now(),
        }

        if position is not None:
            volume = int(position.get("volume") or 0)
            avg_price = self._to_optional_float(position.get("avg_price"))
            market_value = (
                round(last_price * volume, 4)
                if last_price is not None
                else self._to_optional_float(position.get("market_value"))
            )
            cost_basis = (
                round(avg_price * volume, 4)
                if avg_price is not None
                else None
            )
            unrealized_pnl = (
                round(market_value - cost_basis, 4)
                if market_value is not None and cost_basis is not None
                else None
            )
            unrealized_pnl_pct = (
                round(unrealized_pnl / cost_basis * 100, 4)
                if unrealized_pnl is not None and cost_basis not in {None, 0}
                else None
            )

            position_payload = {
                "account_id": position.get("account_id"),
                "volume": volume,
                "available_volume": int(position.get("available_volume") or 0),
                "avg_price": avg_price,
                "snapshot_source": position.get("snapshot_source"),
                "source": position.get("source"),
                "position_method": position.get("position_method"),
            }
            pnl_payload = {
                "cost_basis": cost_basis,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
            }
            timestamps["position_snapshot_time"] = position.get("snapshot_time")
            timestamps["positions_as_of"] = self._positions_cache_as_of

        return {
            "stock_code": stock_code,
            "source": "cms_quote_enriched",
            "quote_source": quote_data.get("source"),
            "period": quote_data.get("period"),
            "last_price": last_price,
            "quote_volume": quote_volume,
            "has_position": position_payload is not None,
            "quote": quote_data.get("quote"),
            "position": position_payload,
            "pnl": pnl_payload,
            "timestamps": timestamps,
        }

    def _get_position_for_stock(self, stock_code: str) -> Optional[Dict[str, Any]]:
        now = time_module.monotonic()
        cache_seconds = max(int(settings.cms_quote_position_cache_seconds), 1)

        with self._positions_cache_lock:
            if now >= self._positions_cache_expire_at:
                try:
                    snapshot = self.account_data_service.get_positions_snapshot()
                    positions = snapshot.get("positions") or []
                    self._positions_cache_by_stock = {
                        normalize_stock_code(item.get("stock_code")): item
                        for item in positions
                        if normalize_stock_code(item.get("stock_code"))
                    }
                    self._positions_cache_as_of = snapshot.get("as_of")
                except Exception as exc:
                    logger.warning("Failed to refresh position cache for quote enrichment: {}", exc)
                    self._positions_cache_by_stock = {}
                    self._positions_cache_as_of = None
                self._positions_cache_expire_at = now + cache_seconds

            return self._positions_cache_by_stock.get(stock_code)

    @staticmethod
    def _extract_from_quote(quote: Any, *keys: str) -> Any:
        if not isinstance(quote, dict):
            return None
        for key in keys:
            value = quote.get(key)
            if value is not None:
                return value
        return None

    @staticmethod
    def _to_optional_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


class WebSocketClient:
    def __init__(self, sock, manager):
        self.sock = sock
        self.manager = manager

    def send_message(self, message: str):
        data = message.encode()
        payload_length = len(data)
        frame = bytearray([0x81])
        if payload_length < 126:
            frame.append(payload_length)
        elif payload_length < 65536:
            frame.append(126)
            frame.extend(struct.pack(">H", payload_length))
        else:
            frame.append(127)
            frame.extend(struct.pack(">Q", payload_length))
        frame.extend(data)
        self.sock.sendall(frame)

    def handle(self):
        try:
            while True:
                header = self.sock.recv(2)
                if not header:
                    break
                opcode = header[0] & 0x0F
                masked = header[1] & 0x80
                length = header[1] & 0x7F

                if length == 126:
                    length = struct.unpack(">H", self.sock.recv(2))[0]
                elif length == 127:
                    length = struct.unpack(">Q", self.sock.recv(8))[0]

                mask = self.sock.recv(4) if masked else None
                data = bytearray(self.sock.recv(length))

                if mask:
                    for i in range(len(data)):
                        data[i] ^= mask[i % 4]

                if opcode == 0x8:
                    break
                elif opcode == 0x1:
                    msg = json.loads(data.decode())
                    action = msg.get("action")
                    stock_code = msg.get("stock_code")

                    if action == "subscribe" and stock_code:
                        latest_payload = self.manager.subscribe(stock_code, self)
                        self.send_message(json.dumps({"status": "subscribed", "stock_code": stock_code}))
                        if latest_payload:
                            self.send_message(latest_payload)
                    elif action == "unsubscribe" and stock_code:
                        self.manager.unsubscribe(stock_code, self)
                        self.send_message(json.dumps({"status": "unsubscribed", "stock_code": stock_code}))
        except:
            pass
        finally:
            self.manager.remove_client(self)


def _timestamp_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _project_version() -> str:
    try:
        return version("quant")
    except PackageNotFoundError:
        return "0.1.0"


def _is_valid_ipv4_address(value: str) -> bool:
    try:
        socket.inet_aton(value)
    except OSError:
        return False
    return value.count(".") == 3


def _extract_ipv4_address(value: str) -> Optional[str]:
    for match in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", value or ""):
        if _is_valid_ipv4_address(match):
            return match
    return None


def _resolve_tailscale_ipv4_from_cli() -> Optional[str]:
    for command in (["tailscale", "ip", "-4"], ["tailscale.exe", "ip", "-4"]):
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=True,
                text=True,
                timeout=3,
            )
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue

        for line in result.stdout.splitlines():
            address = line.strip()
            if _is_valid_ipv4_address(address):
                return address

    return None


def _resolve_tailscale_ipv4_from_ipconfig() -> Optional[str]:
    if os.name != "nt":
        return None

    try:
        result = subprocess.run(
            ["ipconfig"],
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
            errors="ignore",
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    in_tailscale_adapter = False
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if raw_line and raw_line == raw_line.lstrip() and line.endswith(":"):
            in_tailscale_adapter = "tailscale" in line.lower()
            continue

        if not in_tailscale_adapter:
            continue

        address = _extract_ipv4_address(line)
        if address:
            return address

    return None


def resolve_cms_server_host(host: str) -> str:
    candidate = (host or "").strip()
    if not candidate:
        return "127.0.0.1"

    if candidate.lower() != _TAILSCALE_HOST_SENTINEL:
        return candidate

    resolved_host = _resolve_tailscale_ipv4_from_cli() or _resolve_tailscale_ipv4_from_ipconfig()
    if resolved_host:
        return resolved_host

    raise RuntimeError(
        "CMS_SERVER_HOST=tailscale，但未解析到 Tailscale IPv4 地址，请确认 Tailscale 已启动。"
    )


@dataclass
class CmsCheckResult:
    name: str
    component: str
    status: str
    message: str
    critical: bool = False
    details: Dict[str, Any] = field(default_factory=dict)
    checked_at: str = field(default_factory=_timestamp_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CmsSnapshot:
    service: str
    scope: str
    version: str
    status: str
    checked_at: str
    summary: Dict[str, int]
    checks: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CmsSnapshotStore:
    """Keep the latest CMS snapshot fresh in a background thread."""

    def __init__(self, scope: str = "project", refresh_interval_seconds: int = 15):
        self.scope = scope
        self.refresh_interval_seconds = max(int(refresh_interval_seconds), 1)
        self._checker = ProjectCmsChecker(scope=scope)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._snapshot = self._bootstrap_snapshot()

    def _bootstrap_snapshot(self) -> CmsSnapshot:
        check = CmsCheckResult(
            name="bootstrap",
            component="cms_server",
            status="warn",
            message="CMS snapshot is warming up",
        )
        return CmsSnapshot(
            service="quant",
            scope=self.scope,
            version=_project_version(),
            status="degraded",
            checked_at=_timestamp_now(),
            summary={"pass": 0, "warn": 1, "fail": 0, "skip": 0, "duration_ms": 0},
            checks=[check.to_dict()],
        )

    def get_snapshot(self) -> CmsSnapshot:
        with self._lock:
            return self._snapshot

    def refresh_once(self) -> None:
        try:
            snapshot = self._checker.build_snapshot()
        except Exception as exc:
            check = CmsCheckResult(
                name="refresh",
                component="cms_server",
                status="warn",
                message=f"CMS snapshot refresh failed: {exc}",
            )
            snapshot = CmsSnapshot(
                service="quant",
                scope=self.scope,
                version=_project_version(),
                status="degraded",
                checked_at=_timestamp_now(),
                summary={"pass": 0, "warn": 1, "fail": 0, "skip": 0, "duration_ms": 0},
                checks=[check.to_dict()],
            )

        with self._lock:
            self._snapshot = snapshot

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"cms-refresh-{self.scope}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.refresh_once()
            if self._stop_event.wait(self.refresh_interval_seconds):
                break


class ProjectCmsChecker:
    def __init__(
        self,
        scope: str = "project",
        account_data_service: Optional[AccountDataService] = None,
    ):
        self.scope = scope
        self.timeout_seconds = max(int(settings.cms_server_timeout_seconds), 1)
        self.account_data_service = account_data_service or AccountDataService()

    def build_snapshot(self) -> CmsSnapshot:
        started_at = datetime.now()
        trading_day = self._check_trading_day()
        processes = self._list_processes()

        checks = [
            trading_day,
            self._check_database(),
            self._check_redis(),
            self._check_watchdog_process(processes),
            self._check_qmt_client_process(processes, trading_day),
            self._check_trading_engine_process(processes, trading_day),
            self._check_strategy_engine_process(processes, trading_day),
            self._check_signal_card(trading_day),
        ]

        status = self._derive_overall_status(checks)
        summary = self._summarize_checks(checks)
        summary["duration_ms"] = int((datetime.now() - started_at).total_seconds() * 1000)

        return CmsSnapshot(
            service="quant",
            scope=self.scope,
            version=_project_version(),
            status=status,
            checked_at=_timestamp_now(),
            summary=summary,
            checks=[check.to_dict() for check in checks],
        )

    def _check_trading_day(self) -> CmsCheckResult:
        try:
            trading_day = is_trading_day()
        except Exception as exc:
            return CmsCheckResult(
                name="trading_day",
                component="calendar",
                status="warn",
                message=f"Failed to determine trading day: {exc}",
            )

        if trading_day:
            return CmsCheckResult(
                name="trading_day",
                component="calendar",
                status="pass",
                message="Today is a trading day",
                details={"date": datetime.now().date().isoformat()},
            )

        return CmsCheckResult(
            name="trading_day",
            component="calendar",
            status="skip",
            message="Today is not a trading day",
            details={"date": datetime.now().date().isoformat()},
        )

    def _check_database(self) -> CmsCheckResult:
        db_details = get_database_details()
        try:
            with application_db_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return CmsCheckResult(
                name="database",
                component="database",
                status="pass",
                message="Meta DB connection succeeded",
                critical=True,
                details=db_details,
            )
        except Exception as exc:
            return CmsCheckResult(
                name="database",
                component="database",
                status="fail",
                message=f"Meta DB connection failed: {exc}",
                critical=True,
                details=db_details,
            )

    def _check_redis(self) -> CmsCheckResult:
        try:
            client = redis.Redis(
                **build_redis_client_kwargs(
                    socket_connect_timeout=self.timeout_seconds,
                    socket_timeout=self.timeout_seconds,
                    decode_responses=True,
                )
            )
            client.ping()
            return CmsCheckResult(
                name="redis",
                component="redis",
                status="pass",
                message="Redis ping succeeded",
                critical=True,
                details={
                    "host": settings.redis_host,
                    "port": settings.redis_port,
                    "channel": settings.redis_signal_channel,
                },
            )
        except Exception as exc:
            return CmsCheckResult(
                name="redis",
                component="redis",
                status="fail",
                message=f"Redis ping failed: {exc}",
                critical=False,
                details={
                    "host": settings.redis_host,
                    "port": settings.redis_port,
                    "channel": settings.redis_signal_channel,
                },
            )

    def _check_qmt_client_process(
        self, processes: List[Dict[str, Any]], trading_day_check: CmsCheckResult
    ) -> CmsCheckResult:
        matches = [
            process
            for process in processes
            if process["name"].lower() in {"xtminiqmt.exe", "xtitclient.exe", "miniquote.exe"}
        ]
        return self._build_process_check(
            name="qmt_client_process",
            component="qmt",
            matches=matches,
            expected=self._is_expected("qmt", trading_day_check),
        )

    def _check_watchdog_process(self, processes: List[Dict[str, Any]]) -> CmsCheckResult:
        matches = find_matching_processes(processes, ("main.py watchdog",))
        return self._build_process_check(
            name="watchdog_process",
            component="watchdog",
            matches=matches,
            expected=bool(settings.watchdog_enabled),
        )

    def _check_trading_engine_process(
        self, processes: List[Dict[str, Any]], trading_day_check: CmsCheckResult
    ) -> CmsCheckResult:
        matches = find_matching_processes(processes, ("main.py run", "main.py test-run"))
        return self._build_process_check(
            name="trading_engine_process",
            component="trading_engine",
            matches=matches,
            expected=self._is_expected("trading_engine", trading_day_check),
        )

    def _check_strategy_engine_process(
        self, processes: List[Dict[str, Any]], trading_day_check: CmsCheckResult
    ) -> CmsCheckResult:
        matches = find_matching_processes(processes, ("main.py t0-daemon",))
        return self._build_process_check(
            name="strategy_engine_process",
            component="strategy_engine",
            matches=matches,
            expected=self._is_expected("strategy_engine", trading_day_check),
        )

    def _check_signal_card(self, trading_day_check: CmsCheckResult) -> CmsCheckResult:
        try:
            payload = self.account_data_service.get_latest_signal_card_snapshot()
        except Exception as exc:
            return CmsCheckResult(
                name="signal_card",
                component="strategy_engine",
                status="warn",
                message=f"Failed to read signal card from Meta DB: {exc}",
                details={"source": "meta_db"},
            )

        if not payload.get("available"):
            status = "warn" if self._is_expected("strategy_engine", trading_day_check) else "skip"
            return CmsCheckResult(
                name="signal_card",
                component="strategy_engine",
                status=status,
                message=str(payload.get("error") or "Signal card not available in Meta DB"),
                details={
                    "source": payload.get("source", "meta_db"),
                    "stock_code": payload.get("stock_code"),
                    "as_of_time": payload.get("as_of_time"),
                },
            )

        details = {
            "source": payload.get("source", "meta_db"),
            "stock_code": payload.get("stock_code"),
            "signal_action": payload.get("signal_action"),
            "as_of_time": payload.get("as_of_time"),
            "regime": payload.get("regime"),
        }
        return CmsCheckResult(
            name="signal_card",
            component="strategy_engine",
            status="pass",
            message="Signal card is present",
            details=details,
        )

    def _build_process_check(
        self,
        name: str,
        component: str,
        matches: List[Dict[str, Any]],
        expected: bool,
    ) -> CmsCheckResult:
        details = {
            "count": len(matches),
            "pids": [match["pid"] for match in matches],
        }
        if matches:
            return CmsCheckResult(
                name=name,
                component=component,
                status="pass",
                message=f"{component} process is running",
                details=details,
            )

        if expected:
            return CmsCheckResult(
                name=name,
                component=component,
                status="warn",
                message=f"{component} process is not running during its expected window",
                details=details,
            )

        return CmsCheckResult(
            name=name,
            component=component,
            status="skip",
            message=f"{component} process is not expected to be running right now",
            details=details,
        )

    def _derive_overall_status(self, checks: List[CmsCheckResult]) -> str:
        if any(check.status == "fail" and check.critical for check in checks):
            return "down"
        if any(check.status in {"fail", "warn"} for check in checks):
            return "degraded"
        return "ok"

    def _summarize_checks(self, checks: List[CmsCheckResult]) -> Dict[str, int]:
        summary = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
        for check in checks:
            summary[check.status] = summary.get(check.status, 0) + 1
        return summary

    def _is_expected(self, component: str, trading_day_check: CmsCheckResult) -> bool:
        if trading_day_check.status != "pass":
            return False

        now = datetime.now().time()
        windows = {
            "qmt": (time(8, 15), time(21, 5)),
            "trading_engine": (
                datetime.strptime(settings.watchdog_trading_start_time, "%H:%M").time(),
                datetime.strptime(settings.watchdog_trading_stop_time, "%H:%M").time(),
            ),
            "strategy_engine": (
                datetime.strptime(settings.watchdog_t0_start_time, "%H:%M").time(),
                datetime.strptime(settings.watchdog_t0_stop_time, "%H:%M").time(),
            ),
        }
        start_time, end_time = windows[component]
        return start_time <= now <= end_time

    def _list_processes(self) -> List[Dict[str, Any]]:
        if os.name == "nt":
            try:
                return self._list_processes_windows_native()
            except Exception as exc:
                logger.warning(
                    "Native process enumeration failed for health check, falling back to PowerShell: {}",
                    exc,
                )
            command = [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process | "
                    "Select-Object Name,ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress"
                ),
            ]
        else:
            command = ["ps", "-eo", "pid=,ppid=,comm=,args="]

        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=max(self.timeout_seconds, 8),
            )
        except Exception as exc:
            logger.warning(f"Failed to list processes for health check: {exc}")
            return []

        if os.name == "nt":
            raw_output = result.stdout.strip()
            if not raw_output:
                return []
            try:
                data = json.loads(raw_output)
            except json.JSONDecodeError:
                return []
            if isinstance(data, dict):
                data = [data]
            return [
                {
                    "name": (item.get("Name") or ""),
                    "pid": int(item.get("ProcessId") or 0),
                    "parent_pid": int(item.get("ParentProcessId") or 0),
                    "command_line": item.get("CommandLine") or "",
                }
                for item in data
            ]

        processes = []
        for line in result.stdout.splitlines():
            parts = line.strip().split(None, 3)
            if len(parts) != 4:
                continue
            pid_text, parent_pid_text, name, command_line = parts
            try:
                pid = int(pid_text)
                parent_pid = int(parent_pid_text)
            except ValueError:
                continue
            processes.append(
                {
                    "name": name,
                    "pid": pid,
                    "parent_pid": parent_pid,
                    "command_line": command_line,
                }
            )
        return processes

    def _list_processes_windows_native(self) -> List[Dict[str, Any]]:
        processes: List[Dict[str, Any]] = []

        for process in psutil.process_iter(attrs=["pid", "ppid", "name", "cmdline"]):
            try:
                info = process.info
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

            cmdline_parts = info.get("cmdline") or []
            command_line = " ".join(part for part in cmdline_parts if part)
            processes.append(
                {
                    "name": info.get("name") or "",
                    "pid": int(info.get("pid") or 0),
                    "parent_pid": int(info.get("ppid") or 0),
                    "command_line": command_line,
                }
            )

        return processes


class _CmsRequestHandler(BaseHTTPRequestHandler):
    snapshot_store: CmsSnapshotStore
    ws_manager: WebSocketManager
    account_data_service = AccountDataService()

    def do_GET(self) -> None:  # noqa: N802
        if self.headers.get("Upgrade", "").lower() == "websocket":
            self._handle_websocket()
            return

        parsed = urlparse(self.path)
        query_params = parse_qs(parsed.query)

        if parsed.path in {"/health", "/healthz"}:
            self._handle_health()
        elif parsed.path == "/api/positions":
            self._handle_positions()
        elif parsed.path == "/api/orders":
            self._handle_orders(query_params)
        elif parsed.path == "/api/signals":
            self._handle_signals(query_params)
        elif parsed.path == "/api/trades":
            self._handle_trades(query_params)
        elif parsed.path == "/api/pnl":
            self._handle_pnl()
        elif parsed.path == "/api/strategy-pnl-summary":
            self._handle_strategy_pnl_summary(query_params)
        elif parsed.path == "/api/data-policy":
            self._handle_data_policy()
        elif parsed.path == "/api/account-overview":
            self._handle_account_overview()
        elif parsed.path == "/api/t0-strategy-status":
            self._handle_t0_strategy_status()
        elif parsed.path == "/" or parsed.path == "/t0-monitor":
            self._handle_static_file("static/t0-monitor.html")
        elif parsed.path.startswith("/static/"):
            self._handle_static_file(parsed.path[1:])
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def _handle_websocket(self):
        if not hasattr(self, "ws_manager") or self.ws_manager is None:
            self._send_error_response("WebSocket manager is not available", HTTPStatus.SERVICE_UNAVAILABLE)
            return

        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return

        accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode()

        self.send_response(HTTPStatus.SWITCHING_PROTOCOLS)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()

        ws_client = WebSocketClient(self.request, self.ws_manager)
        ws_client.handle()

    def _handle_health(self) -> None:
        snapshot = self.snapshot_store.get_snapshot().to_dict()
        payload = json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8")
        status_code = (
            HTTPStatus.OK if snapshot["status"] != "down" else HTTPStatus.SERVICE_UNAVAILABLE
        )
        self._send_json_response(payload, status_code)

    def _handle_positions(self) -> None:
        try:
            snapshot = self.account_data_service.get_positions_snapshot()
            self._send_json_response(
                json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8")
            )
        except Exception as e:
            self._send_error_response(f"Failed to get positions: {e}", HTTPStatus.SERVICE_UNAVAILABLE)

    def _handle_orders(self, query_params: Dict) -> None:
        try:
            page, limit, _ = parse_pagination(query_params)
            result = self.account_data_service.get_orders_page(page, limit)
            self._send_json_response(
                json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
            )
        except ValueError as e:
            self._send_error_response(f"Invalid pagination: {e}", HTTPStatus.BAD_REQUEST)
        except Exception as e:
            self._send_error_response(f"Failed to get orders: {e}")

    def _handle_signals(self, query_params: Dict) -> None:
        try:
            page, limit, _ = parse_pagination(query_params)
            result = self.account_data_service.get_signals_page(page, limit)
            self._send_json_response(
                json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
            )
        except ValueError as e:
            self._send_error_response(f"Invalid pagination: {e}", HTTPStatus.BAD_REQUEST)
        except Exception as e:
            self._send_error_response(f"Failed to get signals: {e}")

    def _handle_trades(self, query_params: Dict) -> None:
        try:
            page, limit, _ = parse_pagination(query_params)
            result = self.account_data_service.get_trades_page(page, limit)
            self._send_json_response(
                json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
            )
        except ValueError as e:
            self._send_error_response(f"Invalid pagination: {e}", HTTPStatus.BAD_REQUEST)
        except Exception as e:
            self._send_error_response(f"Failed to get trades: {e}")

    def _handle_pnl(self) -> None:
        try:
            result = self.account_data_service.get_pnl_snapshot()
            self._send_json_response(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
        except Exception as e:
            self._send_error_response(f"Failed to calculate PnL: {e}")

    def _handle_strategy_pnl_summary(self, query_params: Dict) -> None:
        try:
            date_values = query_params.get("date", [])
            target_date = None
            if date_values:
                target_date = datetime.strptime(date_values[0], "%Y-%m-%d").date()
            result = self.account_data_service.get_strategy_pnl_summary(target_date)
            self._send_json_response(
                json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
            )
        except ValueError as e:
            self._send_error_response(f"Invalid date: {e}", HTTPStatus.BAD_REQUEST)
        except Exception as e:
            self._send_error_response(f"Failed to get strategy PnL summary: {e}")

    def _handle_data_policy(self) -> None:
        result = self.account_data_service.get_data_policy()
        self._send_json_response(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))

    def _handle_account_overview(self) -> None:
        try:
            parsed = urlparse(self.path)
            query_params = parse_qs(parsed.query)
            include_positions = (
                str(query_params.get("include_positions", ["true"])[0]).strip().lower()
                in {"1", "true", "yes", "on"}
            )
            result = self.account_data_service.get_account_overview(
                include_positions=include_positions
            )
            self._send_json_response(
                json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
            )
        except Exception as e:
            self._send_error_response(f"Failed to get account overview: {e}")

    def _handle_t0_strategy_status(self) -> None:
        """处理 T+0 策略状态请求"""
        try:
            from src.strategy.strategies.t0.strategy_status_service import StrategyStatusService

            service = StrategyStatusService()
            result = service.get_strategy_status()
            self._send_json_response(
                json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
            )
        except Exception as e:
            logger.error(f"获取 T+0 策略状态失败: {e}", exc_info=True)
            self._send_error_response(f"Failed to get T+0 strategy status: {e}")

    def _handle_static_file(self, file_path: str) -> None:
        """处理静态文件请求"""
        try:
            full_path = Path(file_path)
            if not full_path.exists():
                self.send_error(HTTPStatus.NOT_FOUND, "File not found")
                return

            # 确定 MIME 类型
            content_type = "text/html; charset=utf-8"
            if file_path.endswith(".css"):
                content_type = "text/css; charset=utf-8"
            elif file_path.endswith(".js"):
                content_type = "application/javascript; charset=utf-8"
            elif file_path.endswith(".json"):
                content_type = "application/json; charset=utf-8"

            with open(full_path, "rb") as f:
                content = f.read()

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        except Exception as e:
            logger.error(f"读取静态文件失败: {e}")
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Failed to read file")

    def _send_json_response(self, payload: bytes, status_code: int = HTTPStatus.OK) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_error_response(
        self,
        message: str,
        status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR,
    ) -> None:
        payload = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self._send_json_response(payload, status_code)

    def log_message(self, format: str, *args: Any) -> None:
        return


def serve_cms_server(host: str, port: int, scope: str = "project") -> None:
    bind_host = resolve_cms_server_host(host)
    _bootstrap_account_positions_snapshot_if_needed()
    snapshot_store = CmsSnapshotStore(
        scope=scope,
        refresh_interval_seconds=settings.cms_server_refresh_interval_seconds,
    )
    snapshot_store.start()
    ws_manager = WebSocketManager()
    ws_manager.start()
    handler = type(
        "CmsRequestHandler",
        (_CmsRequestHandler,),
        {"snapshot_store": snapshot_store, "ws_manager": ws_manager},
    )
    server = ThreadingHTTPServer((bind_host, port), handler)
    logger.info("CMS server listening on http://{}:{}/health", bind_host, port)
    logger.info("WebSocket server available on ws://{}:{}/ws", bind_host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("CMS server stopped by signal")
    finally:
        server.server_close()
        snapshot_store.stop()
        ws_manager.stop()


def start_cms_server(host: str, port: int, scope: str = "project") -> bool:
    """Start the HTTP CMS server in a background daemon thread."""
    global _server_instance, _server_thread, _snapshot_store, _ws_manager

    bind_host = resolve_cms_server_host(host)
    _bootstrap_account_positions_snapshot_if_needed()

    with _server_lock:
        if (
            _server_instance is not None
            and _server_thread is not None
            and _server_thread.is_alive()
        ):
            logger.debug(
                "CMS server already running on http://{}:{}/health", bind_host, port
            )
            return True

        snapshot_store = CmsSnapshotStore(
            scope=scope,
            refresh_interval_seconds=settings.cms_server_refresh_interval_seconds,
        )
        snapshot_store.start()

        ws_manager = WebSocketManager()
        ws_manager.start()

        handler = type(
            "CmsRequestHandler",
            (_CmsRequestHandler,),
            {"snapshot_store": snapshot_store, "ws_manager": ws_manager},
        )
        try:
            server = ThreadingHTTPServer((bind_host, port), handler)
        except OSError as exc:
            snapshot_store.stop()
            ws_manager.stop()
            logger.warning(
                "CMS server could not bind to http://{}:{}/health: {}",
                bind_host,
                port,
                exc,
            )
            return False

        thread = threading.Thread(
            target=server.serve_forever,
            name=f"cms-server-{bind_host}:{port}",
            daemon=True,
        )
        thread.start()
        _server_instance = server
        _server_thread = thread
        _snapshot_store = snapshot_store
        _ws_manager = ws_manager
        logger.info("CMS server started on http://{}:{}/health", bind_host, port)
        logger.info("WebSocket server available on ws://{}:{}/ws", bind_host, port)
        return True


def stop_cms_server() -> None:
    """Stop the background CMS server if it is running."""
    global _server_instance, _server_thread, _snapshot_store, _ws_manager

    with _server_lock:
        if _server_instance is None:
            return

        server = _server_instance
        thread = _server_thread
        snapshot_store = _snapshot_store
        ws_manager = _ws_manager
        _server_instance = None
        _server_thread = None
        _snapshot_store = None
        _ws_manager = None

    try:
        server.shutdown()
    finally:
        server.server_close()
        if snapshot_store is not None:
            snapshot_store.stop()
        if ws_manager is not None:
            ws_manager.stop()
        if thread is not None:
            thread.join(timeout=2)
