"""Backtrader DataFeed adapter for QMT data."""

from __future__ import annotations

import backtrader as bt


class QMTDataFeed(bt.CSVDataBase):
    """Backtrader DataFeed adapter for QMT data."""

    params = (
        ("stock_code", None),
        ("name", "QMT"),
    )

    def _load(self):
        """Load data (minimal implementation)."""
        # Subclasses would override this with actual QMT data loading
        return False
