#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据下载器
基于QMT xtquant接口下载市场数据
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from xtquant import xtdata

from .storage import MarketDataStorage
from .universe import StockUniverse

logger = logging.getLogger(__name__)


class DataDownloader:
    """
    数据下载器
    封装QMT数据下载逻辑，类似examples/tmp.py的方式
    """

    def __init__(self, storage_path: str = "c:/Users/shen/z/market_data"):
        """
        初始化数据下载器

        Args:
            storage_path: 数据存储路径
        """
        self.storage = MarketDataStorage(storage_path)
        self.universe = StockUniverse(f"{storage_path}/universe")
        self.progress_file = Path(storage_path) / "download_progress.json"
        logger.info(f"数据下载器初始化完成，存储路径: {storage_path}")

    def download_history_data(
        self, codes: List[str], period: str = "1m", start: str = "20240101", end: str = "20301231"
    ) -> bool:
        """
        下载历史数据（类似 tmp.py 的方式）

        Args:
            codes: 股票代码列表
            period: 数据周期 ('day', '1m', '5m', '15m', '30m', '60m')
            start: 开始日期
            end: 结束日期

        Returns:
            是否全部下载成功
        """
        logger.info(f"开始下载数据: {codes}, 周期: {period}, 时间范围: {start}-{end}")

        success_count = 0

        # 下载数据
        for code in codes:
            try:
                ok = xtdata.download_history_data(code, period, start, end)
                if ok:
                    success_count += 1
                    logger.info(f"下载成功: {code}")
                else:
                    logger.warning(f"下载失败: {code}")

            except Exception as e:
                logger.error(f"下载异常 {code}: {e}")

        logger.info(f"下载完成: {success_count}/{len(codes)} 成功")
        return success_count == len(codes)

    def download_and_save(
        self,
        codes: List[str],
        period: str = "1m",
        start: str = "20240101",
        end: str = "20301231",
        format: str = "parquet",
    ) -> bool:
        """
        下载并保存数据

        Args:
            codes: 股票代码列表
            period: 数据周期
            start: 开始日期
            end: 结束日期
            format: 存储格式

        Returns:
            是否成功
        """
        try:
            # 1. 下载数据
            if not self.download_history_data(codes, period, start, end):
                logger.warning("部分数据下载失败，继续处理已下载的数据")

            # 2. 获取本地数据
            res = xtdata.get_local_data(
                stock_list=codes, period=period, start_time=start, end_time=end
            )

            if res is None:
                logger.error("未获取到任何数据")
                return False

            if isinstance(res, dict):
                if not res:
                    logger.error("未获取到任何数据")
                    return False
            elif res.empty:
                logger.error("未获取到任何数据")
                return False

            # 3. 确定数据类型
            data_type = "daily" if period == "day" else "minute"

            # 4. 保存数据
            self.storage.save_market_data(res, data_type=data_type, format=format)

            total_symbols = len(res) if isinstance(res, dict) else len(res.columns)
            logger.info(f"数据处理完成，共 {total_symbols} 只股票")
            return True

        except Exception as e:
            logger.error(f"数据处理失败: {e}")
            return False

    def get_available_data(
        self, codes: List[str], period: str = "1m", start: str = "20240101", end: str = "20301231"
    ) -> Optional[dict]:
        """
        获取本地可用数据（不下载）

        Args:
            codes: 股票代码列表
            period: 数据周期
            start: 开始日期
            end: 结束日期

        Returns:
            数据字典或None
        """
        try:
            res = xtdata.get_local_data(
                stock_list=codes, period=period, start_time=start, end_time=end
            )

            if res is None:
                logger.warning("本地无可用数据")
                return None

            if isinstance(res, dict):
                if res:
                    logger.info(f"获取本地数据成功，共 {len(res)} 只股票")
                    return res
                logger.warning("本地无可用数据")
                return None

            if not res.empty:
                logger.info(f"获取本地数据成功，共 {len(res.columns)} 只股票")
                return res

            logger.warning("本地无可用数据")
            return None

        except Exception as e:
            logger.error(f"获取本地数据失败: {e}")
            return None

    def download_full_market(
        self,
        market: str = "ALL",
        period: str = "1m",
        start: str = "20240101",
        end: str = "20301231",
        batch_size: int = 50,
        max_workers: int = 3,
        include_st: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        retry_failed: bool = True,
    ) -> Dict[str, Any]:
        """
        下载全市场数据

        Args:
            market: 市场类型 ("ALL", "SH", "SZ", "CYB", "KCB")
            period: 数据周期
            start: 开始日期
            end: 结束日期
            batch_size: 批量大小
            max_workers: 最大并发数
            include_st: 是否包含ST股票
            progress_callback: 进度回调函数 (completed, total, current_stock)
            retry_failed: 是否重试失败的股票

        Returns:
            下载结果统计
        """
        start_time = datetime.now()
        logger.info(f"开始全市场数据下载: {market}, 周期: {period}, 时间范围: {start}-{end}")

        # 1. 获取股票代码
        stocks = self.universe.get_all_stocks(market, include_st)
        stocks = stocks[0:1]
        if not stocks:
            logger.error("未获取到股票代码")
            return {"success": False, "error": "无股票代码"}

        total_stocks = len(stocks)
        logger.info(f"待下载股票数量: {total_stocks}")

        # 2. 加载进度（支持断点续传）
        completed_stocks, failed_stocks = self._load_progress()
        remaining_stocks = [s for s in stocks if s not in completed_stocks]

        if remaining_stocks != stocks:
            logger.info(f"断点续传: 剩余 {len(remaining_stocks)} 只股票")

        # 3. 批量下载
        results = {
            "success": True,
            "total": total_stocks,
            "completed": len(completed_stocks),
            "failed": len(failed_stocks),
            "skipped": 0,
            "start_time": start_time.isoformat(),
            "failed_stocks": failed_stocks.copy(),
        }

        try:
            for i in range(0, len(remaining_stocks), batch_size):
                batch = remaining_stocks[i : i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(remaining_stocks) + batch_size - 1) // batch_size

                logger.info(f"处理第 {batch_num}/{total_batches} 批，股票数: {len(batch)}")

                batch_results = self._download_batch(
                    batch, period, start, end, max_workers, progress_callback, results
                )

                results["completed"] += batch_results["completed"]
                results["failed"] += batch_results["failed"]
                results["failed_stocks"].extend(batch_results["failed_stocks"])

                # 保存进度
                self._save_progress(results["completed"], results["failed_stocks"])

                # 批次间休息
                if i + batch_size < len(remaining_stocks):
                    time.sleep(1)

            # 4. 重试失败的股票
            if retry_failed and results["failed_stocks"]:
                logger.info(f"重试失败的股票: {len(results['failed_stocks'])} 只")
                retry_results = self._retry_failed_stocks(
                    results["failed_stocks"], period, start, end, progress_callback
                )
                results["completed"] += retry_results["completed"]
                results["failed"] -= retry_results["completed"]
                results["failed_stocks"] = retry_results["remaining_failed"]

            # 5. 完成统计
            end_time = datetime.now()
            results["end_time"] = end_time.isoformat()
            results["duration"] = (end_time - start_time).total_seconds()
            results["success_rate"] = results["completed"] / total_stocks * 100

            logger.info(
                f"全市场下载完成: 成功 {results['completed']}/{total_stocks} "
                f"({results['success_rate']:.1f}%), 耗时 {results['duration']:.1f}秒"
            )

            # 清理进度文件
            if results["failed"] == 0:
                self._clear_progress()

            return results

        except Exception as e:
            logger.error(f"全市场下载失败: {e}")
            results["success"] = False
            results["error"] = str(e)
            return results

    def _download_batch(
        self,
        batch: List[str],
        period: str,
        start: str,
        end: str,
        max_workers: int,
        progress_callback: Optional[Callable],
        results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """批量下载一批股票"""
        batch_results = {"completed": 0, "failed": 0, "failed_stocks": []}

        if max_workers > 1:
            # 并发下载
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self._download_single_stock, stock, period, start, end): stock
                    for stock in batch
                }

                for future in as_completed(futures):
                    stock = futures[future]
                    try:
                        success = future.result()
                        if success:
                            batch_results["completed"] += 1
                        else:
                            batch_results["failed"] += 1
                            batch_results["failed_stocks"].append(stock)

                        if progress_callback:
                            progress_callback(
                                results["completed"] + batch_results["completed"],
                                results["total"],
                                stock,
                            )

                    except Exception as e:
                        logger.error(f"下载异常 {stock}: {e}")
                        batch_results["failed"] += 1
                        batch_results["failed_stocks"].append(stock)
        else:
            # 串行下载
            for stock in batch:
                try:
                    success = self._download_single_stock(stock, period, start, end)
                    if success:
                        batch_results["completed"] += 1
                    else:
                        batch_results["failed"] += 1
                        batch_results["failed_stocks"].append(stock)

                    if progress_callback:
                        progress_callback(
                            results["completed"] + batch_results["completed"],
                            results["total"],
                            stock,
                        )

                except Exception as e:
                    logger.error(f"下载异常 {stock}: {e}")
                    batch_results["failed"] += 1
                    batch_results["failed_stocks"].append(stock)

        return batch_results

    def _download_single_stock(self, stock: str, period: str, start: str, end: str) -> bool:
        """下载单只股票数据"""
        try:
            success = xtdata.download_history_data(stock, period, start, end)
            if success:
                logger.debug(f"下载成功: {stock}")
            else:
                logger.warning(f"下载失败: {stock}")
            return success
        except Exception as e:
            logger.error(f"下载异常 {stock}: {e}")
            return False

    def _retry_failed_stocks(
        self,
        failed_stocks: List[str],
        period: str,
        start: str,
        end: str,
        progress_callback: Optional[Callable],
    ) -> Dict[str, Any]:
        """重试失败的股票"""
        retry_results = {"completed": 0, "remaining_failed": []}

        for stock in failed_stocks:
            try:
                success = self._download_single_stock(stock, period, start, end)
                if success:
                    retry_results["completed"] += 1
                    logger.info(f"重试成功: {stock}")
                else:
                    retry_results["remaining_failed"].append(stock)

                if progress_callback:
                    progress_callback(-1, -1, f"重试: {stock}")

                time.sleep(0.5)  # 重试间隔

            except Exception as e:
                logger.error(f"重试异常 {stock}: {e}")
                retry_results["remaining_failed"].append(stock)

        return retry_results

    def _load_progress(self) -> tuple[List[str], List[str]]:
        """加载下载进度"""
        if not self.progress_file.exists():
            return [], []

        try:
            with open(self.progress_file, "r", encoding="utf-8") as f:
                progress = json.load(f)
            return progress.get("completed", []), progress.get("failed", [])
        except Exception as e:
            logger.warning(f"加载进度文件失败: {e}")
            return [], []

    def _save_progress(self, completed: int, failed_stocks: List[str]) -> None:
        """保存下载进度"""
        try:
            progress = {
                "completed_count": completed,
                "failed": failed_stocks,
                "last_update": datetime.now().isoformat(),
            }

            with open(self.progress_file, "w", encoding="utf-8") as f:
                json.dump(progress, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.warning(f"保存进度文件失败: {e}")

    def _clear_progress(self) -> None:
        """清理进度文件"""
        try:
            if self.progress_file.exists():
                self.progress_file.unlink()
                logger.info("进度文件已清理")
        except Exception as e:
            logger.warning(f"清理进度文件失败: {e}")

    def save_downloaded_data(
        self,
        market: str = "ALL",
        period: str = "1m",
        start: str = "20240101",
        end: str = "20301231",
        format: str = "parquet",
    ) -> bool:
        """
        保存已下载的全市场数据

        Args:
            market: 市场类型
            period: 数据周期
            start: 开始日期
            end: 结束日期
            format: 存储格式

        Returns:
            是否成功
        """
        try:
            stocks = self.universe.get_all_stocks(market)
            if not stocks:
                logger.error("未获取到股票代码")
                return False

            logger.info(f"开始保存全市场数据: {len(stocks)} 只股票")

            # 获取本地数据
            data = xtdata.get_local_data(
                stock_list=stocks, period=period, start_time=start, end_time=end
            )

            if data is None:
                logger.error("未获取到任何数据")
                return False

            if isinstance(data, dict):
                if not data:
                    logger.error("未获取到任何数据")
                    return False
            elif data.empty:
                logger.error("未获取到任何数据")
                return False

            # 确定数据类型
            data_type = "daily" if period == "day" else "minute"

            # 保存数据
            self.storage.save_market_data(data, data_type=data_type, format=format)

            total_symbols = len(data) if isinstance(data, dict) else len(data.columns)
            logger.info(f"全市场数据保存完成，共 {total_symbols} 只股票")
            return True

        except Exception as e:
            logger.error(f"保存全市场数据失败: {e}")
            return False

    def get_download_status(self) -> Dict[str, Any]:
        """获取下载状态"""
        if not self.progress_file.exists():
            return {"status": "no_progress", "message": "无下载进度"}

        try:
            with open(self.progress_file, "r", encoding="utf-8") as f:
                progress = json.load(f)

            return {
                "status": "in_progress",
                "completed_count": progress.get("completed_count", 0),
                "failed_count": len(progress.get("failed", [])),
                "last_update": progress.get("last_update"),
                "failed_stocks": progress.get("failed", []),
            }

        except Exception as e:
            logger.error(f"获取下载状态失败: {e}")
            return {"status": "error", "message": str(e)}
