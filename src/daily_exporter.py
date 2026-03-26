#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Daily positions/trades exporter with optional rsync upload.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from xtquant.xttrader import XtQuantTrader
from xtquant.xttype import StockAccount

from src.config import settings
from src.logger_config import configured_logger as logger
from src.qmt_constants import get_status_name
from src.remote_sync import sync_files_via_rsync


class DailyExporter:
    """Export daily positions and trades, then optionally sync them remotely."""

    def __init__(self, export_dir: str = "data/daily_export"):
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

        self.xt_trader: Optional[XtQuantTrader] = None
        self.account: Optional[StockAccount] = None

    def connect_qmt(self) -> bool:
        """Connect to QMT."""
        try:
            logger.info("正在连接 QMT...")

            session_id = settings.qmt_session_id
            self.xt_trader = XtQuantTrader(settings.qmt_path, session_id)
            self.xt_trader.start()
            connect_result = self.xt_trader.connect()

            if connect_result != 0:
                logger.error(f"QMT 连接失败，错误码: {connect_result}")
                return False

            self.account = StockAccount(settings.qmt_account_id)
            logger.info("QMT 连接成功")
            return True
        except Exception as exc:
            logger.error(f"连接 QMT 失败: {exc}")
            return False

    def disconnect_qmt(self):
        """Disconnect from QMT."""
        try:
            if self.xt_trader:
                self.xt_trader.stop()
                logger.info("QMT 连接已断开")
        except Exception as exc:
            logger.error(f"断开 QMT 连接失败: {exc}")

    def export_positions(self, date_str: Optional[str] = None) -> bool:
        """Export positions to CSV."""
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")

        try:
            logger.info("正在查询持仓数据...")
            positions = self.xt_trader.query_stock_positions(self.account)

            if not positions:
                logger.warning("当前无持仓数据")
                return True

            csv_file = self.export_dir / f"positions_{date_str}.csv"
            logger.info(f"导出持仓数据到: {csv_file}")

            with csv_file.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "stock_code",
                        "volume",
                        "can_use_volume",
                        "avg_price",
                        "last_price",
                        "market_value",
                        "float_profit",
                        "profit_rate",
                    ]
                )

                for pos in positions:
                    writer.writerow(
                        [
                            pos.stock_code,
                            pos.volume,
                            pos.can_use_volume,
                            f"{pos.avg_price:.4f}",
                            f"{pos.last_price:.2f}",
                            f"{pos.market_value:.2f}",
                            f"{pos.float_profit:.2f}",
                            f"{pos.profit_rate:.4f}",
                        ]
                    )

            logger.info(f"持仓数据导出成功，共 {len(positions)} 条记录")
            return True
        except Exception as exc:
            logger.error(f"导出持仓数据失败: {exc}")
            return False

    def export_trades(self, date_str: Optional[str] = None) -> bool:
        """Export today trades/orders to CSV."""
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")

        try:
            logger.info("正在查询当日委托成交数据...")
            orders = self.xt_trader.query_stock_orders(self.account, cancelable_only=False)

            if not orders:
                logger.warning("当日无委托成交数据")
                return True

            csv_file = self.export_dir / f"trades_{date_str}.csv"
            logger.info(f"导出成交数据到: {csv_file}")

            with csv_file.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "order_id",
                        "stock_code",
                        "order_type",
                        "order_volume",
                        "price",
                        "traded_volume",
                        "traded_price",
                        "order_status",
                        "order_time",
                        "status_desc",
                    ]
                )

                for order in orders:
                    status_desc = get_status_name(order.order_status)
                    writer.writerow(
                        [
                            order.order_id,
                            order.stock_code,
                            order.order_type,
                            order.order_volume,
                            f"{order.price:.2f}",
                            order.traded_volume,
                            f"{order.traded_price:.2f}" if order.traded_price else "0.00",
                            order.order_status,
                            order.order_time,
                            status_desc,
                        ]
                    )

            logger.info(f"成交数据导出成功，共 {len(orders)} 条记录")
            return True
        except Exception as exc:
            logger.error(f"导出成交数据失败: {exc}")
            return False

    def _upload_via_rsync(self, files: List[Path], date_str: str) -> bool:
        """Use rsync to upload files to the remote data directory."""
        try:
            remote_files = sync_files_via_rsync(
                files=files,
                remote_subdir=date_str,
                remote_base=settings.ns_scp_remote_dir,
                alias_or_host=settings.ns_host,
                timeout=20,
            )
            logger.info(
                f"文件已通过 rsync 同步到 {settings.ns_host}:{date_str}/，共 {len(remote_files)} 个文件"
            )
            return True
        except Exception as exc:
            logger.warning(f"rsync 同步失败: {exc}")
            return False

    def export_all(self, date_str: Optional[str] = None) -> bool:
        """Export positions and trades, then try syncing them remotely."""
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")

        logger.info(f"开始导出 {date_str} 的交易数据...")

        if not self.connect_qmt():
            return False

        try:
            positions_ok = self.export_positions(date_str)
            trades_ok = self.export_trades(date_str)
            success = positions_ok and trades_ok

            if success:
                logger.info(f"所有数据导出完成，保存在: {self.export_dir}")
                csv_files = list(self.export_dir.glob(f"*_{date_str}.csv"))
                if csv_files:
                    self._upload_via_rsync(csv_files, date_str)
            else:
                logger.error("部分数据导出失败")

            return success
        finally:
            self.disconnect_qmt()


def export_daily_data(date_str: Optional[str] = None) -> bool:
    """Convenience entry for daily export."""
    exporter = DailyExporter()
    return exporter.export_all(date_str)
