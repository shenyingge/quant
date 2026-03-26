import json
from pathlib import Path

import pandas as pd

from src.backtest.cli import run_backtest_cli


def test_t0_backtest_cli_writes_output_files(tmp_path: Path):
    minute_path = tmp_path / "minute.csv"
    daily_path = tmp_path / "daily.csv"
    output_dir = tmp_path / "result"

    pd.DataFrame(
        {
            "datetime": [
                "2026-03-26 09:50:00",
                "2026-03-26 10:00:00",
                "2026-03-26 13:30:00",
            ],
            "symbol": ["601138.SH", "601138.SH", "601138.SH"],
            "open": [50.0, 49.6, 50.8],
            "high": [50.1, 50.9, 51.0],
            "low": [49.4, 49.5, 50.6],
            "close": [49.6, 50.8, 50.8],
            "volume": [10000, 15000, 12000],
            "amount": [496000, 762000, 609600],
            "pre_close": [50.5, 50.5, 50.5],
        }
    ).to_csv(minute_path, index=False)

    pd.DataFrame(
        {
            "datetime": pd.date_range("2025-11-01", periods=100, freq="D"),
            "symbol": ["601138.SH"] * 100,
            "open": [50 + i * 0.1 for i in range(100)],
            "high": [50.2 + i * 0.1 for i in range(100)],
            "low": [49.8 + i * 0.1 for i in range(100)],
            "close": [50 + i * 0.1 for i in range(100)],
            "volume": [100000] * 100,
            "amount": [5000000] * 100,
            "pre_close": [49.9 + i * 0.1 for i in range(100)],
        }
    ).to_csv(daily_path, index=False)

    exit_code = run_backtest_cli(
        [
            "--minute-data",
            str(minute_path),
            "--daily-data",
            str(daily_path),
            "--symbol",
            "601138.SH",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert (output_dir / "signals.csv").exists()
    assert (output_dir / "fills.csv").exists()
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["symbol"] == "601138.SH"
