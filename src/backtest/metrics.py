"""T+0 回测结果汇总与绩效指标。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.strategy.core.models import PortfolioState


def summarize_backtest(
    *,
    minute_data: pd.DataFrame,
    fills: pd.DataFrame,
    final_position: PortfolioState,
    symbol: str,
    execution_mode: str,
    initial_position: PortfolioState,
) -> dict[str, Any]:
    last_close = float(minute_data["close"].iloc[-1]) if not minute_data.empty else 0.0
    initial_equity = float(
        initial_position.cash_available + initial_position.total_position * initial_position.cost_price
    )
    final_equity = float(final_position.cash_available + final_position.total_position * last_close)
    roundtrips_df = build_roundtrips(fills)
    open_legs = build_open_legs(fills, last_close=last_close)

    total_fees = float(fills["total_fee"].sum()) if not fills.empty and "total_fee" in fills.columns else 0.0
    gross_realized_t_pnl = (
        float(roundtrips_df["gross_pnl"].sum()) if not roundtrips_df.empty else 0.0
    )
    net_realized_t_pnl = float(roundtrips_df["net_pnl"].sum()) if not roundtrips_df.empty else 0.0
    open_legs_mtm_pnl = float(open_legs["mtm_pnl"].sum()) if not open_legs.empty else 0.0

    return {
        "symbol": symbol,
        "minute_rows": int(len(minute_data)),
        "signal_count": None,
        "fill_count": int(len(fills)),
        "fill_actions": summarize_actions(fills),
        "roundtrip_count": int(len(roundtrips_df)),
        "execution_mode": execution_mode,
        "initial_position": initial_position.to_dict(),
        "final_position": final_position.to_dict(),
        "initial_equity": round(initial_equity, 6),
        "final_equity": round(final_equity, 6),
        "equity_pnl": round(final_equity - initial_equity, 6),
        "last_close": round(last_close, 6),
        "gross_realized_t_pnl": round(gross_realized_t_pnl, 6),
        "net_realized_t_pnl": round(net_realized_t_pnl, 6),
        "open_legs_mtm_pnl": round(open_legs_mtm_pnl, 6),
        "total_fees": round(total_fees, 6),
        "open_legs": open_legs.to_dict("records") if not open_legs.empty else [],
    }


def summarize_actions(fills_df: pd.DataFrame) -> dict[str, int]:
    if fills_df.empty:
        return {}
    counts = fills_df.groupby("action").size().to_dict()
    return {str(key): int(value) for key, value in counts.items()}


def build_roundtrips(fills: pd.DataFrame) -> pd.DataFrame:
    if fills.empty:
        return pd.DataFrame(
            columns=[
                "branch",
                "entry_action",
                "exit_action",
                "entry_timestamp",
                "exit_timestamp",
                "volume",
                "gross_pnl",
                "net_pnl",
            ]
        )

    working = fills.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"])
    records: list[dict[str, Any]] = []
    open_positive = None
    open_reverse = None

    for row in working.to_dict("records"):
        action = str(row["action"])
        if action == "positive_t_sell":
            open_positive = row
        elif action == "positive_t_buyback" and open_positive is not None:
            gross = open_positive["price"] * open_positive["volume"] - row["price"] * row["volume"]
            net = (open_positive["price"] * open_positive["volume"] - open_positive["total_fee"]) - (
                row["price"] * row["volume"] + row["total_fee"]
            )
            records.append(
                {
                    "branch": "positive_t",
                    "entry_action": "positive_t_sell",
                    "exit_action": "positive_t_buyback",
                    "entry_timestamp": open_positive["timestamp"],
                    "exit_timestamp": row["timestamp"],
                    "volume": int(row["volume"]),
                    "gross_pnl": round(float(gross), 6),
                    "net_pnl": round(float(net), 6),
                }
            )
            open_positive = None
        elif action == "reverse_t_buy":
            open_reverse = row
        elif action == "reverse_t_sell" and open_reverse is not None:
            gross = row["price"] * row["volume"] - open_reverse["price"] * open_reverse["volume"]
            net = (row["price"] * row["volume"] - row["total_fee"]) - (
                open_reverse["price"] * open_reverse["volume"] + open_reverse["total_fee"]
            )
            records.append(
                {
                    "branch": "reverse_t",
                    "entry_action": "reverse_t_buy",
                    "exit_action": "reverse_t_sell",
                    "entry_timestamp": open_reverse["timestamp"],
                    "exit_timestamp": row["timestamp"],
                    "volume": int(row["volume"]),
                    "gross_pnl": round(float(gross), 6),
                    "net_pnl": round(float(net), 6),
                }
            )
            open_reverse = None

    return pd.DataFrame(records)


def build_open_legs(fills: pd.DataFrame, *, last_close: float) -> pd.DataFrame:
    if fills.empty:
        return pd.DataFrame(columns=["branch", "action", "timestamp", "price", "volume", "mtm_pnl"])

    working = fills.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"])
    open_positive = None
    open_reverse = None

    for row in working.to_dict("records"):
        action = str(row["action"])
        if action == "positive_t_sell":
            open_positive = row
        elif action == "positive_t_buyback":
            open_positive = None
        elif action == "reverse_t_buy":
            open_reverse = row
        elif action == "reverse_t_sell":
            open_reverse = None

    records: list[dict[str, Any]] = []
    if open_positive is not None:
        records.append(
            {
                "branch": "positive_t",
                "action": "positive_t_sell",
                "timestamp": open_positive["timestamp"],
                "price": float(open_positive["price"]),
                "volume": int(open_positive["volume"]),
                "mtm_pnl": round((float(open_positive["price"]) - last_close) * int(open_positive["volume"]), 6),
            }
        )
    if open_reverse is not None:
        records.append(
            {
                "branch": "reverse_t",
                "action": "reverse_t_buy",
                "timestamp": open_reverse["timestamp"],
                "price": float(open_reverse["price"]),
                "volume": int(open_reverse["volume"]),
                "mtm_pnl": round((last_close - float(open_reverse["price"])) * int(open_reverse["volume"]), 6),
            }
        )
    return pd.DataFrame(records)
