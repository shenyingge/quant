"""Comprehensive Phase 5 migration verification."""

import sys
from pathlib import Path


def test_all_old_imports_still_work():
    """All backward-compatible imports work."""
    from src.database import Base, OrderRecord, TradeExecution
    from src.notifications import FeishuNotifier
    from src.redis_listener import RedisSignalListener
    from src.trader import QMTTrader
    from src.trading_engine import TradingEngine

    assert all([Base, OrderRecord, TradeExecution, FeishuNotifier,
                RedisSignalListener, QMTTrader, TradingEngine])


def test_all_new_imports_work():
    """All new imports work."""
    from src.infrastructure.db.models import Base, OrderRecord, TradeExecution
    from src.infrastructure.notifications.feishu import FeishuNotifier
    from src.infrastructure.redis.signal_listener import RedisSignalListener
    from src.trading.execution.qmt_trader import QMTTrader
    from src.trading.runtime.engine import TradingEngine

    assert all([Base, OrderRecord, TradeExecution, FeishuNotifier,
                RedisSignalListener, QMTTrader, TradingEngine])


def test_old_and_new_paths_reference_same_classes():
    """Verify single class identity across import paths."""
    # databases
    from src.database import Base as OldBase
    from src.infrastructure.db.models import Base as NewBase
    assert OldBase is NewBase

    # notifications
    from src.notifications import FeishuNotifier as OldNotifier
    from src.infrastructure.notifications.feishu import FeishuNotifier as NewNotifier
    assert OldNotifier is NewNotifier

    # redis
    from src.redis_listener import RedisSignalListener as OldListener
    from src.infrastructure.redis.signal_listener import RedisSignalListener as NewListener
    assert OldListener is NewListener

    # trader
    from src.trader import QMTTrader as OldTrader
    from src.trading.execution.qmt_trader import QMTTrader as NewTrader
    assert OldTrader is NewTrader

    # trading engine
    from src.trading_engine import TradingEngine as OldEngine
    from src.trading.runtime.engine import TradingEngine as NewEngine
    assert OldEngine is NewEngine


def test_infrastructure_package_structure():
    """Verify infrastructure package structure is correct."""
    from pathlib import Path
    
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
    """Verify trading package structure is correct."""
    from pathlib import Path
    
    src_path = Path("src/trading")
    assert (src_path / "__init__.py").exists(), "trading/__init__.py missing"
    assert (src_path / "execution").is_dir(), "trading/execution directory missing"
    assert (src_path / "execution" / "__init__.py").exists(), "trading/execution/__init__.py missing"
    assert (src_path / "execution" / "qmt_trader.py").exists(), "trading/execution/qmt_trader.py missing"
    assert (src_path / "runtime").is_dir(), "trading/runtime directory missing"
    assert (src_path / "runtime" / "__init__.py").exists(), "trading/runtime/__init__.py missing"
    assert (src_path / "runtime" / "engine.py").exists(), "trading/runtime/engine.py missing"


def test_backward_compat_wrappers_exist():
    """Verify all backward compatibility wrappers exist."""
    from pathlib import Path
    
    assert (Path("src/database.py")).exists(), "src/database.py wrapper missing"
    assert (Path("src/notifications.py")).exists(), "src/notifications.py wrapper missing"
    assert (Path("src/redis_listener.py")).exists(), "src/redis_listener.py wrapper missing"
    assert (Path("src/trader.py")).exists(), "src/trader.py wrapper missing"
    assert (Path("src/trading_engine.py")).exists(), "src/trading_engine.py wrapper missing"
