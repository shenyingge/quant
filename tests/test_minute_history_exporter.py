from argparse import Namespace
from datetime import date as real_date

import main as main_module

import src.minute_history_exporter as minute_history_exporter


class FixedDate:
    @staticmethod
    def today():
        return real_date(2026, 3, 26)


def test_normalize_trade_date_supports_today(monkeypatch):
    monkeypatch.setattr(minute_history_exporter, "date", FixedDate)

    assert minute_history_exporter.normalize_trade_date("today") == "20260326"


def test_resolve_date_range_prefers_trade_date():
    args = Namespace(trade_date="20260326", start_date="20250101", end_date="20251231")

    assert minute_history_exporter.resolve_date_range(args) == ("20260326", "20260326")


def test_build_bundle_name_collapses_single_day():
    assert (
        minute_history_exporter.build_bundle_name("20260326", "20260326")
        == "stock_minute_1m_20260326"
    )
    assert (
        minute_history_exporter.build_bundle_name("20260301", "20260326")
        == "stock_minute_1m_20260301_20260326"
    )


def test_export_minute_daily_skips_on_non_trading_day(monkeypatch):
    monkeypatch.setattr(main_module, "is_trading_day", lambda: False)
    called = {"value": False}

    def fake_export(_):
        called["value"] = True
        return 0

    monkeypatch.setattr(main_module, "export_minute_history", fake_export)

    assert main_module.export_minute_daily(["--skip-upload"]) == 0
    assert called["value"] is False


def test_export_minute_daily_uses_trade_date_defaults(monkeypatch):
    monkeypatch.setattr(main_module, "is_trading_day", lambda: True)
    monkeypatch.setattr(main_module, "date", FixedDate)
    captured = {}

    def fake_export(args):
        captured["args"] = args
        return 0

    monkeypatch.setattr(main_module, "export_minute_history", fake_export)

    assert main_module.export_minute_daily(["--skip-upload"]) == 0
    assert captured["args"] == [
        "--trade-date",
        "20260326",
        "--listed-only",
        "--overwrite",
        "--skip-zip",
        "--skip-upload",
    ]
