"""Standardized project health checks and a lightweight HTTP endpoint."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time as time_module
from dataclasses import asdict, dataclass, field
from datetime import datetime, time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import redis
from sqlalchemy import create_engine, text

from src.config import settings
from src.logger_config import configured_logger as logger
from src.trading_day_checker import is_trading_day

_server_lock = threading.Lock()
_server_instance: Optional[ThreadingHTTPServer] = None
_server_thread: Optional[threading.Thread] = None
_snapshot_store: Optional["HealthSnapshotStore"] = None


def _timestamp_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _project_version() -> str:
    try:
        return version("quant")
    except PackageNotFoundError:
        return "0.1.0"


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

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in {"/health", "/healthz"}:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        snapshot = self.snapshot_store.get_snapshot().to_dict()
        payload = json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8")
        status_code = (
            HTTPStatus.OK if snapshot["status"] != "down" else HTTPStatus.SERVICE_UNAVAILABLE
        )

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        return


def serve_healthcheck(host: str, port: int, scope: str = "project") -> None:
    snapshot_store = HealthSnapshotStore(
        scope=scope,
        refresh_interval_seconds=settings.healthcheck_refresh_interval_seconds,
    )
    snapshot_store.start()
    handler = type(
        "HealthRequestHandler", (_HealthRequestHandler,), {"snapshot_store": snapshot_store}
    )
    server = ThreadingHTTPServer((host, port), handler)
    logger.info("Health check server listening on http://%s:%s/health", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Health check server stopped by signal")
    finally:
        server.server_close()
        snapshot_store.stop()


def start_healthcheck_server(host: str, port: int, scope: str = "project") -> bool:
    """Start the HTTP health check server in a background daemon thread."""
    global _server_instance, _server_thread, _snapshot_store

    with _server_lock:
        if (
            _server_instance is not None
            and _server_thread is not None
            and _server_thread.is_alive()
        ):
            logger.debug("Health check server already running on http://%s:%s/health", host, port)
            return True

        snapshot_store = HealthSnapshotStore(
            scope=scope,
            refresh_interval_seconds=settings.healthcheck_refresh_interval_seconds,
        )
        snapshot_store.start()
        handler = type(
            "HealthRequestHandler",
            (_HealthRequestHandler,),
            {"snapshot_store": snapshot_store},
        )
        try:
            server = ThreadingHTTPServer((host, port), handler)
        except OSError as exc:
            snapshot_store.stop()
            logger.warning(
                "Health check server could not bind to http://%s:%s/health: %s",
                host,
                port,
                exc,
            )
            return False

        thread = threading.Thread(
            target=server.serve_forever,
            name=f"healthcheck-{host}:{port}",
            daemon=True,
        )
        thread.start()
        _server_instance = server
        _server_thread = thread
        _snapshot_store = snapshot_store
        logger.info("Health check server started on http://%s:%s/health", host, port)
        return True


def stop_healthcheck_server() -> None:
    """Stop the background health check server if it is running."""
    global _server_instance, _server_thread, _snapshot_store

    with _server_lock:
        if _server_instance is None:
            return

        server = _server_instance
        thread = _server_thread
        snapshot_store = _snapshot_store
        _server_instance = None
        _server_thread = None
        _snapshot_store = None

    try:
        server.shutdown()
    finally:
        server.server_close()
        if snapshot_store is not None:
            snapshot_store.stop()
        if thread is not None:
            thread.join(timeout=2)
