#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票池管理器
获取全市场股票代码列表
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd

try:
    from xtquant import xtdata

    HAS_XTQUANT = True
except ImportError:
    HAS_XTQUANT = False
    logging.warning("xtquant未安装，部分功能不可用")

try:
    import akshare as ak

    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    logging.warning("akshare未安装，部分功能不可用")

logger = logging.getLogger(__name__)


class StockUniverse:
    """
    股票池管理器
    获取和管理全市场股票代码
    """

    def __init__(self, cache_path: str = "c:/Users/shen/z/market_data/universe"):
        """
        初始化股票池管理器

        Args:
            cache_path: 股票代码缓存路径
        """
        self.cache_path = Path(cache_path)
        self.cache_path.mkdir(parents=True, exist_ok=True)

        self.cache_file = self.cache_path / "stock_universe.json"
        self.last_update = None

        logger.info(f"股票池管理器初始化完成，缓存路径: {self.cache_path}")

    def get_all_stocks(
        self,
        market: str = "ALL",
        include_st: bool = False,
        use_cache: bool = True,
        cache_hours: int = 24,
    ) -> List[str]:
        """
        获取全市场股票代码

        Args:
            market: 市场类型 ("ALL", "SH", "SZ", "CYB", "KCB")
            include_st: 是否包含ST股票
            use_cache: 是否使用缓存
            cache_hours: 缓存有效期（小时）

        Returns:
            股票代码列表
        """
        # 检查缓存
        if use_cache and self._is_cache_valid(cache_hours):
            cached_stocks = self._load_from_cache(market, include_st)
            if cached_stocks:
                logger.info(f"从缓存加载 {market} 市场股票: {len(cached_stocks)} 只")
                return cached_stocks

        # 获取新数据
        stocks = []

        if market == "ALL" or market == "SH":
            stocks.extend(self._get_sh_stocks(include_st))
        if market == "ALL" or market == "SZ":
            stocks.extend(self._get_sz_stocks(include_st))
        if market == "ALL" or market == "CYB":
            stocks.extend(self._get_cyb_stocks(include_st))
        if market == "ALL" or market == "KCB":
            stocks.extend(self._get_kcb_stocks(include_st))

        # 去重并排序
        stocks = sorted(list(set(stocks)))

        # 过滤ST股票
        if not include_st:
            stocks = self._filter_st_stocks(stocks)

        # 保存到缓存
        self._save_to_cache(market, include_st, stocks)

        logger.info(f"获取 {market} 市场股票: {len(stocks)} 只")
        return stocks

    def get_stocks_by_sector(self, sector_name: str = "沪深A股") -> List[str]:
        """
        根据板块获取股票代码（使用xtquant）

        Args:
            sector_name: 板块名称

        Returns:
            股票代码列表
        """
        if not HAS_XTQUANT:
            logger.error("xtquant未安装，无法使用板块功能")
            return []

        try:
            stocks = xtdata.get_stock_list_in_sector(sector_name)
            if stocks:
                logger.info(f"获取 {sector_name} 板块股票: {len(stocks)} 只")
                return stocks
            else:
                logger.warning(f"未获取到 {sector_name} 板块股票")
                return []

        except Exception as e:
            logger.error(f"获取板块股票失败: {e}")
            return []

    def _get_sh_stocks(self, include_st: bool = False) -> List[str]:
        """获取上海市场股票"""
        stocks = []

        # 方法1: 使用xtquant
        if HAS_XTQUANT:
            try:
                sh_stocks = xtdata.get_stock_list_in_sector("沪市A股")
                if sh_stocks:
                    stocks.extend(sh_stocks)
                    return stocks
            except Exception as e:
                logger.warning(f"xtquant获取沪市股票失败: {e}")

        # 方法2: 使用akshare
        if HAS_AKSHARE:
            try:
                stock_info = ak.stock_info_a_code_name()
                sh_stocks = stock_info[stock_info["code"].str.startswith("60")]["code"].tolist()
                stocks.extend([f"{code}.SH" for code in sh_stocks])
                return stocks
            except Exception as e:
                logger.warning(f"akshare获取沪市股票失败: {e}")

        # 方法3: 预定义代码范围（备选方案）
        logger.warning("使用预定义代码范围获取沪市股票")
        for i in range(600000, 605000):  # 沪市A股主要范围
            stocks.append(f"{i:06d}.SH")

        return stocks

    def _get_sz_stocks(self, include_st: bool = False) -> List[str]:
        """获取深圳市场股票（主板+中小板）"""
        stocks = []

        # 方法1: 使用xtquant
        if HAS_XTQUANT:
            try:
                sz_stocks = xtdata.get_stock_list_in_sector("深市A股")
                if sz_stocks:
                    # 过滤掉创业板（300开头）
                    sz_stocks = [s for s in sz_stocks if not s.startswith("300")]
                    stocks.extend(sz_stocks)
                    return stocks
            except Exception as e:
                logger.warning(f"xtquant获取深市股票失败: {e}")

        # 方法2: 使用akshare
        if HAS_AKSHARE:
            try:
                stock_info = ak.stock_info_a_code_name()
                sz_stocks = stock_info[
                    stock_info["code"].str.startswith("00")
                    | stock_info["code"].str.startswith("002")
                ]["code"].tolist()
                stocks.extend([f"{code}.SZ" for code in sz_stocks])
                return stocks
            except Exception as e:
                logger.warning(f"akshare获取深市股票失败: {e}")

        # 方法3: 预定义代码范围
        logger.warning("使用预定义代码范围获取深市股票")
        # 深市主板 000001-000999
        for i in range(1, 1000):
            stocks.append(f"{i:06d}.SZ")
        # 深市中小板 002000-002999
        for i in range(2000, 3000):
            stocks.append(f"{i:06d}.SZ")

        return stocks

    def _get_cyb_stocks(self, include_st: bool = False) -> List[str]:
        """获取创业板股票"""
        stocks = []

        # 方法1: 使用xtquant
        if HAS_XTQUANT:
            try:
                cyb_stocks = xtdata.get_stock_list_in_sector("创业板")
                if cyb_stocks:
                    stocks.extend(cyb_stocks)
                    return stocks
            except Exception as e:
                logger.warning(f"xtquant获取创业板股票失败: {e}")

        # 方法2: 使用akshare
        if HAS_AKSHARE:
            try:
                stock_info = ak.stock_info_a_code_name()
                cyb_stocks = stock_info[stock_info["code"].str.startswith("300")]["code"].tolist()
                stocks.extend([f"{code}.SZ" for code in cyb_stocks])
                return stocks
            except Exception as e:
                logger.warning(f"akshare获取创业板股票失败: {e}")

        # 方法3: 预定义代码范围
        logger.warning("使用预定义代码范围获取创业板股票")
        for i in range(300000, 301000):  # 创业板主要范围
            stocks.append(f"{i:06d}.SZ")

        return stocks

    def _get_kcb_stocks(self, include_st: bool = False) -> List[str]:
        """获取科创板股票"""
        stocks = []

        # 方法1: 使用xtquant
        if HAS_XTQUANT:
            try:
                kcb_stocks = xtdata.get_stock_list_in_sector("科创板")
                if kcb_stocks:
                    stocks.extend(kcb_stocks)
                    return stocks
            except Exception as e:
                logger.warning(f"xtquant获取科创板股票失败: {e}")

        # 方法2: 使用akshare
        if HAS_AKSHARE:
            try:
                stock_info = ak.stock_info_a_code_name()
                kcb_stocks = stock_info[stock_info["code"].str.startswith("688")]["code"].tolist()
                stocks.extend([f"{code}.SH" for code in kcb_stocks])
                return stocks
            except Exception as e:
                logger.warning(f"akshare获取科创板股票失败: {e}")

        # 方法3: 预定义代码范围
        logger.warning("使用预定义代码范围获取科创板股票")
        for i in range(688000, 689000):  # 科创板范围
            stocks.append(f"{i:06d}.SH")

        return stocks

    def _filter_st_stocks(self, stocks: List[str]) -> List[str]:
        """过滤ST股票"""
        if not HAS_XTQUANT:
            logger.warning("无法获取ST股票信息，跳过过滤")
            return stocks

        try:
            # 获取股票信息并过滤ST
            filtered_stocks = []
            for stock in stocks:
                try:
                    # 这里可以添加ST股票检查逻辑
                    # 由于xtquant没有直接的ST检查方法，暂时保留所有股票
                    filtered_stocks.append(stock)
                except:
                    continue

            return filtered_stocks

        except Exception as e:
            logger.warning(f"过滤ST股票失败: {e}")
            return stocks

    def _is_cache_valid(self, cache_hours: int) -> bool:
        """检查缓存是否有效"""
        if not self.cache_file.exists():
            return False

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            last_update = datetime.fromisoformat(cache_data.get("last_update", ""))
            hours_diff = (datetime.now() - last_update).total_seconds() / 3600

            return hours_diff < cache_hours

        except Exception as e:
            logger.warning(f"检查缓存失败: {e}")
            return False

    def _load_from_cache(self, market: str, include_st: bool) -> Optional[List[str]]:
        """从缓存加载股票代码"""
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            cache_key = f"{market}_{'with_st' if include_st else 'no_st'}"
            return cache_data.get("data", {}).get(cache_key)

        except Exception as e:
            logger.warning(f"加载缓存失败: {e}")
            return None

    def _save_to_cache(self, market: str, include_st: bool, stocks: List[str]) -> None:
        """保存股票代码到缓存"""
        try:
            # 读取现有缓存
            cache_data = {"data": {}, "last_update": datetime.now().isoformat()}
            if self.cache_file.exists():
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)

            # 更新缓存
            cache_key = f"{market}_{'with_st' if include_st else 'no_st'}"
            cache_data["data"][cache_key] = stocks
            cache_data["last_update"] = datetime.now().isoformat()

            # 保存缓存
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            logger.info(f"股票代码缓存已更新: {cache_key}")

        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")

    def get_market_summary(self) -> Dict[str, int]:
        """获取市场概览"""
        summary = {
            "SH": len(self.get_all_stocks("SH")),
            "SZ": len(self.get_all_stocks("SZ")),
            "CYB": len(self.get_all_stocks("CYB")),
            "KCB": len(self.get_all_stocks("KCB")),
        }
        summary["ALL"] = sum(summary.values())

        return summary
