#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
每日持仓与成交记录导出模块
负责从QMT查询持仓和成交数据，导出为CSV文件并通过SCP上传到NS主机
"""

import csv
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from xtquant.xttrader import XtQuantTrader
from xtquant.xttype import StockAccount

from src.config import settings
from src.logger_config import configured_logger as logger
from src.qmt_constants import get_status_name


class DailyExporter:
    """每日数据导出器"""

    def __init__(self, export_dir: str = "data/daily_export"):
        """
        初始化导出器

        Args:
            export_dir: 导出目录路径
        """
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

        self.xt_trader: Optional[XtQuantTrader] = None
        self.account: Optional[StockAccount] = None

    def connect_qmt(self) -> bool:
        """
        连接QMT

        Returns:
            bool: 连接是否成功
        """
        try:
            logger.info("正在连接QMT...")

            # 创建交易对象
            session_id = settings.qmt_session_id
            self.xt_trader = XtQuantTrader(settings.qmt_path, session_id)

            # 启动并连接
            self.xt_trader.start()
            connect_result = self.xt_trader.connect()

            if connect_result != 0:
                logger.error(f"QMT连接失败，错误码: {connect_result}")
                return False

            # 创建账户对象
            self.account = StockAccount(settings.qmt_account_id)
            logger.info("QMT连接成功")
            return True

        except Exception as e:
            logger.error(f"连接QMT失败: {e}")
            return False

    def disconnect_qmt(self):
        """断开QMT连接"""
        try:
            if self.xt_trader:
                self.xt_trader.stop()
                logger.info("QMT连接已断开")
        except Exception as e:
            logger.error(f"断开QMT连接失败: {e}")

    def export_positions(self, date_str: Optional[str] = None) -> bool:
        """
        导出持仓数据到CSV

        Args:
            date_str: 日期字符串(YYYYMMDD)，默认为今天

        Returns:
            bool: 导出是否成功
        """
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")

        try:
            logger.info("正在查询持仓数据...")

            # 查询持仓
            positions = self.xt_trader.query_stock_positions(self.account)

            if not positions:
                logger.warning("当前无持仓数据")
                return True

            # 准备CSV文件
            csv_file = self.export_dir / f"positions_{date_str}.csv"
            logger.info(f"导出持仓数据到: {csv_file}")

            # 写入CSV
            with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)

                # 写入表头
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

                # 写入数据
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

            logger.info(f"✓ 持仓数据导出成功，共 {len(positions)} 条记录")
            return True

        except Exception as e:
            logger.error(f"导出持仓数据失败: {e}")
            return False

    def export_trades(self, date_str: Optional[str] = None) -> bool:
        """
        导出当日成交记录到CSV

        Args:
            date_str: 日期字符串(YYYYMMDD)，默认为今天

        Returns:
            bool: 导出是否成功
        """
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")

        try:
            logger.info("正在查询当日委托成交数据...")

            # 查询当日所有委托（包括已成交和未成交）
            orders = self.xt_trader.query_stock_orders(self.account, cancelable_only=False)

            if not orders:
                logger.warning("当日无委托成交数据")
                return True

            # 准备CSV文件
            csv_file = self.export_dir / f"trades_{date_str}.csv"
            logger.info(f"导出成交数据到: {csv_file}")

            # 写入CSV
            with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)

                # 写入表头
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

                # 写入数据
                for order in orders:
                    # 获取状态描述
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

            logger.info(f"✓ 成交数据导出成功，共 {len(orders)} 条记录")
            return True

        except Exception as e:
            logger.error(f"导出成交数据失败: {e}")
            return False

    def _upload_via_scp(self, files: List[Path], date_str: str) -> bool:
        """通过scp上传文件到NS主机"""
        ns_host = settings.ns_host
        remote_base = settings.ns_scp_remote_dir
        remote_dir = f"{remote_base}/{date_str}"

        try:
            # 创建远程日期子目录
            mkdir_result = subprocess.run(
                ["ssh", ns_host, "mkdir", "-p", remote_dir],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if mkdir_result.returncode != 0:
                logger.warning(f"创建远程目录失败: {mkdir_result.stderr.strip()}")
                return False

            # scp上传文件
            scp_args = ["scp"] + [str(f) for f in files] + [f"{ns_host}:{remote_dir}/"]
            scp_result = subprocess.run(
                scp_args,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if scp_result.returncode != 0:
                logger.warning(f"SCP上传失败: {scp_result.stderr.strip()}")
                return False

            logger.info(f"✓ 文件已上传到 {ns_host}:{remote_dir}/ ({len(files)} 个文件)")
            return True

        except subprocess.TimeoutExpired:
            logger.warning("SCP上传超时")
            return False
        except Exception as e:
            logger.warning(f"SCP上传异常: {e}")
            return False

    def export_all(self, date_str: Optional[str] = None) -> bool:
        """
        导出所有数据（持仓+成交），并通过SCP上传到NS主机

        Args:
            date_str: 日期字符串(YYYYMMDD)，默认为今天

        Returns:
            bool: 导出是否成功
        """
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")

        logger.info(f"开始导出 {date_str} 的交易数据...")

        # 连接QMT
        if not self.connect_qmt():
            return False

        try:
            # 导出持仓
            positions_ok = self.export_positions(date_str)

            # 导出成交
            trades_ok = self.export_trades(date_str)

            success = positions_ok and trades_ok

            if success:
                logger.info(f"✓ 所有数据导出完成，保存在: {self.export_dir}")

                # SCP上传到NS主机（失败不阻塞导出）
                csv_files = list(self.export_dir.glob(f"*_{date_str}.csv"))
                if csv_files:
                    self._upload_via_scp(csv_files, date_str)
            else:
                logger.error("部分数据导出失败")

            return success

        finally:
            self.disconnect_qmt()


def export_daily_data(date_str: Optional[str] = None) -> bool:
    """
    导出每日交易数据（便捷函数）

    Args:
        date_str: 日期字符串(YYYYMMDD)，默认为今天

    Returns:
        bool: 导出是否成功
    """
    exporter = DailyExporter()
    return exporter.export_all(date_str)
