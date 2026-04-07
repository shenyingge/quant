import pandas as pd

from src.backtest.metrics import summarize_backtest
from src.strategy.core.models import PortfolioState


def test_summarize_backtest_separates_realized_t_pnl_and_open_leg_mtm():
    minute_data = pd.DataFrame({"close": [10.0, 10.2, 10.5]})
    fills = pd.DataFrame(
        [
            {
                "timestamp": "2026-03-26 09:50:00+08:00",
                "action": "reverse_t_buy",
                "price": 10.0,
                "volume": 1000,
                "total_fee": 5.0,
            },
            {
                "timestamp": "2026-03-26 13:30:00+08:00",
                "action": "reverse_t_sell",
                "price": 10.3,
                "volume": 1000,
                "total_fee": 5.0,
            },
            {
                "timestamp": "2026-03-27 10:00:00+08:00",
                "action": "positive_t_sell",
                "price": 10.8,
                "volume": 500,
                "total_fee": 5.0,
            },
        ]
    )
    initial_position = PortfolioState(
        total_position=4000,
        available_volume=4000,
        cost_price=10.0,
        base_position=3000,
        tactical_position=1000,
        max_position=4000,
        t0_sell_available=1000,
        t0_buy_capacity=0,
        cash_available=250000.0,
    )
    final_position = PortfolioState(
        total_position=3500,
        available_volume=3500,
        cost_price=10.0,
        base_position=3000,
        tactical_position=1000,
        max_position=4000,
        t0_sell_available=500,
        t0_buy_capacity=500,
        cash_available=255285.0,
    )

    summary = summarize_backtest(
        minute_data=minute_data,
        fills=fills,
        final_position=final_position,
        symbol="601138.SH",
        execution_mode="same_bar_close",
        initial_position=initial_position,
    )

    assert summary["net_realized_t_pnl"] == 290.0
    assert summary["open_legs_mtm_pnl"] == 150.0
