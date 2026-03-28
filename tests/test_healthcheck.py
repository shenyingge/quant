import json
import socket
import time
from pathlib import Path

import src.healthcheck as healthcheck


def make_check(name: str, status: str, critical: bool = False):
    return healthcheck.HealthCheckResult(
        name=name,
        component=name,
        status=status,
        message=f"{name}:{status}",
        critical=critical,
    )


def test_health_snapshot_uses_standard_structure(monkeypatch, tmp_path):
    signal_card_path = Path(tmp_path) / "live_signal_card.json"
    signal_card_path.write_text(
        '{"as_of_time":"2026-03-28 10:00:00","regime":"range","signal":{"action":"observe"}}',
        encoding="utf-8",
    )

    monkeypatch.setattr(healthcheck.settings, "t0_output_dir", str(tmp_path))

    checker = healthcheck.ProjectHealthChecker()
    monkeypatch.setattr(checker, "_check_trading_day", lambda: make_check("trading_day", "pass"))
    monkeypatch.setattr(checker, "_check_database", lambda: make_check("database", "pass", True))
    monkeypatch.setattr(checker, "_check_redis", lambda: make_check("redis", "pass", True))
    monkeypatch.setattr(checker, "_list_processes", lambda: [])
    monkeypatch.setattr(
        checker,
        "_check_qmt_client_process",
        lambda processes, trading_day: make_check("qmt_client_process", "pass"),
    )
    monkeypatch.setattr(
        checker,
        "_check_trading_engine_process",
        lambda processes, trading_day: make_check("trading_engine_process", "pass"),
    )
    monkeypatch.setattr(
        checker,
        "_check_strategy_engine_process",
        lambda processes, trading_day: make_check("strategy_engine_process", "pass"),
    )

    snapshot = checker.build_snapshot().to_dict()

    assert snapshot["service"] == "quant"
    assert snapshot["scope"] == "project"
    assert snapshot["status"] == "ok"
    assert "checked_at" in snapshot
    assert "summary" in snapshot
    assert snapshot["summary"]["pass"] >= 6
    assert "duration_ms" in snapshot["summary"]
    assert isinstance(snapshot["checks"], list)
    assert snapshot["checks"][0]["status"] in {"pass", "warn", "fail", "skip"}


def test_health_status_is_down_when_critical_check_fails():
    checker = healthcheck.ProjectHealthChecker()

    status = checker._derive_overall_status(
        [
            make_check("database", "fail", True),
            make_check("redis", "pass", True),
            make_check("strategy_engine_process", "warn"),
        ]
    )

    assert status == "down"


def test_health_status_is_degraded_when_only_noncritical_checks_warn():
    checker = healthcheck.ProjectHealthChecker()

    status = checker._derive_overall_status(
        [
            make_check("database", "pass", True),
            make_check("redis", "pass", True),
            make_check("strategy_engine_process", "warn"),
        ]
    )

    assert status == "degraded"


def test_process_check_skips_when_component_not_expected():
    checker = healthcheck.ProjectHealthChecker()

    result = checker._build_process_check(
        name="strategy_engine_process",
        component="strategy_engine",
        matches=[],
        expected=False,
    )

    assert result.status == "skip"


def test_process_check_warns_when_component_expected_but_missing():
    checker = healthcheck.ProjectHealthChecker()

    result = checker._build_process_check(
        name="trading_engine_process",
        component="trading_engine",
        matches=[],
        expected=True,
    )

    assert result.status == "warn"


def test_background_health_server_serves_snapshot(monkeypatch):
    snapshot = healthcheck.HealthSnapshot(
        service="quant",
        scope="project",
        version="0.1.0",
        status="ok",
        checked_at="2026-03-29T00:00:00+08:00",
        summary={"pass": 1, "warn": 0, "fail": 0, "skip": 0, "duration_ms": 1},
        checks=[make_check("database", "pass", True).to_dict()],
    )

    monkeypatch.setattr(
        healthcheck.ProjectHealthChecker,
        "build_snapshot",
        lambda self: snapshot,
    )

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    host, port = sock.getsockname()
    sock.close()

    try:
        assert healthcheck.start_healthcheck_server(host, port, scope="project") is True
        time.sleep(0.2)
        client = socket.create_connection((host, port), timeout=2)
        client.sendall(
            b"GET /health HTTP/1.1\r\n"
            + f"Host: {host}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
        )

        chunks = []
        while True:
            data = client.recv(4096)
            if not data:
                break
            chunks.append(data)
        client.close()

        raw_response = b"".join(chunks)
        header_bytes, body_bytes = raw_response.split(b"\r\n\r\n", 1)
        status_line = header_bytes.splitlines()[0].decode("ascii")
        payload = json.loads(body_bytes.decode("utf-8"))

        assert "200" in status_line
        assert payload["service"] == "quant"
        assert payload["status"] == "ok"
    finally:
        healthcheck.stop_healthcheck_server()


def test_background_health_server_is_idempotent(monkeypatch):
    snapshot = healthcheck.HealthSnapshot(
        service="quant",
        scope="project",
        version="0.1.0",
        status="ok",
        checked_at="2026-03-29T00:00:00+08:00",
        summary={"pass": 1, "warn": 0, "fail": 0, "skip": 0, "duration_ms": 1},
        checks=[],
    )

    monkeypatch.setattr(
        healthcheck.ProjectHealthChecker,
        "build_snapshot",
        lambda self: snapshot,
    )

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    host, port = sock.getsockname()
    sock.close()

    try:
        assert healthcheck.start_healthcheck_server(host, port, scope="project") is True
        assert healthcheck.start_healthcheck_server(host, port, scope="project") is True
    finally:
        healthcheck.stop_healthcheck_server()
