from datetime import date as real_date

import src.infrastructure.runtime.watchdog_service as watchdog_module


def test_watchdog_retries_after_unresolved_trading_day(monkeypatch):
    responses = iter([None, True])
    monkeypatch.setattr(
        watchdog_module,
        "resolve_trading_day_status",
        lambda check_date=None: next(responses),
    )

    watchdog = watchdog_module.QuantWatchdogService(dry_run=True)
    target_date = real_date(2026, 4, 7)

    assert watchdog._get_trading_day_status(target_date) is False
    assert watchdog._trading_day_cache == {"date": None, "value": False}

    assert watchdog._get_trading_day_status(target_date) is True
    assert watchdog._trading_day_cache == {"date": target_date.isoformat(), "value": True}
