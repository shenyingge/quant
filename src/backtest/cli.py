"""T+0 回测命令行入口。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .data_loader import BacktestDataLoader
from .metrics import build_open_legs, build_roundtrips, summarize_backtest
from .simulator import T0BacktestSimulator
from src.infrastructure.config import settings
from src.infrastructure.logger_config import configured_logger as logger
from src.strategy.core.models import PortfolioState
from src.strategy.core.params import T0StrategyParams


def run_backtest_cli(argv: Optional[list] = None) -> int:
    parser = _build_parser(argv)
    args = parser.parse_args(argv)
    _normalize_datetime_args(args)

    loader = BacktestDataLoader()
    minute_path = loader.resolve_data_path(
        args.minute_data, symbol=args.symbol, dataset_kind="minute"
    )
    daily_path = loader.resolve_data_path(args.daily_data, symbol=args.symbol, dataset_kind="daily")

    minute_data = loader.load_minute_data(
        minute_path,
        symbol=args.symbol,
        timezone=args.timezone,
        start=args.start_datetime,
        end=args.end_datetime,
    )
    daily_data = loader.load_daily_data(
        daily_path,
        symbol=args.symbol,
        timezone=args.timezone,
        start=args.daily_start_datetime,
        end=args.daily_end_datetime,
    )
    minute_data = loader.align_minute_pre_close(minute_data, daily_data)

    params = T0StrategyParams(
        t0_base_position=args.base_position,
        t0_tactical_position=args.tactical_position,
        t0_trade_unit=args.trade_unit,
        t0_max_trade_value=args.max_trade_value,
        t0_commission_rate=args.commission_rate,
        t0_min_commission=args.min_commission,
        t0_transfer_fee_rate=args.transfer_fee_rate,
        t0_stamp_duty_rate=args.stamp_duty_rate,
        t0_min_hold_minutes=args.min_hold_minutes,
        t0_positive_sell_start_time=args.positive_sell_start_time,
        t0_positive_sell_end_time=args.positive_sell_end_time,
        t0_positive_buyback_start_time=args.positive_buyback_start_time,
        t0_positive_buyback_end_time=args.positive_buyback_end_time,
        t0_reverse_buy_start_time=args.reverse_buy_start_time,
        t0_reverse_buy_end_time=args.reverse_buy_end_time,
        t0_reverse_sell_start_time=args.reverse_sell_start_time,
        t0_reverse_sell_end_time=args.reverse_sell_end_time,
        t0_positive_sell_min_rise=args.positive_sell_min_rise,
        t0_positive_sell_min_pullback=args.positive_sell_min_pullback,
        t0_reverse_buy_min_drop=args.reverse_buy_min_drop,
        t0_reverse_buy_min_bounce=args.reverse_buy_min_bounce,
        t0_reverse_sell_min_profit=args.reverse_sell_min_profit,
        t0_reverse_sell_max_vwap_distance=args.reverse_sell_max_vwap_distance,
    )
    initial_position = build_initial_position(args, params)

    simulator = T0BacktestSimulator(params, execution_mode=args.execution_mode)
    result = simulator.run(minute_data, daily_data, initial_position, symbol=args.symbol)

    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result["signals"].to_csv(output_dir / "signals.csv", index=False)
    result["fills"].to_csv(output_dir / "fills.csv", index=False)
    roundtrips = build_roundtrips(result["fills"])
    roundtrips.to_csv(output_dir / "roundtrips.csv", index=False)
    open_legs = build_open_legs(
        result["fills"],
        last_close=float(minute_data["close"].iloc[-1]) if not minute_data.empty else 0.0,
    )
    open_legs.to_csv(output_dir / "open_legs.csv", index=False)

    summary = summarize_backtest(
        minute_data=minute_data,
        fills=result["fills"],
        final_position=result["final_position"],
        symbol=args.symbol,
        execution_mode=args.execution_mode,
        initial_position=initial_position,
    )
    summary["daily_rows"] = int(len(daily_data))
    summary["signal_count"] = int(len(result["signals"]))
    summary["config"] = build_config_payload(args, minute_path=minute_path, daily_path=daily_path)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    logger.info(
        f"回测完成: output={output_dir}, signals={len(result['signals'])}, fills={len(result['fills'])}"
    )
    return 0


def _build_parser(argv: Optional[list]) -> argparse.ArgumentParser:
    config = load_config_from_argv(argv)
    parser = argparse.ArgumentParser(prog="python main.py t0-backtest")
    cfg = lambda key, default=None: config.get(key, default)
    default_params = T0StrategyParams()

    parser.add_argument("--config", help="JSON 配置文件路径")
    parser.add_argument(
        "--minute-data",
        required=cfg("minute_data") is None,
        default=cfg("minute_data"),
        help="分钟线 csv/parquet 文件或目录",
    )
    parser.add_argument(
        "--daily-data",
        required=cfg("daily_data") is None,
        default=cfg("daily_data"),
        help="日线 csv/parquet 文件或目录",
    )
    parser.add_argument("--symbol", default=cfg("symbol", settings.t0_stock_code), help="股票代码")
    parser.add_argument(
        "--output-dir",
        default=cfg("output_dir"),
        help="回测输出目录；默认写到 output/backtest_<timestamp>",
    )
    parser.add_argument("--timezone", default=cfg("timezone", "Asia/Shanghai"), help="数据时区")
    parser.add_argument(
        "--start-date", default=cfg("start_date"), help="分钟数据开始日期，例如 2026-03-01"
    )
    parser.add_argument(
        "--end-date", default=cfg("end_date"), help="分钟数据结束日期，例如 2026-03-24"
    )
    parser.add_argument(
        "--start-datetime",
        default=cfg("start_datetime"),
        help="分钟数据开始时间，例如 2026-03-12 09:58:00",
    )
    parser.add_argument(
        "--end-datetime",
        default=cfg("end_datetime"),
        help="分钟数据结束时间，例如 2026-03-24 15:00:00",
    )
    parser.add_argument("--daily-start-date", default=cfg("daily_start_date"), help="日线开始日期")
    parser.add_argument("--daily-end-date", default=cfg("daily_end_date"), help="日线结束日期")
    parser.add_argument(
        "--daily-start-datetime", default=cfg("daily_start_datetime"), help="日线开始时间"
    )
    parser.add_argument(
        "--daily-end-datetime", default=cfg("daily_end_datetime"), help="日线结束时间"
    )

    parser.add_argument(
        "--base-position",
        type=int,
        default=cfg("base_position", default_params.t0_base_position),
        help="底仓股数",
    )
    parser.add_argument(
        "--tactical-position",
        type=int,
        default=cfg("tactical_position", default_params.t0_tactical_position),
        help="机动仓股数",
    )
    parser.add_argument(
        "--trade-unit",
        type=int,
        default=cfg("trade_unit", settings.t0_trade_unit),
        help="最小交易单位",
    )
    parser.add_argument(
        "--max-trade-value",
        type=float,
        default=cfg("max_trade_value", default_params.t0_max_trade_value),
        help="单次最大可动用金额",
    )
    parser.add_argument(
        "--initial-position",
        type=int,
        default=cfg("initial_position"),
        help="初始总持仓股数，默认 base + tactical",
    )
    parser.add_argument(
        "--available-volume",
        type=int,
        default=cfg("available_volume"),
        help="初始可用股数，默认 initial_position",
    )
    parser.add_argument(
        "--cost-price", type=float, default=cfg("cost_price", 80.0), help="初始成本价"
    )
    parser.add_argument(
        "--cash-available",
        type=float,
        default=cfg("cash_available", default_params.t0_max_trade_value),
        help="初始可用现金",
    )

    parser.add_argument(
        "--execution-mode",
        choices=["same_bar_close", "next_bar_open"],
        default=cfg("execution_mode", "same_bar_close"),
        help="成交模型：当前 bar 收盘成交或下一 bar 开盘成交",
    )
    parser.add_argument(
        "--commission-rate",
        type=float,
        default=cfg("commission_rate", settings.t0_commission_rate),
        help="佣金费率",
    )
    parser.add_argument(
        "--min-commission",
        type=float,
        default=cfg("min_commission", settings.t0_min_commission),
        help="最低佣金",
    )
    parser.add_argument(
        "--transfer-fee-rate",
        type=float,
        default=cfg("transfer_fee_rate", settings.t0_transfer_fee_rate),
        help="过户费费率",
    )
    parser.add_argument(
        "--stamp-duty-rate",
        type=float,
        default=cfg("stamp_duty_rate", settings.t0_stamp_duty_rate),
        help="印花税费率",
    )

    parser.add_argument(
        "--min-hold-minutes",
        type=int,
        default=cfg("min_hold_minutes", settings.t0_min_hold_minutes),
    )
    parser.add_argument(
        "--positive-sell-start-time",
        default=cfg("positive_sell_start_time", settings.t0_positive_sell_start_time),
    )
    parser.add_argument(
        "--positive-sell-end-time",
        default=cfg("positive_sell_end_time", settings.t0_positive_sell_end_time),
    )
    parser.add_argument(
        "--positive-buyback-start-time",
        default=cfg("positive_buyback_start_time", settings.t0_positive_buyback_start_time),
    )
    parser.add_argument(
        "--positive-buyback-end-time",
        default=cfg("positive_buyback_end_time", settings.t0_positive_buyback_end_time),
    )
    parser.add_argument(
        "--reverse-buy-start-time",
        default=cfg("reverse_buy_start_time", settings.t0_reverse_buy_start_time),
    )
    parser.add_argument(
        "--reverse-buy-end-time",
        default=cfg("reverse_buy_end_time", settings.t0_reverse_buy_end_time),
    )
    parser.add_argument(
        "--reverse-sell-start-time",
        default=cfg("reverse_sell_start_time", settings.t0_reverse_sell_start_time),
    )
    parser.add_argument(
        "--reverse-sell-end-time",
        default=cfg("reverse_sell_end_time", settings.t0_reverse_sell_end_time),
    )
    parser.add_argument(
        "--positive-sell-min-rise",
        type=float,
        default=cfg("positive_sell_min_rise", settings.t0_positive_sell_min_rise),
    )
    parser.add_argument(
        "--positive-sell-min-pullback",
        type=float,
        default=cfg("positive_sell_min_pullback", settings.t0_positive_sell_min_pullback),
    )
    parser.add_argument(
        "--reverse-buy-min-drop",
        type=float,
        default=cfg("reverse_buy_min_drop", settings.t0_reverse_buy_min_drop),
    )
    parser.add_argument(
        "--reverse-buy-min-bounce",
        type=float,
        default=cfg("reverse_buy_min_bounce", settings.t0_reverse_buy_min_bounce),
    )
    parser.add_argument(
        "--reverse-sell-min-profit",
        type=float,
        default=cfg("reverse_sell_min_profit", settings.t0_reverse_sell_min_profit),
    )
    parser.add_argument(
        "--reverse-sell-max-vwap-distance",
        type=float,
        default=cfg("reverse_sell_max_vwap_distance", settings.t0_reverse_sell_max_vwap_distance),
    )
    return parser


def load_config_from_argv(argv: Optional[list]) -> dict[str, Any]:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config")
    known, _ = pre_parser.parse_known_args(argv)
    if not known.config:
        return {}
    config_path = Path(known.config)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Backtest config must be a JSON object: {config_path}")
    return payload


def build_initial_position(args: argparse.Namespace, params: T0StrategyParams) -> PortfolioState:
    max_position = params.t0_base_position + params.t0_tactical_position
    total_position = int(
        args.initial_position if args.initial_position is not None else max_position
    )
    available_volume = int(
        args.available_volume if args.available_volume is not None else total_position
    )
    trade_unit = max(int(params.t0_trade_unit), 1)

    def round_down_lot(volume: int) -> int:
        return max(int(volume) // trade_unit * trade_unit, 0)

    return PortfolioState(
        total_position=total_position,
        available_volume=available_volume,
        cost_price=float(args.cost_price),
        base_position=params.t0_base_position,
        tactical_position=params.t0_tactical_position,
        max_position=max_position,
        t0_sell_available=round_down_lot(
            min(available_volume, max(total_position - params.t0_base_position, 0))
        ),
        t0_buy_capacity=round_down_lot(max(max_position - total_position, 0)),
        cash_available=float(args.cash_available),
    )


def build_config_payload(
    args: argparse.Namespace,
    *,
    minute_path: Path,
    daily_path: Path,
) -> dict[str, Any]:
    return {
        "minute_data": str(minute_path),
        "daily_data": str(daily_path),
        "symbol": args.symbol,
        "timezone": args.timezone,
        "start_datetime": args.start_datetime,
        "end_datetime": args.end_datetime,
        "daily_start_datetime": args.daily_start_datetime,
        "daily_end_datetime": args.daily_end_datetime,
        "execution_mode": args.execution_mode,
        "params": {
            "base_position": args.base_position,
            "tactical_position": args.tactical_position,
            "trade_unit": args.trade_unit,
            "max_trade_value": args.max_trade_value,
            "min_hold_minutes": args.min_hold_minutes,
            "positive_sell_min_rise": args.positive_sell_min_rise,
            "positive_sell_min_pullback": args.positive_sell_min_pullback,
            "reverse_buy_min_drop": args.reverse_buy_min_drop,
            "reverse_buy_min_bounce": args.reverse_buy_min_bounce,
            "reverse_sell_min_profit": args.reverse_sell_min_profit,
            "reverse_sell_max_vwap_distance": args.reverse_sell_max_vwap_distance,
        },
        "fees": {
            "commission_rate": args.commission_rate,
            "min_commission": args.min_commission,
            "transfer_fee_rate": args.transfer_fee_rate,
            "stamp_duty_rate": args.stamp_duty_rate,
        },
    }


def resolve_output_dir(raw_output_dir: Optional[str]) -> Path:
    if raw_output_dir:
        return Path(raw_output_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("./output") / f"backtest_{timestamp}"


def _normalize_datetime_args(args: argparse.Namespace) -> None:
    if args.start_date and not args.start_datetime:
        args.start_datetime = f"{args.start_date} 00:00:00"
    if args.end_date and not args.end_datetime:
        args.end_datetime = f"{args.end_date} 23:59:59"
    if args.daily_start_date and not args.daily_start_datetime:
        args.daily_start_datetime = f"{args.daily_start_date} 00:00:00"
    if args.daily_end_date and not args.daily_end_datetime:
        args.daily_end_datetime = f"{args.daily_end_date} 23:59:59"
    if not args.daily_start_datetime:
        args.daily_start_datetime = args.start_datetime
    if not args.daily_end_datetime:
        args.daily_end_datetime = args.end_datetime
