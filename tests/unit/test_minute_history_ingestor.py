from datetime import datetime

import pandas as pd

from src.market_data.ingestion.minute_history_ingestor import MinuteHistoryIngestor


def test_build_rows_from_dataframe_generates_expected_fields():
    ingestor = MinuteHistoryIngestor()
    index = pd.to_datetime(["2026-03-26 09:30:00", "2026-03-26 09:31:00"])
    frame = pd.DataFrame(
        {
            "open": [10.1, 10.2],
            "high": [10.3, 10.4],
            "low": [10.0, 10.1],
            "close": [10.2, 10.3],
            "volume": [1000, 1200],
            "amount": [10100, 12360],
        },
        index=index,
    )

    rows = ingestor._build_rows_from_dataframe(symbol="000001.SZ", frame=frame)

    assert len(rows) == 2
    assert rows[0]["symbol"] == "000001.SZ"
    assert rows[0]["trade_date"] == datetime(2026, 3, 26).date()
    assert rows[0]["bar_time"] == datetime(2026, 3, 26, 9, 30)
    assert rows[0]["source"] == "qmt_1m"


def test_ingest_range_summarizes_success_and_failure():
    class StubIngestor(MinuteHistoryIngestor):
        def _fetch_stock_records_sync(self, listed_only, codes):
            return [
                type("S", (), {"ts_code": "000001.SZ", "symbol": "000001"})(),
                type("S", (), {"ts_code": "000002.SZ", "symbol": "000002"})(),
            ]

        def _download_minute_dataframe(self, stock_code, start_date, end_date):
            if stock_code == "000001.SZ":
                index = pd.to_datetime(["2026-03-26 09:30:00"])
                return pd.DataFrame(
                    {
                        "open": [10.1],
                        "high": [10.2],
                        "low": [10.0],
                        "close": [10.15],
                        "volume": [100],
                        "amount": [1015],
                    },
                    index=index,
                )
            return pd.DataFrame()

        def _upsert_rows(self, rows):
            return len(rows)

    ingestor = StubIngestor()
    summary = ingestor.ingest_range(start_date="20260326", end_date="20260326", listed_only=True)

    assert summary["total_stocks"] == 2
    assert summary["success_stocks"] == 1
    assert summary["empty_stocks"] == 1
    assert summary["failed_stocks"] == 0
    assert summary["inserted_rows"] == 1
