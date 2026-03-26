"""T+0 回测命令行入口。"""

import argparse
import json
from pathlib import Path
from typing import Optional

from .data_loader import BacktestDataLoader
from .simulator import T0BacktestSimulator
from src.config import settings
from src.logger_config import configured_logger as logger
from src.strategy.core.models import PortfolioState
from src.strategy.core.params import T0StrategyParams


def run_backtest_cli(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="python main.py t0-backtest")
    parser.add_argument("--minute-data", required=True, help="分钟线 csv/parquet 文件路径")
    parser.add_argument("--daily-data", required=True, help="日线 csv/parquet 文件路径")
    parser.add_argument("--symbol", default=settings.t0_stock_code, help="股票代码")
    parser.add_argument("--output-dir", default="./output/backtest", help="回测输出目录")
    parser.add_argument(
        "--initial-position",
        type=int,
        default=settings.t0_base_position,
        help="初始总持仓股数",
    )
    parser.add_argument(
        "--available-volume",
        type=int,
        default=settings.t0_base_position,
        help="初始可用股数",
    )
    parser.add_argument("--cost-price", type=float, default=80.0, help="初始成本价")
    parser.add_argument(
        "--cash-available",
        type=float,
        default=settings.t0_max_trade_value,
        help="初始可用现金",
    )
    args = parser.parse_args(argv)

    loader = BacktestDataLoader()
    minute_data = loader.load_minute_data(args.minute_data, symbol=args.symbol)
    daily_data = loader.load_daily_data(args.daily_data, symbol=args.symbol)

    params = T0StrategyParams.from_settings(settings)
    max_position = params.t0_base_position + params.t0_tactical_position
    initial_position = PortfolioState(
        total_position=args.initial_position,
        available_volume=args.available_volume,
        cost_price=args.cost_price,
        base_position=params.t0_base_position,
        tactical_position=params.t0_tactical_position,
        max_position=max_position,
        t0_sell_available=max(
            min(args.available_volume, max(args.initial_position - params.t0_base_position, 0)), 0
        ),
        t0_buy_capacity=max(max_position - args.initial_position, 0),
        cash_available=args.cash_available,
    )

    simulator = T0BacktestSimulator(params)
    result = simulator.run(minute_data, daily_data, initial_position, symbol=args.symbol)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    signals_path = output_dir / "signals.csv"
    fills_path = output_dir / "fills.csv"
    summary_path = output_dir / "summary.json"

    result["signals"].to_csv(signals_path, index=False)
    result["fills"].to_csv(fills_path, index=False)

    summary = {
        "symbol": args.symbol,
        "minute_rows": int(len(minute_data)),
        "daily_rows": int(len(daily_data)),
        "signal_count": int(len(result["signals"])),
        "fill_count": int(len(result["fills"])),
        "final_position": result["final_position"].to_dict(),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"回测完成: signals={signals_path}, fills={fills_path}, summary={summary_path}")
    return 0
