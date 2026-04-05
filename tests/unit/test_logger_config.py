from src.logger_config import configure_process_logger, resolve_log_file_path


def test_resolve_log_file_path_uses_role_based_default(tmp_path, monkeypatch):
    monkeypatch.delenv("LOG_FILE", raising=False)
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setenv("LOG_TO_FILE", "true")

    path = resolve_log_file_path("t0-daemon")

    assert path == tmp_path / "t0_daemon.log"


def test_resolve_log_file_path_honors_explicit_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setenv("LOG_TO_FILE", "true")

    path = resolve_log_file_path("t0-daemon", explicit_log_file=str(tmp_path / "custom.log"))

    assert path == tmp_path / "custom.log"


def test_configure_process_logger_uses_role_specific_file_even_with_shared_log_file(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setenv("LOG_TO_FILE", "true")
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "shared.log"))

    configure_process_logger("t0-daemon")

    assert (tmp_path / "t0_daemon.log").exists()
