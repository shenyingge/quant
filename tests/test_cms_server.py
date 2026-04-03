import json
import socket
import subprocess
import time
from pathlib import Path

import src.cms_server as cms_server


def make_check(name: str, status: str, critical: bool = False):
    return cms_server.CmsCheckResult(
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

    monkeypatch.setattr(cms_server.settings, "t0_output_dir", str(tmp_path))

    checker = cms_server.ProjectCmsChecker()
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
    checker = cms_server.ProjectCmsChecker()

    status = checker._derive_overall_status(
        [
            make_check("database", "fail", True),
            make_check("redis", "pass", True),
            make_check("strategy_engine_process", "warn"),
        ]
    )

    assert status == "down"


def test_health_status_is_degraded_when_only_noncritical_checks_warn():
    checker = cms_server.ProjectCmsChecker()

    status = checker._derive_overall_status(
        [
            make_check("database", "pass", True),
            make_check("redis", "pass", True),
            make_check("strategy_engine_process", "warn"),
        ]
    )

    assert status == "degraded"


def test_process_check_skips_when_component_not_expected():
    checker = cms_server.ProjectCmsChecker()

    result = checker._build_process_check(
        name="strategy_engine_process",
        component="strategy_engine",
        matches=[],
        expected=False,
    )

    assert result.status == "skip"


def test_process_check_warns_when_component_expected_but_missing():
    checker = cms_server.ProjectCmsChecker()

    result = checker._build_process_check(
        name="trading_engine_process",
        component="trading_engine",
        matches=[],
        expected=True,
    )

    assert result.status == "warn"


def test_strategy_engine_process_check_collapses_windows_launcher_chain():
    checker = cms_server.ProjectCmsChecker()
    trading_day = make_check("trading_day", "pass")
    processes = [
        {
            "pid": 1336,
            "parent_pid": 4868,
            "command_line": r"C:\Users\sai\quant\.venv\Scripts\python.exe main.py t0-daemon",
        },
        {
            "pid": 12324,
            "parent_pid": 1336,
            "command_line": (
                r"C:\Users\sai\AppData\Roaming\uv\python\cpython-3.9.23-windows-x86_64-none"
                r"\python.exe main.py t0-daemon"
            ),
        },
    ]

    result = checker._check_strategy_engine_process(processes, trading_day)

    assert result.status == "pass"
    assert result.details["count"] == 1
    assert result.details["pids"] == [1336]


def test_background_health_server_serves_snapshot(monkeypatch):
    snapshot = cms_server.CmsSnapshot(
        service="quant",
        scope="project",
        version="0.1.0",
        status="ok",
        checked_at="2026-03-29T00:00:00+08:00",
        summary={"pass": 1, "warn": 0, "fail": 0, "skip": 0, "duration_ms": 1},
        checks=[make_check("database", "pass", True).to_dict()],
    )

    monkeypatch.setattr(
        cms_server.ProjectCmsChecker,
        "build_snapshot",
        lambda self: snapshot,
    )

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    host, port = sock.getsockname()
    sock.close()

    try:
        assert cms_server.start_cms_server(host, port, scope="project") is True
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
        cms_server.stop_cms_server()


def test_background_health_server_is_idempotent(monkeypatch):
    snapshot = cms_server.CmsSnapshot(
        service="quant",
        scope="project",
        version="0.1.0",
        status="ok",
        checked_at="2026-03-29T00:00:00+08:00",
        summary={"pass": 1, "warn": 0, "fail": 0, "skip": 0, "duration_ms": 1},
        checks=[],
    )

    monkeypatch.setattr(
        cms_server.ProjectCmsChecker,
        "build_snapshot",
        lambda self: snapshot,
    )

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    host, port = sock.getsockname()
    sock.close()

    try:
        assert cms_server.start_cms_server(host, port, scope="project") is True
        assert cms_server.start_cms_server(host, port, scope="project") is True
    finally:
        cms_server.stop_cms_server()


def test_resolve_cms_server_host_returns_explicit_host():
    assert cms_server.resolve_cms_server_host("127.0.0.1") == "127.0.0.1"


def test_resolve_cms_server_host_uses_tailscale_cli(monkeypatch):
    def fake_run(command, capture_output, check, text, timeout):
        return subprocess.CompletedProcess(command, 0, stdout="100.92.140.63\n", stderr="")

    monkeypatch.setattr(cms_server.subprocess, "run", fake_run)

    assert cms_server.resolve_cms_server_host("tailscale") == "100.92.140.63"


def test_resolve_cms_server_host_uses_ipconfig_fallback(monkeypatch):
    outputs = [
        FileNotFoundError(),
        FileNotFoundError(),
        subprocess.CompletedProcess(
            ["ipconfig"],
            0,
            stdout=(
                "Windows IP Configuration\n\n"
                "Unknown adapter Tailscale:\n\n"
                "   IPv4 Address. . . . . . . . . . . : 100.92.140.63\n"
            ),
            stderr="",
        ),
    ]

    def fake_run(command, capture_output, check, text, timeout, errors=None):
        result = outputs.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(cms_server, "os", type("FakeOS", (), {"name": "nt"})())
    monkeypatch.setattr(cms_server.subprocess, "run", fake_run)

    assert cms_server.resolve_cms_server_host("tailscale") == "100.92.140.63"


def test_websocket_client_send_message_supports_extended_frame_length():
    class FakeSocket:
        def __init__(self):
            self.payload = b""

        def sendall(self, data):
            self.payload += data

    fake_socket = FakeSocket()
    client = cms_server.WebSocketClient(fake_socket, manager=None)
    message = "x" * 200

    client.send_message(message)

    assert fake_socket.payload[0] == 0x81
    assert fake_socket.payload[1] == 126
    assert int.from_bytes(fake_socket.payload[2:4], byteorder="big") == 200
    assert fake_socket.payload[4:] == message.encode()


def test_websocket_manager_syncs_quote_subscription_and_pushes_cached_quote(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.sets = {}
            self.values = {
                f"{cms_server.settings.redis_quote_enriched_latest_prefix}000001.SZ": json.dumps(
                    {"stock_code": "000001.SZ", "last_price": 12.34}
                )
            }
            self.published = []

        def sadd(self, key, value):
            self.sets.setdefault(key, set()).add(value)

        def srem(self, key, value):
            self.sets.setdefault(key, set()).discard(value)

        def publish(self, channel, payload):
            self.published.append((channel, json.loads(payload)))

        def get(self, key):
            return self.values.get(key)

        def pubsub(self):
            class _PubSub:
                def subscribe(self, *_args, **_kwargs):
                    return None

                def get_message(self, *_args, **_kwargs):
                    return None

            return _PubSub()

    class FakeClient:
        def __init__(self):
            self.messages = []

        def send_message(self, message):
            self.messages.append(message)

    fake_redis = FakeRedis()
    monkeypatch.setattr(cms_server.redis, "Redis", lambda **_kwargs: fake_redis)

    manager = cms_server.WebSocketManager()
    client = FakeClient()

    latest_payload = manager.subscribe("000001.sz", client)

    assert "000001.SZ" in manager.clients
    assert fake_redis.sets[cms_server.settings.redis_quote_subscriptions_key] == {"000001.SZ"}
    assert fake_redis.published == [
        (
            cms_server.settings.redis_quote_control_channel,
            {"action": "subscribe", "stock_code": "000001.SZ"},
        )
    ]
    assert json.loads(latest_payload)["stock_code"] == "000001.SZ"

    manager.unsubscribe("000001.SZ", client)

    assert "000001.SZ" not in manager.clients
    assert fake_redis.sets[cms_server.settings.redis_quote_subscriptions_key] == set()
    assert fake_redis.published[-1] == (
        cms_server.settings.redis_quote_control_channel,
        {"action": "unsubscribe", "stock_code": "000001.SZ"},
    )


def test_websocket_manager_enriches_quote_with_position_pnl(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.sets = {}
            self.values = {}
            self.published = []

        def sadd(self, key, value):
            self.sets.setdefault(key, set()).add(value)

        def srem(self, key, value):
            self.sets.setdefault(key, set()).discard(value)

        def publish(self, channel, payload):
            self.published.append((channel, json.loads(payload)))

        def get(self, key):
            return self.values.get(key)

        def set(self, key, value):
            self.values[key] = value

        def setex(self, key, _ttl, value):
            self.values[key] = value

        def pubsub(self):
            class _PubSub:
                def subscribe(self, *_args, **_kwargs):
                    return None

                def get_message(self, *_args, **_kwargs):
                    return None

            return _PubSub()

    class FakeAccountDataService:
        def get_positions_snapshot(self):
            return {
                "source": "meta_db",
                "available": True,
                "is_live": False,
                "fallback_used": False,
                "as_of": "2026-04-02T13:30:00+08:00",
                "positions": [
                    {
                        "stock_code": "000001.SZ",
                        "volume": 1000,
                        "available_volume": 900,
                        "avg_price": 10.0,
                        "market_value": 10000.0,
                        "account_id": "demo",
                        "source": "meta_db",
                        "position_method": "broker_snapshot",
                        "snapshot_source": "startup_connect",
                        "snapshot_time": "2026-04-02T13:29:59+08:00",
                    }
                ],
            }

    fake_redis = FakeRedis()
    monkeypatch.setattr(cms_server.redis, "Redis", lambda **_kwargs: fake_redis)
    monkeypatch.setattr(cms_server.settings, "cms_quote_position_cache_seconds", 60)
    monkeypatch.setattr(cms_server.settings, "redis_quote_enriched_latest_ttl_seconds", 0)

    manager = cms_server.WebSocketManager(account_data_service=FakeAccountDataService())
    enriched = manager._enrich_quote_payload(
        {
            "stock_code": "000001.SZ",
            "source": "qmt",
            "period": "tick",
            "last_price": 12.34,
            "volume": 500,
            "quote_time": "2026-04-02T13:30:01+08:00",
            "published_at": "2026-04-02T13:30:01+08:00",
            "quote": {"lastPrice": 12.34, "volume": 500},
        }
    )

    assert enriched["stock_code"] == "000001.SZ"
    assert enriched["position"]["volume"] == 1000
    assert enriched["position"]["avg_price"] == 10.0
    assert enriched["pnl"]["cost_basis"] == 10000.0
    assert enriched["pnl"]["market_value"] == 12340.0
    assert enriched["pnl"]["unrealized_pnl"] == 2340.0
    assert enriched["pnl"]["unrealized_pnl_pct"] == 23.4
    assert enriched["timestamps"]["position_snapshot_time"] == "2026-04-02T13:29:59+08:00"
    assert enriched["timestamps"]["positions_as_of"] == "2026-04-02T13:30:00+08:00"


def test_websocket_manager_stop_keeps_redis_quote_subscriptions(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.sets = {}
            self.values = {}
            self.published = []

        def sadd(self, key, value):
            self.sets.setdefault(key, set()).add(value)

        def srem(self, key, value):
            self.sets.setdefault(key, set()).discard(value)

        def publish(self, channel, payload):
            self.published.append((channel, json.loads(payload)))

        def get(self, key):
            return self.values.get(key)

        def pubsub(self):
            class _PubSub:
                def subscribe(self, *_args, **_kwargs):
                    return None

                def get_message(self, *_args, **_kwargs):
                    return None

            return _PubSub()

    class FakeClient:
        def send_message(self, _message):
            return None

    fake_redis = FakeRedis()
    monkeypatch.setattr(cms_server.redis, "Redis", lambda **_kwargs: fake_redis)

    manager = cms_server.WebSocketManager()
    client = FakeClient()
    manager.subscribe("000001.SZ", client)

    manager.stop()

    assert fake_redis.sets[cms_server.settings.redis_quote_subscriptions_key] == {"000001.SZ"}
    assert fake_redis.published == [
        (
            cms_server.settings.redis_quote_control_channel,
            {"action": "subscribe", "stock_code": "000001.SZ"},
        )
    ]
