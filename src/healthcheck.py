"""Standardized project health checks and a lightweight HTTP endpoint."""

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

import redis
from sqlalchemy import create_engine, text, desc
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.database import OrderRecord, TradingSignal
from src.logger_config import configured_logger as logger
from src.trading_day_checker import is_trading_day

_server_lock = threading.Lock()
_server_instance: Optional[ThreadingHTTPServer] = None
_server_thread: Optional[threading.Thread] = None
_snapshot_store: Optional["HealthSnapshotStore"] = None
_ws_manager: Optional["WebSocketManager"] = None
_TAILSCALE_HOST_SENTINEL = "tailscale"


class WebSocketManager:
    def __init__(self):
        self.clients: Dict[str, Set[Any]] = {}
        self.redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            decode_responses=True,
        )
        self.running = False
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.running = True
        self.thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def subscribe(self, stock_code: str, client):
        if stock_code not in self.clients:
            self.clients[stock_code] = set()
        self.clients[stock_code].add(client)

    def unsubscribe(self, stock_code: str, client):
        if stock_code in self.clients:
            self.clients[stock_code].discard(client)
            if not self.clients[stock_code]:
                del self.clients[stock_code]

    def remove_client(self, client):
        for stock_code in list(self.clients.keys()):
            self.clients[stock_code].discard(client)
            if not self.clients[stock_code]:
                del self.clients[stock_code]

    def _broadcast_loop(self):
        pubsub = self.redis_client.pubsub()
        pubsub.subscribe("quote_stream")
        while self.running:
            try:
                message = pubsub.get_message(timeout=1)
                if message and message["type"] == "message":
                    quote_data = json.loads(message["data"])
                    stock_code = quote_data.get("stock_code")
                    if stock_code in self.clients:
                        disconnected = set()
                        for client in list(self.clients[stock_code]):
                            try:
                                client.send_message(json.dumps(quote_data))
                            except:
                                disconnected.add(client)
                        for client in disconnected:
                            self.remove_client(client)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
                time_module.sleep(1)


class WebSocketClient:
    def __init__(self, sock, manager):
        self.sock = sock
        self.manager = manager

    def send_message(self, message: str):
        data = message.encode()
        frame = bytearray([0x81, len(data)])
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
                        self.manager.subscribe(stock_code, self)
                        self.send_message(json.dumps({"status": "subscribed", "stock_code": stock_code}))
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


def resolve_healthcheck_host(host: str) -> str:
    candidate = (host or "").strip()
    if not candidate:
        return "127.0.0.1"

    if candidate.lower() != _TAILSCALE_HOST_SENTINEL:
        return candidate

    resolved_host = _resolve_tailscale_ipv4_from_cli() or _resolve_tailscale_ipv4_from_ipconfig()
    if resolved_host:
        return resolved_host

    raise RuntimeError(
        "HEALTHCHECK_HOST=tailscale，但未解析到 Tailscale IPv4 地址，请确认 Tailscale 已启动。"
    )


@dataclass
class HealthCheckResult:
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
class HealthSnapshot:
    service: str
    scope: str
    version: str
    status: str
    checked_at: str
    summary: Dict[str, int]
    checks: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HealthSnapshotStore:
    """Keep the latest health snapshot fresh in a background thread."""

    def __init__(self, scope: str = "project", refresh_interval_seconds: int = 15):
        self.scope = scope
        self.refresh_interval_seconds = max(int(refresh_interval_seconds), 1)
        self._checker = ProjectHealthChecker(scope=scope)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._snapshot = self._bootstrap_snapshot()

    def _bootstrap_snapshot(self) -> HealthSnapshot:
        check = HealthCheckResult(
            name="bootstrap",
            component="healthcheck",
            status="warn",
            message="Health snapshot is warming up",
        )
        return HealthSnapshot(
            service="quant",
            scope=self.scope,
            version=_project_version(),
            status="degraded",
            checked_at=_timestamp_now(),
            summary={"pass": 0, "warn": 1, "fail": 0, "skip": 0, "duration_ms": 0},
            checks=[check.to_dict()],
        )

    def get_snapshot(self) -> HealthSnapshot:
        with self._lock:
            return self._snapshot

    def refresh_once(self) -> None:
        try:
            snapshot = self._checker.build_snapshot()
        except Exception as exc:
            check = HealthCheckResult(
                name="refresh",
                component="healthcheck",
                status="warn",
                message=f"Health snapshot refresh failed: {exc}",
            )
            snapshot = HealthSnapshot(
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
            name=f"healthcheck-refresh-{self.scope}",
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


class ProjectHealthChecker:
    def __init__(self, scope: str = "project"):
        self.scope = scope
        self.timeout_seconds = max(int(settings.healthcheck_timeout_seconds), 1)

    def build_snapshot(self) -> HealthSnapshot:
        started_at = datetime.now()
        trading_day = self._check_trading_day()
        processes = self._list_processes()

        checks = [
            trading_day,
            self._check_database(),
            self._check_redis(),
            self._check_qmt_client_process(processes, trading_day),
            self._check_trading_engine_process(processes, trading_day),
            self._check_strategy_engine_process(processes, trading_day),
            self._check_signal_card(trading_day),
        ]

        status = self._derive_overall_status(checks)
        summary = self._summarize_checks(checks)
        summary["duration_ms"] = int((datetime.now() - started_at).total_seconds() * 1000)

        return HealthSnapshot(
            service="quant",
            scope=self.scope,
            version=_project_version(),
            status=status,
            checked_at=_timestamp_now(),
            summary=summary,
            checks=[check.to_dict() for check in checks],
        )

    def _check_trading_day(self) -> HealthCheckResult:
        try:
            trading_day = is_trading_day()
        except Exception as exc:
            return HealthCheckResult(
                name="trading_day",
                component="calendar",
                status="warn",
                message=f"Failed to determine trading day: {exc}",
            )

        if trading_day:
            return HealthCheckResult(
                name="trading_day",
                component="calendar",
                status="pass",
                message="Today is a trading day",
                details={"date": datetime.now().date().isoformat()},
            )

        return HealthCheckResult(
            name="trading_day",
            component="calendar",
            status="skip",
            message="Today is not a trading day",
            details={"date": datetime.now().date().isoformat()},
        )

    def _check_database(self) -> HealthCheckResult:
        engine = None
        try:
            engine = create_engine(settings.db_url)
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return HealthCheckResult(
                name="database",
                component="database",
                status="pass",
                message="Database connection succeeded",
                critical=True,
                details={"url": settings.db_url},
            )
        except Exception as exc:
            return HealthCheckResult(
                name="database",
                component="database",
                status="fail",
                message=f"Database connection failed: {exc}",
                critical=True,
                details={"url": settings.db_url},
            )
        finally:
            if engine is not None:
                engine.dispose()

    def _check_redis(self) -> HealthCheckResult:
        try:
            client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password,
                socket_connect_timeout=self.timeout_seconds,
                socket_timeout=self.timeout_seconds,
                decode_responses=True,
            )
            client.ping()
            return HealthCheckResult(
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
            return HealthCheckResult(
                name="redis",
                component="redis",
                status="fail",
                message=f"Redis ping failed: {exc}",
                critical=True,
                details={
                    "host": settings.redis_host,
                    "port": settings.redis_port,
                    "channel": settings.redis_signal_channel,
                },
            )

    def _check_qmt_client_process(
        self, processes: List[Dict[str, Any]], trading_day_check: HealthCheckResult
    ) -> HealthCheckResult:
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

    def _check_trading_engine_process(
        self, processes: List[Dict[str, Any]], trading_day_check: HealthCheckResult
    ) -> HealthCheckResult:
        matches = [
            process
            for process in processes
            if "main.py run" in process["command_line"]
            or "main.py test-run" in process["command_line"]
        ]
        return self._build_process_check(
            name="trading_engine_process",
            component="trading_engine",
            matches=matches,
            expected=self._is_expected("trading_engine", trading_day_check),
        )

    def _check_strategy_engine_process(
        self, processes: List[Dict[str, Any]], trading_day_check: HealthCheckResult
    ) -> HealthCheckResult:
        matches = [
            process for process in processes if "main.py t0-daemon" in process["command_line"]
        ]
        return self._build_process_check(
            name="strategy_engine_process",
            component="strategy_engine",
            matches=matches,
            expected=self._is_expected("strategy_engine", trading_day_check),
        )

    def _check_signal_card(self, trading_day_check: HealthCheckResult) -> HealthCheckResult:
        output_path = Path(settings.t0_output_dir) / "live_signal_card.json"
        if not output_path.exists():
            status = "warn" if self._is_expected("strategy_engine", trading_day_check) else "skip"
            return HealthCheckResult(
                name="signal_card",
                component="strategy_engine",
                status=status,
                message=f"Signal card not found at {output_path}",
                details={"path": str(output_path)},
            )

        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return HealthCheckResult(
                name="signal_card",
                component="strategy_engine",
                status="warn",
                message=f"Signal card is unreadable: {exc}",
                details={"path": str(output_path)},
            )

        details = {
            "path": str(output_path),
            "signal_action": payload.get("signal", {}).get("action"),
            "as_of_time": payload.get("as_of_time"),
            "regime": payload.get("regime"),
        }
        return HealthCheckResult(
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
    ) -> HealthCheckResult:
        details = {
            "count": len(matches),
            "pids": [match["pid"] for match in matches],
        }
        if matches:
            return HealthCheckResult(
                name=name,
                component=component,
                status="pass",
                message=f"{component} process is running",
                details=details,
            )

        if expected:
            return HealthCheckResult(
                name=name,
                component=component,
                status="warn",
                message=f"{component} process is not running during its expected window",
                details=details,
            )

        return HealthCheckResult(
            name=name,
            component=component,
            status="skip",
            message=f"{component} process is not expected to be running right now",
            details=details,
        )

    def _derive_overall_status(self, checks: List[HealthCheckResult]) -> str:
        if any(check.status == "fail" and check.critical for check in checks):
            return "down"
        if any(check.status in {"fail", "warn"} for check in checks):
            return "degraded"
        return "ok"

    def _summarize_checks(self, checks: List[HealthCheckResult]) -> Dict[str, int]:
        summary = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
        for check in checks:
            summary[check.status] = summary.get(check.status, 0) + 1
        return summary

    def _is_expected(self, component: str, trading_day_check: HealthCheckResult) -> bool:
        if trading_day_check.status != "pass":
            return False

        now = datetime.now().time()
        windows = {
            "qmt": (time(8, 15), time(21, 5)),
            "trading_engine": (time(8, 35), time(21, 5)),
            "strategy_engine": (time(9, 20), time(15, 5)),
        }
        start_time, end_time = windows[component]
        return start_time <= now <= end_time

    def _list_processes(self) -> List[Dict[str, Any]]:
        if os.name == "nt":
            command = [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process | "
                    "Select-Object Name,ProcessId,CommandLine | ConvertTo-Json -Compress"
                ),
            ]
        else:
            command = ["ps", "-eo", "pid=,comm=,args="]

        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=self.timeout_seconds,
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
                    "command_line": item.get("CommandLine") or "",
                }
                for item in data
            ]

        processes = []
        for line in result.stdout.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) != 3:
                continue
            pid_text, name, command_line = parts
            try:
                pid = int(pid_text)
            except ValueError:
                continue
            processes.append({"name": name, "pid": pid, "command_line": command_line})
        return processes


class _HealthRequestHandler(BaseHTTPRequestHandler):
    snapshot_store: HealthSnapshotStore
    ws_manager: WebSocketManager

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
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def _handle_websocket(self):
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
            from xtquant import xtdata
            account_id = settings.qmt_account_id
            positions = xtdata.get_stock_position(account_id) or {}
            result = [{"stock_code": k, **v} for k, v in positions.items()]
            self._send_json_response(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
        except Exception as e:
            self._send_error_response(f"Failed to get positions: {e}")

    def _handle_orders(self, query_params: Dict) -> None:
        try:
            page = int(query_params.get("page", ["1"])[0])
            limit = int(query_params.get("limit", ["100"])[0])
            offset = (page - 1) * limit

            engine = create_engine(settings.db_url)
            Session = sessionmaker(bind=engine)
            session = Session()

            total = session.query(OrderRecord).count()
            orders = session.query(OrderRecord).order_by(desc(OrderRecord.order_time)).offset(offset).limit(limit).all()

            result = {
                "total": total,
                "page": page,
                "limit": limit,
                "data": [{"id": o.id, "signal_id": o.signal_id, "order_id": o.order_id,
                          "stock_code": o.stock_code, "direction": o.direction, "volume": o.volume,
                          "price": o.price, "order_status": o.order_status,
                          "filled_volume": o.filled_volume, "filled_price": o.filled_price,
                          "order_time": o.order_time.isoformat() if o.order_time else None,
                          "filled_time": o.filled_time.isoformat() if o.filled_time else None}
                         for o in orders]
            }
            session.close()
            engine.dispose()
            self._send_json_response(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
        except Exception as e:
            self._send_error_response(f"Failed to get orders: {e}")

    def _handle_signals(self, query_params: Dict) -> None:
        try:
            page = int(query_params.get("page", ["1"])[0])
            limit = int(query_params.get("limit", ["100"])[0])
            offset = (page - 1) * limit

            engine = create_engine(settings.db_url)
            Session = sessionmaker(bind=engine)
            session = Session()

            total = session.query(TradingSignal).count()
            signals = session.query(TradingSignal).order_by(desc(TradingSignal.signal_time)).offset(offset).limit(limit).all()

            result = {
                "total": total,
                "page": page,
                "limit": limit,
                "data": [{"id": s.id, "signal_id": s.signal_id, "stock_code": s.stock_code,
                          "direction": s.direction, "volume": s.volume, "price": s.price,
                          "processed": s.processed, "error_message": s.error_message,
                          "signal_time": s.signal_time.isoformat() if s.signal_time else None}
                         for s in signals]
            }
            session.close()
            engine.dispose()
            self._send_json_response(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
        except Exception as e:
            self._send_error_response(f"Failed to get signals: {e}")

    def _handle_trades(self, query_params: Dict) -> None:
        try:
            page = int(query_params.get("page", ["1"])[0])
            limit = int(query_params.get("limit", ["100"])[0])
            offset = (page - 1) * limit

            engine = create_engine(settings.db_url)
            Session = sessionmaker(bind=engine)
            session = Session()

            total = session.query(OrderRecord).filter(OrderRecord.filled_volume > 0).count()
            trades = session.query(OrderRecord).filter(OrderRecord.filled_volume > 0).order_by(desc(OrderRecord.filled_time)).offset(offset).limit(limit).all()

            result = {
                "total": total,
                "page": page,
                "limit": limit,
                "data": [{"id": t.id, "order_id": t.order_id, "stock_code": t.stock_code,
                          "direction": t.direction, "filled_volume": t.filled_volume,
                          "filled_price": t.filled_price,
                          "filled_time": t.filled_time.isoformat() if t.filled_time else None}
                         for t in trades]
            }
            session.close()
            engine.dispose()
            self._send_json_response(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
        except Exception as e:
            self._send_error_response(f"Failed to get trades: {e}")

    def _handle_pnl(self) -> None:
        try:
            engine = create_engine(settings.db_url)
            Session = sessionmaker(bind=engine)
            session = Session()
            trades = session.query(OrderRecord).filter(OrderRecord.filled_volume > 0).all()

            pnl_by_stock = {}
            for t in trades:
                if t.stock_code not in pnl_by_stock:
                    pnl_by_stock[t.stock_code] = {"buy_amount": 0, "sell_amount": 0, "pnl": 0}
                amount = t.filled_volume * (t.filled_price or 0)
                if t.direction == "BUY":
                    pnl_by_stock[t.stock_code]["buy_amount"] += amount
                else:
                    pnl_by_stock[t.stock_code]["sell_amount"] += amount
                    pnl_by_stock[t.stock_code]["pnl"] = pnl_by_stock[t.stock_code]["sell_amount"] - pnl_by_stock[t.stock_code]["buy_amount"]

            result = [{"stock_code": k, **v} for k, v in pnl_by_stock.items()]
            session.close()
            engine.dispose()
            self._send_json_response(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
        except Exception as e:
            self._send_error_response(f"Failed to calculate PnL: {e}")

    def _send_json_response(self, payload: bytes, status_code: int = HTTPStatus.OK) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_error_response(self, message: str) -> None:
        payload = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self._send_json_response(payload, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: Any) -> None:
        return


def serve_healthcheck(host: str, port: int, scope: str = "project") -> None:
    bind_host = resolve_healthcheck_host(host)
    snapshot_store = HealthSnapshotStore(
        scope=scope,
        refresh_interval_seconds=settings.healthcheck_refresh_interval_seconds,
    )
    snapshot_store.start()
    handler = type(
        "HealthRequestHandler", (_HealthRequestHandler,), {"snapshot_store": snapshot_store}
    )
    server = ThreadingHTTPServer((bind_host, port), handler)
    logger.info("Health check server listening on http://{}:{}/health", bind_host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Health check server stopped by signal")
    finally:
        server.server_close()
        snapshot_store.stop()


def start_healthcheck_server(host: str, port: int, scope: str = "project") -> bool:
    """Start the HTTP health check server in a background daemon thread."""
    global _server_instance, _server_thread, _snapshot_store, _ws_manager

    bind_host = resolve_healthcheck_host(host)

    with _server_lock:
        if (
            _server_instance is not None
            and _server_thread is not None
            and _server_thread.is_alive()
        ):
            logger.debug(
                "Health check server already running on http://{}:{}/health", bind_host, port
            )
            return True

        snapshot_store = HealthSnapshotStore(
            scope=scope,
            refresh_interval_seconds=settings.healthcheck_refresh_interval_seconds,
        )
        snapshot_store.start()

        ws_manager = WebSocketManager()
        ws_manager.start()

        handler = type(
            "HealthRequestHandler",
            (_HealthRequestHandler,),
            {"snapshot_store": snapshot_store, "ws_manager": ws_manager},
        )
        try:
            server = ThreadingHTTPServer((bind_host, port), handler)
        except OSError as exc:
            snapshot_store.stop()
            ws_manager.stop()
            logger.warning(
                "Health check server could not bind to http://{}:{}/health: {}",
                bind_host,
                port,
                exc,
            )
            return False

        thread = threading.Thread(
            target=server.serve_forever,
            name=f"healthcheck-{bind_host}:{port}",
            daemon=True,
        )
        thread.start()
        _server_instance = server
        _server_thread = thread
        _snapshot_store = snapshot_store
        _ws_manager = ws_manager
        logger.info("Health check server started on http://{}:{}/health", bind_host, port)
        logger.info("WebSocket server available on ws://{}:{}/ws", bind_host, port)
        return True


def stop_healthcheck_server() -> None:
    """Stop the background health check server if it is running."""
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
