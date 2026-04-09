import threading

from src.infrastructure.connection.manager import ConnectionManager, ConnectionState


def test_connection_manager_retries_after_initial_connect_failure(monkeypatch):
    attempts = {"count": 0}
    reconnect_finished = threading.Event()

    def connect_func() -> bool:
        attempts["count"] += 1
        return attempts["count"] >= 2

    def disconnect_func() -> None:
        return None

    def health_check_func() -> bool:
        return True

    monkeypatch.setattr(
        "src.infrastructure.connection.manager.settings.auto_reconnect_enabled",
        True,
    )
    monkeypatch.setattr(
        "src.infrastructure.connection.manager.settings.reconnect_max_attempts",
        2,
    )
    monkeypatch.setattr(
        "src.infrastructure.connection.manager.settings.reconnect_initial_delay",
        0,
    )
    monkeypatch.setattr(
        "src.infrastructure.connection.manager.settings.reconnect_backoff_factor",
        1.0,
    )
    monkeypatch.setattr(
        "src.infrastructure.connection.manager.settings.reconnect_max_delay",
        0,
    )
    monkeypatch.setattr(
        "src.infrastructure.connection.manager.settings.health_check_interval",
        60,
    )

    manager = ConnectionManager(
        name="QMT",
        connect_func=connect_func,
        disconnect_func=disconnect_func,
        health_check_func=health_check_func,
    )

    original_connect = manager._connect

    def tracked_connect() -> bool:
        result = original_connect()
        if attempts["count"] >= 2:
            reconnect_finished.set()
        return result

    manager._connect = tracked_connect

    assert manager.start() is True
    assert reconnect_finished.wait(timeout=2), "reconnect thread never retried the connection"
    assert attempts["count"] == 2
    assert manager.get_state() == ConnectionState.CONNECTED
    manager.stop()
