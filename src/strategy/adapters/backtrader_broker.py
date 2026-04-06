"""Backtrader Broker interface for QMT."""

from __future__ import annotations

import backtrader as bt

from src.infrastructure.logger_config import logger


class QMTBrokerInterface(bt.brokers.BackBroker):
    """Backtrader Broker interface for QMT."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.qmt_orders = {}
        logger.info("QMTBrokerInterface initialized")

    def next(self):
        """Process orders."""
        super().next()
