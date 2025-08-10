#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple trading day check test
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add project path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))


def test_simple_trading_day():
    """Simple trading day check test"""
    print("Testing xtquant trading day check...")

    try:
        from xtquant import xtdata

        print("SUCCESS: xtdata module imported")

        # Get current date
        today = datetime.now()
        today_str = today.strftime("%Y%m%d")

        print(f"Checking if {today_str} is a trading day...")

        # Get current year calendar
        year = today.year
        start_date = f"{year}0101"
        end_date = f"{year}1231"

        print(f"Getting trading calendar for year {year}...")

        # Try to get trading calendar directly (skip download)
        trading_calendar = xtdata.get_trading_calendar("SH", start_date, end_date)

        if trading_calendar is None:
            print("WARNING: Cannot get trading calendar, defaulting to True")
            return True

        print(f"SUCCESS: Got trading calendar with {len(trading_calendar)} trading days")

        # Check if today is trading day
        is_today_trading = today_str in trading_calendar
        result_msg = (
            f"Today {today_str} is {'a TRADING DAY' if is_today_trading else 'NOT a trading day'}"
        )
        print(result_msg)

        # Show last few trading days for reference
        print("\nLast 3 trading days:")
        recent_trading_days = [d for d in trading_calendar if d <= today_str][-3:]
        for day in recent_trading_days:
            marker = " <-- TODAY" if day == today_str else ""
            print(f"  {day}{marker}")

        return is_today_trading

    except ImportError as e:
        print(f"ERROR: Cannot import xtdata: {e}")
        return True
    except Exception as e:
        print(f"ERROR: Exception during check: {e}")
        return True


if __name__ == "__main__":
    result = test_simple_trading_day()
    print(f"\nFINAL RESULT: {'Trading day' if result else 'Not a trading day'}")
