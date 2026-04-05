#!/usr/bin/env python3
"""Manual helper for sending the daily PnL summary notification."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.logger_config import configured_logger as logger
from src.infrastructure.notifications import FeishuNotifier
from src.trading.daily_pnl_calculator import calculate_daily_summary


def main() -> bool:
    print("Manual daily PnL notification")
    print("=" * 50)

    try:
        logger.info("Calculating daily PnL summary...")
        pnl_data = calculate_daily_summary()
        if not pnl_data:
            print("No daily PnL summary was produced.")
            return False

        print(f"Summary date: {pnl_data['date_display']}")
        print(f"Orders: {pnl_data['summary']['total_orders']}")
        print(f"Amount: {pnl_data['summary']['total_amount']:.2f}")

        notifier = FeishuNotifier()
        print("\nSending Feishu notification...")
        success = notifier.notify_daily_pnl_summary(pnl_data)
        if success:
            logger.info("Manual daily PnL notification sent successfully.")
            print("Notification sent.")
            return True

        logger.error("Manual daily PnL notification failed.")
        print("Notification failed.")
        return False
    except Exception as exc:
        logger.error(f"Manual daily PnL notification failed: {exc}")
        print(f"Error: {exc}")
        return False


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
