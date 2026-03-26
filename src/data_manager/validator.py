#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据验证器
按照 market_data_format.md 规范验证数据质量
"""

import logging
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


class DataValidator:
    """
    数据验证器
    验证市场数据的完整性和质量
    """

    # 必需字段定义
    REQUIRED_FIELDS = ["open", "high", "low", "close", "volume"]
    OPTIONAL_FIELDS = [
        "amount",
        "pre_close",
        "high_limit",
        "low_limit",
        "turnover_rate",
        "pe_ratio",
        "pb_ratio",
    ]

    def validate_market_data(self, data: pd.DataFrame, symbol: str) -> bool:
        """
        验证市场数据完整性和质量

        Args:
            data: 市场数据
            symbol: 股票代码

        Returns:
            是否通过验证
        """
        validation_results = {
            "required_fields": self._check_required_fields(data, symbol),
            "data_types": self._check_data_types(data, symbol),
            "datetime_index": self._check_datetime_index(data, symbol),
            "price_logic": self._check_price_logic(data, symbol),
            "negative_values": self._check_negative_values(data, symbol),
            "missing_values": self._check_missing_values(data, symbol),
        }

        # 统计验证结果
        passed_checks = sum(validation_results.values())
        total_checks = len(validation_results)

        logger.info(f"{symbol} 数据验证完成: {passed_checks}/{total_checks} 项通过")

        # 只有基础检查失败才返回False
        critical_checks = ["required_fields", "datetime_index"]
        critical_passed = all(validation_results[check] for check in critical_checks)

        return critical_passed

    def _check_required_fields(self, data: pd.DataFrame, symbol: str) -> bool:
        """检查必需字段"""
        missing_fields = set(self.REQUIRED_FIELDS) - set(data.columns)
        if missing_fields:
            logger.error(f"{symbol} 缺少必需字段: {missing_fields}")
            return False
        return True

    def _check_data_types(self, data: pd.DataFrame, symbol: str) -> bool:
        """检查数据类型"""
        numeric_columns = self.REQUIRED_FIELDS + [
            col for col in self.OPTIONAL_FIELDS if col in data.columns
        ]

        type_errors = []
        for col in numeric_columns:
            if col in data.columns and not pd.api.types.is_numeric_dtype(data[col]):
                type_errors.append(col)

        if type_errors:
            logger.warning(f"{symbol} 数据类型错误: {type_errors}")
            return False
        return True

    def _check_datetime_index(self, data: pd.DataFrame, symbol: str) -> bool:
        """检查时间索引"""
        if not isinstance(data.index, pd.DatetimeIndex):
            logger.error(f"{symbol} 时间索引类型错误")
            return False
        return True

    def _check_price_logic(self, data: pd.DataFrame, symbol: str) -> bool:
        """检查价格逻辑"""
        # 检查OHLC价格逻辑
        price_logic_errors = data[
            (data["high"] < data["low"])
            | (data["close"] < data["low"])
            | (data["close"] > data["high"])
            | (data["open"] < data["low"])
            | (data["open"] > data["high"])
        ]

        if not price_logic_errors.empty:
            logger.warning(f"{symbol} 发现 {len(price_logic_errors)} 条价格逻辑错误")
            return False
        return True

    def _check_negative_values(self, data: pd.DataFrame, symbol: str) -> bool:
        """检查负值或零值"""
        price_cols = ["open", "high", "low", "close"]
        negative_prices = data[price_cols] <= 0

        if negative_prices.any().any():
            logger.warning(f"{symbol} 发现负价格或零价格")
            return False
        return True

    def _check_missing_values(self, data: pd.DataFrame, symbol: str) -> bool:
        """检查缺失值"""
        critical_cols = ["open", "high", "low", "close"]
        missing_data = data[critical_cols].isnull()

        if missing_data.any().any():
            missing_count = missing_data.sum().sum()
            logger.warning(f"{symbol} 发现 {missing_count} 个关键字段缺失值")
            return False
        return True

    def get_data_summary(self, data: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """
        获取数据摘要信息

        Args:
            data: 市场数据
            symbol: 股票代码

        Returns:
            数据摘要字典
        """
        summary = {
            "symbol": symbol,
            "shape": data.shape,
            "columns": list(data.columns),
            "date_range": {"start": data.index.min(), "end": data.index.max()},
            "price_range": (
                {
                    "min": data["close"].min(),
                    "max": data["close"].max(),
                    "mean": data["close"].mean(),
                }
                if "close" in data.columns
                else None
            ),
            "volume_stats": (
                {
                    "total": data["volume"].sum(),
                    "mean": data["volume"].mean(),
                    "max": data["volume"].max(),
                }
                if "volume" in data.columns
                else None
            ),
            "missing_values": data.isnull().sum().to_dict(),
            "data_quality_score": self._calculate_quality_score(data),
        }

        return summary

    def _calculate_quality_score(self, data: pd.DataFrame) -> float:
        """
        计算数据质量分数 (0-100)

        Args:
            data: 市场数据

        Returns:
            质量分数
        """
        score = 100.0

        # 缺失值扣分
        missing_rate = data.isnull().sum().sum() / (data.shape[0] * data.shape[1])
        score -= missing_rate * 30

        # 价格逻辑错误扣分
        if all(col in data.columns for col in ["high", "low", "close", "open"]):
            price_errors = len(
                data[
                    (data["high"] < data["low"])
                    | (data["close"] < data["low"])
                    | (data["close"] > data["high"])
                ]
            )
            error_rate = price_errors / len(data)
            score -= error_rate * 40

        # 负值扣分
        price_cols = [col for col in ["open", "high", "low", "close"] if col in data.columns]
        if price_cols:
            negative_rate = (data[price_cols] <= 0).sum().sum() / (len(data) * len(price_cols))
            score -= negative_rate * 20

        return max(0.0, min(100.0, score))
