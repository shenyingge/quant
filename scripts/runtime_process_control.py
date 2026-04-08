from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Iterable

import psutil


MANAGED_COMMANDS = {"watchdog", "cms-server", "run", "test-run"}
WATCHDOG_COMMAND = "watchdog"
PID_FILE_NAMES = ("watchdog.pid", "cms-server.pid", "run.pid")


def _iter_managed_processes() -> list[psutil.Process]:
    current_pid = psutil.Process().pid
    matches: list[psutil.Process] = []

    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            pid = int(proc.info.get("pid") or 0)
            cmdline = list(proc.info.get("cmdline") or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

        if pid <= 0 or pid == current_pid:
            continue

        if _is_managed_main_py_command(cmdline):
            matches.append(proc)

    return matches


def _is_managed_main_py_command(cmdline: Iterable[str]) -> bool:
    parts = [str(part) for part in cmdline]
    for idx, token in enumerate(parts[:-1]):
        if token.endswith("main.py") and parts[idx + 1] in MANAGED_COMMANDS:
            return True
    return False


def _is_watchdog_process(cmdline: Iterable[str]) -> bool:
    parts = [str(part) for part in cmdline]
    for idx, token in enumerate(parts[:-1]):
        if token.endswith("main.py") and parts[idx + 1] == WATCHDOG_COMMAND:
            return True
    return False


def check_watchdog() -> int:
    for proc in psutil.process_iter(["cmdline"]):
        try:
            if _is_watchdog_process(proc.info.get("cmdline") or []):
                return 0
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return 1


def stop_managed_processes(*, log_dir: str) -> int:
    matches = _iter_managed_processes()

    if not matches:
        print("no managed runtime processes found")
    else:
        print("stopping pids:", ", ".join(str(proc.pid) for proc in matches))
        for proc in matches:
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        _, alive = psutil.wait_procs(matches, timeout=5)
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if alive:
            psutil.wait_procs(alive, timeout=3)

    log_path = pathlib.Path(log_dir)
    for name in PID_FILE_NAMES:
        (log_path / name).unlink(missing_ok=True)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Managed runtime process control")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check-watchdog")

    stop_parser = subparsers.add_parser("stop-all")
    stop_parser.add_argument("--log-dir", default="./logs/current")

    args = parser.parse_args()

    if args.command == "check-watchdog":
        return check_watchdog()
    if args.command == "stop-all":
        return stop_managed_processes(log_dir=args.log_dir)

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
