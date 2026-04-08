import src.cli.registry as registry
from src.infrastructure.config import settings
from src.infrastructure.notifications import FeishuNotifier
import src.infrastructure.runtime.cms_server as cms_server
import src.infrastructure.runtime.watchdog_service as watchdog_module
from src.trading.account.account_data_service import AccountDataService


def test_registry_commands_do_not_expose_strategy_entries():
    forbidden_commands = {
        "t0-daemon",
        "t0-strategy",
        "t0-sync-position",
        "t0-reconcile",
        "t0-backtest",
        "t0-diagnose",
    }

    assert forbidden_commands.isdisjoint(registry.COMMANDS)


def test_cms_snapshot_excludes_strategy_checks(monkeypatch):
    checker = cms_server.ProjectCmsChecker()

    monkeypatch.setattr(checker, "_check_trading_day", lambda: cms_server.CmsCheckResult("trading_day", "calendar", "pass", "ok"))
    monkeypatch.setattr(checker, "_check_database", lambda: cms_server.CmsCheckResult("database", "database", "pass", "ok", critical=True))
    monkeypatch.setattr(checker, "_check_redis", lambda: cms_server.CmsCheckResult("redis", "redis", "pass", "ok", critical=True))
    monkeypatch.setattr(checker, "_list_processes", lambda: [])
    monkeypatch.setattr(checker, "_check_watchdog_process", lambda processes: cms_server.CmsCheckResult("watchdog_process", "watchdog", "pass", "ok"))
    monkeypatch.setattr(checker, "_check_qmt_client_process", lambda processes, trading_day: cms_server.CmsCheckResult("qmt_client_process", "qmt", "pass", "ok"))
    monkeypatch.setattr(checker, "_check_trading_engine_process", lambda processes, trading_day: cms_server.CmsCheckResult("trading_engine_process", "trading_engine", "pass", "ok"))

    snapshot = checker.build_snapshot().to_dict()
    names = {item["name"] for item in snapshot["checks"]}

    assert "strategy_engine_process" not in names
    assert "signal_card" not in names


def test_watchdog_targets_do_not_include_strategy_runtime(monkeypatch):
    monkeypatch.setattr(watchdog_module.settings, "watchdog_enable_trading_service", True)

    watchdog = watchdog_module.QuantWatchdogService(dry_run=True)
    target_names = {target.name for target in watchdog.targets}

    assert "strategy_engine" not in target_names
    assert "t0_daemon" not in target_names
    assert "t0_reconcile" not in target_names


def test_settings_and_services_do_not_expose_strategy_specific_contracts():
    assert not hasattr(settings, "t0_strategy_enabled")
    assert not hasattr(settings, "qmt_session_id_t0_daemon")
    assert not hasattr(settings, "watchdog_enable_t0_daemon")
    assert not hasattr(FeishuNotifier, "notify_t0_signal")
    assert not hasattr(FeishuNotifier, "notify_t0_position_sync")
    assert not hasattr(AccountDataService, "get_latest_signal_card_snapshot")
    assert not hasattr(AccountDataService, "get_strategy_pnl_summary")
    assert not hasattr(AccountDataService, "get_strategy_pnl_breakdown")
