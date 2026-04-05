from __future__ import annotations

from datetime import time


def get_minute_daily_ingest_schedule_time() -> time:
    # Phase 2 requirement: daily increment sync at 15:10.
    return time(15, 10)
