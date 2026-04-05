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
    assert (output_dir / "roundtrips.csv").exists()
    assert (output_dir / "open_legs.csv").exists()
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["symbol"] == "601138.SH"
    assert "config" in summary


def test_t0_backtest_cli_supports_json_config_and_time_filter(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    output_dir = tmp_path / "result"

    pd.DataFrame(
        {
            "datetime": [
                "2026-03-12 09:55:00",
                "2026-03-12 10:00:00",
                "2026-03-12 13:30:00",
            ],
            "symbol": ["601138.SH", "601138.SH", "601138.SH"],
            "open": [54.48, 54.07, 52.4],
            "high": [54.48, 54.13, 52.6],
            "low": [54.33, 53.97, 52.3],
            "close": [54.35, 53.97, 52.5],
            "volume": [1000, 1000, 1000],
            "amount": [54350, 53970, 52500],
        }
    ).to_parquet(data_dir / "601138.SH_minute.parquet", index=False)

    pd.DataFrame(
        {
            "datetime": pd.date_range("2025-11-01", periods=120, freq="D"),
            "symbol": ["601138.SH"] * 120,
            "open": [80 - i * 0.2 for i in range(120)],
            "high": [80.1 - i * 0.2 for i in range(120)],
            "low": [79.9 - i * 0.2 for i in range(120)],
            "close": [80 - i * 0.2 for i in range(120)],
            "volume": [100000] * 120,
            "amount": [5000000] * 120,
            "pre_close": [80.2 - i * 0.2 for i in range(120)],
        }
    ).to_parquet(data_dir / "601138.SH_daily.parquet", index=False)

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "minute_data": str(data_dir),
                "daily_data": str(data_dir),
                "symbol": "601138.SH",
                "start_datetime": "2026-03-12 10:00:00",
                "end_datetime": "2026-03-12 23:59:59",
                "output_dir": str(output_dir),
                "execution_mode": "next_bar_open",
                "base_position": 2600,
                "tactical_position": 900,
                "initial_position": 3500,
                "available_volume": 3500,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    exit_code = run_backtest_cli(["--config", str(config_path)])

    assert exit_code == 0
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["minute_rows"] == 2
    assert summary["config"]["execution_mode"] == "next_bar_open"
