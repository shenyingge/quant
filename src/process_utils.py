from __future__ import annotations

from typing import Any, Dict, List, Sequence


def find_matching_processes(
    processes: Sequence[Dict[str, Any]],
    command_patterns: Sequence[str],
) -> List[Dict[str, Any]]:
    patterns = tuple(pattern.lower() for pattern in command_patterns)
    matches = [
        process
        for process in processes
        if any(pattern in (process.get("command_line") or "").lower() for pattern in patterns)
    ]
    return collapse_nested_processes(matches)


def collapse_nested_processes(processes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not processes:
        return []

    matched_pids = {
        pid
        for pid in (_coerce_pid(process.get("pid")) for process in processes)
        if pid > 0
    }
    if not matched_pids:
        return list(processes)

    logical_processes: List[Dict[str, Any]] = []
    for process in processes:
        pid = _coerce_pid(process.get("pid"))
        parent_pid = _coerce_pid(process.get("parent_pid"))
        if pid > 0 and parent_pid > 0 and parent_pid != pid and parent_pid in matched_pids:
            continue
        logical_processes.append(process)

    return logical_processes


def _coerce_pid(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
