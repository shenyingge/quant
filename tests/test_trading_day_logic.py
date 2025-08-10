#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test complete trading day check logic
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# Import configuration
from config import settings


def test_trading_day_logic():
    """Test the complete trading day check logic"""
    print("=" * 60)
    print("Testing Complete Trading Day Check Logic")
    print("=" * 60)

    # Test different scenarios
    test_dates = [
        datetime.now(),  # Today
        datetime.now() - timedelta(days=1),  # Yesterday
        datetime.now() + timedelta(days=1),  # Tomorrow
    ]

    # Add some weekend dates
    today = datetime.now()
    for i in range(7):
        check_date = today + timedelta(days=i)
        if check_date.weekday() >= 5:  # Saturday or Sunday
            test_dates.append(check_date)

    print(f"\nConfiguration:")
    print(f"  Trading day check enabled: {settings.trading_day_check_enabled}")
    print(f"  Service start time: {settings.service_start_time}")
    print(f"  Service stop time: {settings.service_stop_time}")

    # Test each date
    print(f"\nTesting dates:")
    print("-" * 40)

    for test_date in test_dates[:5]:  # Test first 5 dates
        date_str = test_date.strftime("%Y%m%d")
        weekday = test_date.strftime("%A")

        # Test simple weekday check
        is_weekday = test_date.weekday() < 5
        weekday_result = "Weekday" if is_weekday else "Weekend"

        print(f"{date_str} ({weekday[:3]}) -> {weekday_result}")

    print(f"\nTesting xtquant integration:")
    print("-" * 40)

    try:
        from xtquant import xtdata

        print("SUCCESS: xtquant available")

        # Test actual trading day check
        today_str = datetime.now().strftime("%Y%m%d")
        print(f"Checking {today_str}...")

        try:
            year = datetime.now().year
            start_date = f"{year}0101"
            end_date = f"{year}1231"

            trading_calendar = xtdata.get_trading_calendar("SH", start_date, end_date)

            if trading_calendar is None:
                print("WARNING: Cannot get trading calendar from xtquant")
                result = simple_weekday_check(datetime.now())
            else:
                result = today_str in trading_calendar
                print(f"SUCCESS: Got calendar with {len(trading_calendar)} days")

            print(f"RESULT: Today is {'a trading day' if result else 'NOT a trading day'}")

        except Exception as e:
            print(f"WARNING: xtquant API error: {str(e)[:80]}...")
            result = simple_weekday_check(datetime.now())
            print(f"FALLBACK RESULT: Today is {'a weekday' if result else 'weekend'}")

    except ImportError:
        print("WARNING: xtquant not available")
        result = simple_weekday_check(datetime.now())
        print(f"SIMPLE CHECK RESULT: Today is {'a weekday' if result else 'weekend'}")


def simple_weekday_check(check_date):
    """Simple weekday check function"""
    weekday = check_date.weekday()
    is_weekday = weekday < 5
    weekday_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][
        weekday
    ]
    print(
        f"Simple check: {check_date.strftime('%Y%m%d')} is {weekday_name} -> {'Weekday' if is_weekday else 'Weekend'}"
    )
    return is_weekday


def test_service_logic():
    """Test the service startup logic"""
    print(f"\n{'='*40}")
    print("Testing Service Startup Logic")
    print("=" * 40)

    current_time = datetime.now().time()
    current_date = datetime.now()

    # Parse service times (simulate from settings)
    start_time = datetime.strptime(settings.service_start_time, "%H:%M").time()
    stop_time = datetime.strptime(settings.service_stop_time, "%H:%M").time()

    print(f"Current time: {current_time}")
    print(f"Service schedule: {start_time} - {stop_time}")

    # Check if in time range
    time_in_range = start_time <= current_time <= stop_time
    print(f"In time range: {time_in_range}")

    # Check if trading day
    if settings.trading_day_check_enabled:
        is_trading_day = simple_weekday_check(current_date)
        should_run = time_in_range and is_trading_day
        print(f"Trading day check enabled: {is_trading_day}")
    else:
        should_run = time_in_range
        print("Trading day check disabled")

    print(f"SERVICE SHOULD RUN: {should_run}")


if __name__ == "__main__":
    test_trading_day_logic()
    test_service_logic()
    print(f"\n{'='*60}")
    print("Test completed")
