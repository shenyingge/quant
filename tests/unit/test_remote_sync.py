from pathlib import Path

import src.market_data.ingestion.minute_history_exporter as minute_history_exporter
import src.infrastructure.sync.remote_sync as remote_sync
from src.data_manager.daily_exporter import DailyExporter
from src.infrastructure.sync.remote_sync import join_remote_path, normalize_identity_file_path


class _CompletedProcess:
    def __init__(self, command):
        self.args = command
        self.returncode = 0
        self.stdout = ""
        self.stderr = ""


def test_normalize_identity_file_path_supports_msys_style():
    assert (
        normalize_identity_file_path("/c/Users/shen/.ssh/trading_backup_key")
        == r"C:\Users\shen\.ssh\trading_backup_key"
    )


def test_normalize_identity_file_path_supports_backslash_style():
    assert (
        normalize_identity_file_path(r"\c\Users\shen\.ssh\trading_backup_key")
        == r"C:\Users\shen\.ssh\trading_backup_key"
    )


def test_join_remote_path_preserves_home_prefix():
    assert join_remote_path("~/data/trade", "20260326") == "~/data/trade/20260326"
    assert (
        join_remote_path("/srv/data", "minute_history", "20260326")
        == "/srv/data/minute_history/20260326"
    )


def test_daily_exporter_upload_uses_rsync_helper(monkeypatch, tmp_path):
    exporter = DailyExporter(export_dir=str(tmp_path))
    file_path = tmp_path / "positions_20260326.csv"
    file_path.write_text("test", encoding="utf-8")
    captured = {}

    def fake_upload(files, remote_subdir, remote_base, alias_or_host, timeout):
        captured["files"] = files
        captured["remote_subdir"] = remote_subdir
        captured["remote_base"] = remote_base
        captured["alias_or_host"] = alias_or_host
        captured["timeout"] = timeout
        return [f"/remote/{Path(files[0]).name}"]

    monkeypatch.setattr("src.data_manager.daily_exporter.sync_files_via_rsync", fake_upload)

    assert exporter._upload_via_rsync([file_path], "20260326") is True
    assert captured["files"] == [file_path]
    assert captured["remote_subdir"] == "20260326"
    assert captured["timeout"] == 20


def test_build_remote_upload_subdir_for_daily_directory_upload():
    assert (
        minute_history_exporter.build_remote_upload_subdir(
            "minute_history", "20260326", "20260326", "stock_minute_1m_20260326", True
        )
        == "minute_history/20260326"
    )
    assert (
        minute_history_exporter.build_remote_upload_subdir(
            "minute_history", "20260301", "20260326", "stock_minute_1m_20260301_20260326", True
        )
        == "minute_history/stock_minute_1m_20260301_20260326"
    )
    assert (
        minute_history_exporter.build_remote_upload_subdir(
            "minute_history", "20260326", "20260326", "stock_minute_1m_20260326", False
        )
        == "minute_history"
    )


def test_sync_file_via_rsync_runs_ssh_mkdir_then_rsync(monkeypatch, tmp_path):
    local_file = tmp_path / "sample.zip"
    local_file.write_bytes(b"abcdefghij")
    commands = []

    def fake_run(command, check, capture_output, text, timeout=None):
        commands.append({"command": command, "timeout": timeout})
        return _CompletedProcess(command)

    monkeypatch.setattr(remote_sync.subprocess, "run", fake_run)

    uploaded_path = remote_sync.sync_file_via_rsync(
        file=local_file,
        remote_subdir="minute_history",
        remote_base="~/data/trade",
        alias_or_host="example.com",
        username="shen",
        port=2222,
        identity_file="/c/Users/shen/.ssh/id_ed25519",
        timeout=20,
    )

    assert uploaded_path == "~/data/trade/minute_history/sample.zip"
    assert len(commands) == 2
    assert commands[0]["command"][:4] == ["ssh", "-o", "BatchMode=yes", "-o"]
    assert commands[0]["command"][-2] == "example.com"
    assert "mkdir -p" in commands[0]["command"][-1]

    rsync_command = commands[1]["command"]
    assert rsync_command[0] == "rsync"
    assert "--timeout=20" in rsync_command
    assert "--contimeout=20" not in rsync_command
    assert "-e" in rsync_command
    assert rsync_command[-1] == "example.com:~/data/trade/minute_history/"
