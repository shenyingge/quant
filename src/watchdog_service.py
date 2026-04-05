from __future__ import annotations

import json
import os
import signal
import subprocess
import time as time_module
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import psutil

from src.config import settings
from src.infrastructure.scheduling.minute_history import get_minute_daily_ingest_schedule_time
from src.logger_config import configured_logger as logger
from src.infrastructure.notifications import FeishuNotifier
from src.process_utils import find_matching_processes
from src.trading.trading_day_checker import is_trading_day


@dataclass(frozen=True)
class ManagedTarget:
    name: str
    kind: str
    description: str
    command_patterns: Sequence[str]
    launch_command: Sequence[str]
    require_trading_day: bool = False
    start_time: Optional[time] = None
    stop_time: Optional[time] = None
    schedule_time: Optional[time] = None
    enforce_stop_outside_window: bool = False
    probe_path: Optional[str] = None


class QuantWatchdogService:
    def __init__(self, *, dry_run: bool = False):
        self.repo_root = Path(__file__).resolve().parents[1]
        self.dry_run = dry_run
        self.check_interval_seconds = max(int(settings.watchdog_check_interval_seconds), 5)
        self.min_restart_interval_seconds = max(int(settings.watchdog_min_restart_interval_seconds), 5)
        self.job_max_delay_minutes = max(int(settings.watchdog_job_max_delay_minutes), 1)
        self.enforce_stop_outside_window = bool(settings.watchdog_enforce_stop_outside_window)
        self.state_path = self._resolve_state_path(settings.watchdog_state_path)
        self._state = self._load_state()
        self._last_launch_attempt: Dict[str, float] = {}
        self._probe_failure_counts: Dict[str, int] = {}
        self._trading_day_cache: Dict[str, Any] = {"date": None, "value": False}
        self.targets = self._build_targets()
        self.notifier = FeishuNotifier()
        self._shutdown_requested = False

    def run_forever(self) -> None:
        logger.info(
            "Starting watchdog service with {} managed target(s), interval={}s, dry_run={}",
            len(self.targets),
            self.check_interval_seconds,
            self.dry_run,
        )
        self._log_target_inventory()

        # 发送启动通知
        self.notifier.notify_runtime_event("看门狗服务", "已启动", f"管理 {len(self.targets)} 个目标", "success")

        try:
            while not self._shutdown_requested:
                self.run_once()
                time_module.sleep(self.check_interval_seconds)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            # 发送关闭通知
            self.notifier.notify_runtime_event("看门狗服务", "已停止", "服务正常关闭", "info")

    def run_once(self) -> None:
        now = datetime.now()
        trading_day = self._get_trading_day_status(now.date())
        processes = self._list_processes()

        logger.info(
            "Watchdog cycle started at {} | trading_day={} | processes={}",
            now.isoformat(timespec="seconds"),
            trading_day,
            len(processes),
        )

        for target in self.targets:
            matches = self._find_matching_processes(processes, target.command_patterns)

            if target.kind == "service":
                expected = self._is_service_expected(target, now, trading_day)
                self._reconcile_service(target, matches, expected)
                continue

            self._reconcile_job(target, matches, now, trading_day)

    def _build_targets(self) -> List[ManagedTarget]:
        targets: List[ManagedTarget] = [
            ManagedTarget(
                name="cms_service",
                kind="service",
                description="Standalone HTTP CMS service",
                command_patterns=("main.py cms-server",),
                launch_command=self._cms_server_command(),
                probe_path="/health",
            )
        ]

        if settings.watchdog_enable_trading_service:
            targets.append(
                ManagedTarget(
                    name="trading_engine",
                    kind="service",
                    description="Trading engine",
                    command_patterns=("main.py run", "main.py test-run"),
                    launch_command=self._trading_engine_command(),
                    require_trading_day=True,
                    start_time=self._parse_clock(settings.watchdog_trading_start_time),
                    stop_time=self._parse_clock(settings.watchdog_trading_stop_time),
                    enforce_stop_outside_window=self.enforce_stop_outside_window,
                )
            )

        if settings.t0_strategy_enabled and settings.watchdog_enable_t0_daemon:
            targets.append(
                ManagedTarget(
                    name="strategy_engine",
                    kind="service",
                    description="T0 strategy daemon",
                    command_patterns=("main.py t0-daemon",),
                    launch_command=self._strategy_engine_command(),
                    require_trading_day=True,
                    start_time=self._parse_clock(settings.watchdog_t0_start_time),
                    stop_time=self._parse_clock(settings.watchdog_t0_stop_time),
                    enforce_stop_outside_window=self.enforce_stop_outside_window,
                )
            )

        if settings.t0_strategy_enabled and settings.watchdog_enable_t0_reconcile:
            targets.append(
                ManagedTarget(
                    name="t0_reconcile",
                    kind="job",
                    description="T0 end-of-day reconciliation",
                    command_patterns=("main.py t0-reconcile",),
                    launch_command=self._python_main_command("t0-reconcile"),
                    require_trading_day=True,
                    schedule_time=self._parse_clock(settings.watchdog_t0_reconcile_time),
                )
            )

        targets.append(
            ManagedTarget(
                name="minute_history_ingest_daily",
                kind="job",
                description="Daily minute history ingest to Meta DB",
                command_patterns=("main.py ingest-minute-daily",),
                launch_command=self._python_main_command("ingest-minute-daily"),
                require_trading_day=True,
                schedule_time=get_minute_daily_ingest_schedule_time(),
            )
        )

        return targets

    def _reconcile_service(
        self,
        target: ManagedTarget,
        matches: List[Dict[str, Any]],
        expected: bool,
    ) -> None:
        healthy = self._is_service_healthy(target, matches)

        if healthy and expected:
            self._probe_failure_counts[target.name] = 0
            logger.info("{} is healthy with {} logical process(es)", target.name, len(matches))
            return

        if matches and not expected:
            self._probe_failure_counts[target.name] = 0
            if target.enforce_stop_outside_window:
                self._stop_processes(target, matches)
            else:
                logger.info("{} is running outside its window, leaving it untouched", target.name)
            return

        if matches and expected and not healthy:
            failure_count = self._record_probe_failure(target)
            logger.warning(
                "{} has {} logical process(es) but failed its readiness probe ({})",
                target.name,
                len(matches),
                failure_count,
            )
            if target.probe_path and failure_count < 3:
                logger.warning(
                    "{} will be left running until it fails {} consecutive readiness probes",
                    target.name,
                    3,
                )
                return
            self._stop_processes(target, matches)
            self._probe_failure_counts[target.name] = 0

        if not expected:
            self._probe_failure_counts[target.name] = 0
            logger.info("{} is not expected to run right now", target.name)
            return

        self._launch_target(target)

    def _is_service_healthy(
        self,
        target: ManagedTarget,
        matches: List[Dict[str, Any]],
    ) -> bool:
        if not matches:
            return False

        if target.probe_path:
            return self._probe_cms_server_endpoint(target)

        return True

    def _probe_cms_server_endpoint(self, target: ManagedTarget) -> bool:
        host = (settings.cms_server_host or "").strip()
        if not host or host in {"0.0.0.0", "::"}:
            host = "127.0.0.1"
        elif host.lower() == "tailscale":
            host = "127.0.0.1"

        path = target.probe_path or "/health"
        url = f"http://{host}:{settings.cms_server_port}{path}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        timeout_seconds = max(settings.cms_server_timeout_seconds, 5)

        try:
            with opener.open(url, timeout=timeout_seconds) as response:
                return int(getattr(response, "status", 0)) == 200
        except Exception as exc:
            logger.warning("CMS probe failed for {} via {}: {}", target.name, url, exc)
            return False

    def _record_probe_failure(self, target: ManagedTarget) -> int:
        count = self._probe_failure_counts.get(target.name, 0) + 1
        self._probe_failure_counts[target.name] = count
        return count

    def _reconcile_job(
        self,
        target: ManagedTarget,
        matches: List[Dict[str, Any]],
        now: datetime,
        trading_day: bool,
    ) -> None:
        if matches:
            logger.info("{} is already running", target.name)
            return

        if target.require_trading_day and not trading_day:
            logger.info("{} is skipped because today is not a trading day", target.name)
            return

        if target.schedule_time and now.time() < target.schedule_time:
            logger.info(
                "{} is scheduled for {} and will wait",
                target.name,
                target.schedule_time.strftime("%H:%M"),
            )
            return

        if target.schedule_time and not self._is_job_within_trigger_window(target, now):
            logger.info("{} is outside its allowed trigger window", target.name)
            return

        if self._was_job_triggered_today(target.name, now.date()):
            logger.info("{} has already been triggered today", target.name)
            return

        if self._launch_target(target) and not self.dry_run:
            self._mark_job_triggered(target.name, now)

    def _is_service_expected(self, target: ManagedTarget, now: datetime, trading_day: bool) -> bool:
        if target.require_trading_day and not trading_day:
            return False

        if target.start_time is None or target.stop_time is None:
            return True

        return target.start_time <= now.time() <= target.stop_time

    def _launch_target(self, target: ManagedTarget) -> bool:
        if not self._can_launch(target.name):
            logger.warning(
                "Skipping {} launch because the restart cooldown is still active", target.name
            )
            return False

        command_text = " ".join(target.launch_command)
        if self.dry_run:
            logger.warning("Dry run: would launch {} via: {}", target.name, command_text)
        else:
            logger.warning("Launching {} via: {}", target.name, command_text)
            # 发送拉起通知
            self.notifier.notify_runtime_event(
                "看门狗服务", f"拉起服务: {target.description}", f"目标: {target.name}", "warning"
            )
        self._last_launch_attempt[target.name] = time_module.time()

        if self.dry_run:
            return True

        creationflags = 0
        if os.name == "nt":
            creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
            creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)

        subprocess.Popen(
            list(target.launch_command),
            cwd=str(self.repo_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        return True

    def _stop_processes(self, target: ManagedTarget, matches: List[Dict[str, Any]]) -> None:
        pids = [match["pid"] for match in matches]
        logger.warning("{} is outside its window, stopping pid(s): {}", target.name, pids)

        if self.dry_run:
            return

        for pid in pids:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                capture_output=True,
                text=True,
            )

    def _can_launch(self, target_name: str) -> bool:
        last_attempt = self._last_launch_attempt.get(target_name)
        if last_attempt is None:
            return True
        return (time_module.time() - last_attempt) >= self.min_restart_interval_seconds

    def _was_job_triggered_today(self, target_name: str, current_date: date) -> bool:
        jobs = self._state.get("jobs", {})
        raw_value = jobs.get(target_name)
        if not raw_value:
            return False

        try:
            triggered_at = datetime.fromisoformat(raw_value)
        except ValueError:
            return False

        return triggered_at.date() == current_date

    def _mark_job_triggered(self, target_name: str, now: datetime) -> None:
        jobs = self._state.setdefault("jobs", {})
        jobs[target_name] = now.isoformat(timespec="seconds")
        self._save_state()

    def _is_job_within_trigger_window(self, target: ManagedTarget, now: datetime) -> bool:
        if target.schedule_time is None:
            return True

        scheduled_at = datetime.combine(now.date(), target.schedule_time)
        deadline = scheduled_at + timedelta(minutes=self.job_max_delay_minutes)
        return now <= deadline

    def _get_trading_day_status(self, current_date: date) -> bool:
        cached_date = self._trading_day_cache.get("date")
        if cached_date == current_date.isoformat():
            return bool(self._trading_day_cache.get("value"))

        try:
            value = bool(is_trading_day())
        except Exception as exc:
            logger.error("Failed to determine trading day status: {}", exc)
            value = False

        self._trading_day_cache = {"date": current_date.isoformat(), "value": value}
        return value

    def _log_target_inventory(self) -> None:
        for target in self.targets:
            if target.kind == "service":
                window_text = (
                    "24x7"
                    if target.start_time is None or target.stop_time is None
                    else f"{target.start_time.strftime('%H:%M')}-{target.stop_time.strftime('%H:%M')}"
                )
            else:
                window_text = target.schedule_time.strftime("%H:%M") if target.schedule_time else "manual"

            logger.info(
                "Managed target | name={} | kind={} | trading_day={} | window={} | description={}",
                target.name,
                target.kind,
                target.require_trading_day,
                window_text,
                target.description,
            )

    def _resolve_state_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate
        return self.repo_root / candidate

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {"jobs": {}}

        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read watchdog state from {}: {}", self.state_path, exc)
            return {"jobs": {}}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _parse_clock(self, raw_value: str) -> time:
        return datetime.strptime(raw_value.strip(), "%H:%M").time()

    def _python_main_command(self, *args: str) -> List[str]:
        return [str(self._resolve_python_executable()), "main.py", *args]

    def _cms_server_command(self) -> List[str]:
        host = (settings.cms_server_host or "").strip() or "127.0.0.1"
        return self._python_main_command(
            "cms-server",
            f"--host={host}",
            f"--port={settings.cms_server_port}",
        )

    def _trading_engine_command(self) -> List[str]:
        return self._python_main_command("run")

    def _strategy_engine_command(self) -> List[str]:
        return self._python_main_command("t0-daemon")

    def _resolve_python_executable(self) -> Path:
        if os.name == "nt":
            candidate = self.repo_root / ".venv" / "Scripts" / "python.exe"
        else:
            candidate = self.repo_root / ".venv" / "bin" / "python"

        if candidate.exists():
            return candidate

        return Path("python")

    def _find_matching_processes(
        self,
        processes: List[Dict[str, Any]],
        command_patterns: Sequence[str],
    ) -> List[Dict[str, Any]]:
        return find_matching_processes(processes, command_patterns)

    def _list_processes(self) -> List[Dict[str, Any]]:
        if os.name == "nt":
            try:
                return self._list_processes_windows_native()
            except Exception as exc:
                logger.warning(
                    "Native Windows process listing failed for watchdog, falling back to PowerShell: {}",
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
                timeout=max(int(settings.cms_server_timeout_seconds), 8),
            )
        except Exception as exc:
            logger.warning("Failed to list processes for watchdog: {}", exc)
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
                    "name": item.get("Name") or "",
                    "pid": int(item.get("ProcessId") or 0),
                    "parent_pid": int(item.get("ParentProcessId") or 0),
                    "command_line": item.get("CommandLine") or "",
                }
                for item in data
            ]

        processes: List[Dict[str, Any]] = []
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
            command_line = " ".join(str(part) for part in cmdline_parts if part)
            processes.append(
                {
                    "name": info.get("name") or "",
                    "pid": int(info.get("pid") or 0),
                    "parent_pid": int(info.get("ppid") or 0),
                    "command_line": command_line,
                }
            )

        return processes


def run_watchdog_service(*, once: bool = False, dry_run: bool = False) -> None:
    watchdog = QuantWatchdogService(dry_run=dry_run)
    if once:
        watchdog.run_once()
        return
    watchdog.run_forever()
