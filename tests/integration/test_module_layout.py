"""Module layout checks for the post-wrapper package structure."""

from pathlib import Path


def test_infrastructure_package_structure():
    src_path = Path("src/infrastructure")
    assert (src_path / "__init__.py").exists(), "infrastructure/__init__.py missing"
    assert (src_path / "db").is_dir(), "infrastructure/db directory missing"
    assert (src_path / "db" / "__init__.py").exists(), "infrastructure/db/__init__.py missing"
    assert (src_path / "db" / "models.py").exists(), "infrastructure/db/models.py missing"
    assert (src_path / "db" / "session.py").exists(), "infrastructure/db/session.py missing"
    assert (src_path / "notifications").is_dir(), "infrastructure/notifications directory missing"
    assert (src_path / "notifications" / "__init__.py").exists(), "infrastructure/notifications/__init__.py missing"
    assert (src_path / "notifications" / "feishu.py").exists(), "infrastructure/notifications/feishu.py missing"
    assert (src_path / "redis").is_dir(), "infrastructure/redis directory missing"
    assert (src_path / "redis" / "__init__.py").exists(), "infrastructure/redis/__init__.py missing"
    assert (src_path / "redis" / "signal_listener.py").exists(), "infrastructure/redis/signal_listener.py missing"


def test_trading_package_structure():
    src_path = Path("src/trading")
    assert (src_path / "__init__.py").exists(), "trading/__init__.py missing"
    assert (src_path / "execution").is_dir(), "trading/execution directory missing"
    assert (src_path / "execution" / "__init__.py").exists(), "trading/execution/__init__.py missing"
    assert (src_path / "execution" / "qmt_trader.py").exists(), "trading/execution/qmt_trader.py missing"
    assert (src_path / "runtime").is_dir(), "trading/runtime directory missing"
    assert (src_path / "runtime" / "__init__.py").exists(), "trading/runtime/__init__.py missing"
    assert (src_path / "runtime" / "engine.py").exists(), "trading/runtime/engine.py missing"


def test_root_wrapper_modules_removed():
    for path in [
        "src/database.py",
        "src/notifications.py",
        "src/redis_listener.py",
        "src/trader.py",
        "src/trading_engine.py",
    ]:
        assert not Path(path).exists(), f"{path} should be removed"
