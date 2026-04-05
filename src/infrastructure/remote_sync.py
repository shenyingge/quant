#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Remote file sync helpers backed by rsync over SSH.
"""

import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Iterable, List, Optional, Union

from src.config import settings

PathLike = Union[str, Path]
DEFAULT_RSYNC_RETRIES = 3


def normalize_identity_file_path(identity_file: Optional[str]) -> Optional[str]:
    """Normalize SSH identity paths from config for Windows and local usage."""
    if not identity_file:
        return None

    normalized = str(identity_file).strip()
    if not normalized:
        return None

    unix_style_match = re.match(r"^/([A-Za-z])/(.*)$", normalized.replace("\\", "/"))
    if unix_style_match:
        drive = unix_style_match.group(1).upper()
        remainder = unix_style_match.group(2).replace("/", "\\")
        return f"{drive}:\\{remainder}"

    windows_style_match = re.match(r"^\\([A-Za-z])\\(.*)$", normalized)
    if windows_style_match:
        drive = windows_style_match.group(1).upper()
        remainder = windows_style_match.group(2)
        return f"{drive}:\\{remainder}"

    return str(Path(normalized).expanduser())


def normalize_local_path_for_rsync(path: PathLike) -> str:
    """Convert local paths into a format that MSYS/Cygwin rsync understands."""
    resolved = Path(path).expanduser().resolve()
    raw = str(resolved)

    if os.name == "nt" and len(raw) >= 2 and raw[1] == ":":
        drive = raw[0].lower()
        remainder = raw[2:].replace("\\", "/")
        return f"/{drive}{remainder}"

    return raw.replace("\\", "/")


def join_remote_path(base: str, *parts: str) -> str:
    """Join remote path fragments without touching leading ~/ or / prefixes."""
    current = base.rstrip("/")
    for part in parts:
        cleaned = (part or "").strip("/")
        if cleaned:
            current = f"{current}/{cleaned}" if current else cleaned
    return current


def resolve_remote_base_dir(_unused_ssh, remote_base: str) -> str:
    """Keep the remote base path unchanged so the remote shell can expand ~."""
    return remote_base


def _normalize_command_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    normalized = normalize_identity_file_path(path)
    if not normalized:
        return None
    return normalized.replace("\\", "/")


def _resolve_ssh_options(
    alias_or_host: Optional[str],
    username: Optional[str] = None,
    port: Optional[int] = None,
    identity_file: Optional[str] = None,
) -> dict:
    target = alias_or_host or settings.ns_host
    resolved_username = username
    resolved_port = port
    resolved_identity = identity_file

    if target == settings.ns_host:
        resolved_username = resolved_username or settings.ns_ssh_username
        resolved_port = resolved_port or settings.ns_ssh_port
        resolved_identity = resolved_identity or settings.ns_ssh_key_file

    return {
        "target": target,
        "username": resolved_username,
        "port": resolved_port or 22,
        "identity_file": _normalize_command_path(resolved_identity),
    }


def _build_ssh_base_command(
    *,
    username: Optional[str],
    port: int,
    identity_file: Optional[str],
    timeout: int,
) -> List[str]:
    command = [
        settings.ssh_bin,
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout}",
    ]
    if username:
        command.extend(["-l", username])
    if port:
        command.extend(["-p", str(port)])
    if identity_file:
        command.extend(["-i", identity_file])
    return command


def _build_rsync_transport(ssh_command: List[str]) -> str:
    return " ".join(shlex.quote(part) for part in ssh_command)


def _run_checked_command(command: List[str], timeout: Optional[int] = None) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(detail or f"Command failed with exit code {exc.returncode}") from exc


def _ensure_remote_dir(
    remote_dir: str,
    *,
    alias_or_host: Optional[str],
    username: Optional[str] = None,
    port: Optional[int] = None,
    identity_file: Optional[str] = None,
    timeout: int = 20,
) -> None:
    options = _resolve_ssh_options(
        alias_or_host=alias_or_host,
        username=username,
        port=port,
        identity_file=identity_file,
    )
    ssh_command = _build_ssh_base_command(
        username=options["username"],
        port=options["port"],
        identity_file=options["identity_file"],
        timeout=timeout,
    )
    _run_checked_command(
        ssh_command + [options["target"], f"mkdir -p {shlex.quote(remote_dir)}"],
        timeout=timeout + 5,
    )


def _run_rsync(
    sources: List[str],
    destination: str,
    *,
    alias_or_host: Optional[str],
    username: Optional[str] = None,
    port: Optional[int] = None,
    identity_file: Optional[str] = None,
    timeout: int = 20,
    max_retries: int = DEFAULT_RSYNC_RETRIES,
) -> None:
    options = _resolve_ssh_options(
        alias_or_host=alias_or_host,
        username=username,
        port=port,
        identity_file=identity_file,
    )
    ssh_command = _build_ssh_base_command(
        username=options["username"],
        port=options["port"],
        identity_file=options["identity_file"],
        timeout=timeout,
    )
    command = [
        settings.rsync_bin,
        "-az",
        "--partial",
        "--append-verify",
        f"--timeout={timeout}",
        "-e",
        _build_rsync_transport(ssh_command),
        *sources,
        destination,
    ]

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            _run_checked_command(command)
            return
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            time.sleep(min(attempt * 2, 10))

    if last_error:
        raise last_error
    raise RuntimeError("rsync failed without an explicit error")


def sync_files_via_rsync(
    files: Iterable[PathLike],
    remote_subdir: str = "",
    remote_base: Optional[str] = None,
    alias_or_host: Optional[str] = None,
    timeout: int = 20,
    username: Optional[str] = None,
    port: Optional[int] = None,
    identity_file: Optional[str] = None,
    max_retries: int = DEFAULT_RSYNC_RETRIES,
) -> List[str]:
    """Sync files to a remote host and return their remote paths."""
    local_files = [Path(file).expanduser().resolve() for file in files]
    if not local_files:
        return []

    remote_dir = join_remote_path(remote_base or settings.ns_scp_remote_dir, remote_subdir)
    _ensure_remote_dir(
        remote_dir,
        alias_or_host=alias_or_host,
        username=username,
        port=port,
        identity_file=identity_file,
        timeout=timeout,
    )

    destination = f"{(alias_or_host or settings.ns_host)}:{remote_dir.rstrip('/')}/"
    _run_rsync(
        sources=[normalize_local_path_for_rsync(path) for path in local_files],
        destination=destination,
        alias_or_host=alias_or_host,
        username=username,
        port=port,
        identity_file=identity_file,
        timeout=timeout,
        max_retries=max_retries,
    )
    return [join_remote_path(remote_dir, path.name) for path in local_files]


def sync_tree_via_rsync(
    local_root: PathLike,
    remote_subdir: str = "",
    remote_base: Optional[str] = None,
    alias_or_host: Optional[str] = None,
    timeout: int = 20,
    username: Optional[str] = None,
    port: Optional[int] = None,
    identity_file: Optional[str] = None,
    max_retries: int = DEFAULT_RSYNC_RETRIES,
) -> List[str]:
    """Sync a directory tree while preserving relative paths."""
    root = Path(local_root).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Local path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Local path is not a directory: {root}")

    remote_root = join_remote_path(remote_base or settings.ns_scp_remote_dir, remote_subdir)
    _ensure_remote_dir(
        remote_root,
        alias_or_host=alias_or_host,
        username=username,
        port=port,
        identity_file=identity_file,
        timeout=timeout,
    )

    source = f"{normalize_local_path_for_rsync(root)}/"
    destination = f"{(alias_or_host or settings.ns_host)}:{remote_root.rstrip('/')}/"
    _run_rsync(
        sources=[source],
        destination=destination,
        alias_or_host=alias_or_host,
        username=username,
        port=port,
        identity_file=identity_file,
        timeout=timeout,
        max_retries=max_retries,
    )
    return [
        join_remote_path(remote_root, path.relative_to(root).as_posix())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def sync_file_via_rsync(
    file: PathLike,
    remote_subdir: str = "",
    remote_base: Optional[str] = None,
    alias_or_host: Optional[str] = None,
    timeout: int = 20,
    username: Optional[str] = None,
    port: Optional[int] = None,
    identity_file: Optional[str] = None,
    max_retries: int = DEFAULT_RSYNC_RETRIES,
) -> str:
    """Sync a single file and return its remote path."""
    synced_files = sync_files_via_rsync(
        files=[file],
        remote_subdir=remote_subdir,
        remote_base=remote_base,
        alias_or_host=alias_or_host,
        timeout=timeout,
        username=username,
        port=port,
        identity_file=identity_file,
        max_retries=max_retries,
    )
    return synced_files[0]


# Backward-compatible aliases for older call sites.
upload_files_via_sftp = sync_files_via_rsync
upload_tree_via_sftp = sync_tree_via_rsync
upload_file_via_sftp = sync_file_via_rsync
