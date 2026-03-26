#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据存储器
基于 market_data_format.md 规范，提供统一的数据存储接口
"""

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd

from .validator import DataValidator

logger = logging.getLogger(__name__)


class MarketDataStorage:
    """
    市场数据存储器
    按照 market_data_format.md 规范存储数据
    """

    def __init__(self, base_path: str = "c:/Users/shen/z/market_data"):
        """
        初始化数据存储器

        Args:
            base_path: 基础存储路径
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        # 创建子目录结构
        self.paths = {
            "daily": self.base_path / "daily",
            "minute": self.base_path / "minute",
            "fundamental": self.base_path / "fundamental",
            "metadata": self.base_path / "metadata",
        }

        for path in self.paths.values():
            path.mkdir(parents=True, exist_ok=True)

        self.validator = DataValidator()
        logger.info(f"数据存储器初始化完成，基础路径: {self.base_path}")

    def standardize_market_data(self, raw_data: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """
        将原始数据转换为标准格式

        Args:
            raw_data: 原始数据
            symbol: 股票代码

        Returns:
            标准格式的DataFrame
        """
        try:
            # 复制数据避免修改原始数据
            data = raw_data.copy()

            # 确保时间索引
            if "time" in data.columns:
                time_series = data["time"]
                if pd.api.types.is_numeric_dtype(time_series):
                    data["datetime"] = (
                        pd.to_datetime(time_series, unit="ms", utc=True)
                        .dt.tz_convert("Asia/Shanghai")
                        .dt.tz_localize(None)
                    )
                else:
                    data["datetime"] = pd.to_datetime(time_series)
                data.set_index("datetime", inplace=True)
                data.drop("time", axis=1, inplace=True)
            elif not isinstance(data.index, pd.DatetimeIndex):
                data.index = pd.to_datetime(data.index)

            # 标准字段映射
            column_mapping = {
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
                "amount": "amount",
                "turnover": "amount",  # QMT字段映射
                "lastPrice": "close",  # QMT字段映射
                "preClose": "pre_close",
                "upperLimit": "high_limit",
                "lowerLimit": "low_limit",
            }

            # 重命名列
            for old_col, new_col in column_mapping.items():
                if old_col in data.columns and old_col != new_col:
                    data.rename(columns={old_col: new_col}, inplace=True)

            # 确保必需字段存在
            required_fields = ["open", "high", "low", "close", "volume"]
            missing_fields = [field for field in required_fields if field not in data.columns]

            if missing_fields:
                logger.warning(f"{symbol} 缺少必需字段: {missing_fields}")
                # 如果缺少amount字段，尝试计算
                if "amount" not in data.columns and "volume" in data.columns:
                    data["amount"] = data["volume"] * data["close"]

            # 数据类型转换
            numeric_columns = [
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "pre_close",
                "high_limit",
                "low_limit",
            ]
            for col in numeric_columns:
                if col in data.columns:
                    data[col] = pd.to_numeric(data[col], errors="coerce")

            # 数据质量检查
            self.validator.validate_market_data(data, symbol)

            return data

        except Exception as e:
            logger.error(f"数据标准化失败 {symbol}: {e}")
            raise

    def save_market_data(
        self,
        data: Union[Dict[str, pd.DataFrame], pd.DataFrame],
        symbol: Optional[str] = None,
        data_type: str = "minute",
        format: str = "parquet",
    ) -> None:
        """
        保存市场数据

        Args:
            data: 市场数据，可以是单个DataFrame或字典
            symbol: 股票代码（当data为DataFrame时必需）
            data_type: 数据类型 ('minute', 'daily', 'fundamental')
            format: 存储格式 ('parquet', 'csv', 'hdf5')
        """
        if isinstance(data, pd.DataFrame):
            if not symbol:
                raise ValueError("当data为DataFrame时，必须提供symbol参数")
            data = {symbol: data}

        for sym, df in data.items():
            try:
                # 标准化数据
                standardized_data = self.standardize_market_data(df, sym)

                # 生成文件路径
                file_path = self._generate_file_path(sym, data_type, format)

                # 保存数据
                self._save_to_file(standardized_data, file_path, format)

                # 保存元数据
                self._save_metadata(sym, data_type, standardized_data, file_path)

                logger.info(f"保存成功: {sym} -> {file_path}")

            except Exception as e:
                logger.error(f"保存失败 {sym}: {e}")
                raise

    def load_data(
        self,
        symbol: str,
        data_type: str = "minute",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """
        加载数据

        Args:
            symbol: 股票代码
            data_type: 数据类型
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            数据DataFrame
        """
        try:
            # 查找匹配的文件
            data_dir = self.paths[data_type]
            pattern = f"{symbol}_*.parquet"
            files = list(data_dir.glob(pattern))

            if not files:
                # 尝试其他格式
                for ext in ["csv", "h5"]:
                    pattern = f"{symbol}_*.{ext}"
                    files = list(data_dir.glob(pattern))
                    if files:
                        break

            if not files:
                logger.warning(f"未找到 {symbol} 的 {data_type} 数据")
                return None

            # 加载最新文件
            latest_file = max(files, key=lambda x: x.stat().st_mtime)

            if latest_file.suffix == ".parquet":
                data = pd.read_parquet(latest_file)
            elif latest_file.suffix == ".csv":
                data = pd.read_csv(latest_file, index_col=0, parse_dates=True)
            elif latest_file.suffix == ".h5":
                data = pd.read_hdf(latest_file, key="data")
            else:
                raise ValueError(f"不支持的文件格式: {latest_file.suffix}")

            # 日期过滤
            if start_date or end_date:
                if start_date:
                    data = data[data.index >= pd.to_datetime(start_date)]
                if end_date:
                    data = data[data.index <= pd.to_datetime(end_date)]

            logger.info(f"加载数据成功: {symbol} from {latest_file}")
            return data

        except Exception as e:
            logger.error(f"加载数据失败 {symbol}: {e}")
            return None

    def _generate_file_path(self, symbol: str, data_type: str, format: str) -> Path:
        """
        生成文件路径

        Args:
            symbol: 股票代码
            data_type: 数据类型
            format: 文件格式

        Returns:
            文件路径
        """
        today = date.today().strftime("%Y%m%d")
        filename = f"{symbol}_{today}.{format}"
        return self.paths[data_type] / filename

    def _save_to_file(self, data: pd.DataFrame, file_path: Path, format: str) -> None:
        """
        保存数据到文件

        Args:
            data: 数据
            file_path: 文件路径
            format: 文件格式
        """
        if format == "parquet":
            data.to_parquet(file_path, engine="pyarrow")
        elif format == "csv":
            data.to_csv(file_path, encoding="utf-8")
        elif format == "hdf5":
            data.to_hdf(file_path, key="data", mode="w")
        else:
            raise ValueError(f"不支持的文件格式: {format}")

    def _save_metadata(
        self, symbol: str, data_type: str, data: pd.DataFrame, file_path: Path
    ) -> None:
        """
        保存元数据

        Args:
            symbol: 股票代码
            data_type: 数据类型
            data: 数据
            file_path: 数据文件路径
        """
        metadata = {
            "symbol": symbol,
            "data_type": data_type,
            "file_path": str(file_path),
            "columns": list(data.columns),
            "data_shape": data.shape,
            "date_range": {
                "start": data.index.min().strftime("%Y-%m-%d %H:%M:%S"),
                "end": data.index.max().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "file_size_mb": file_path.stat().st_size / (1024 * 1024) if file_path.exists() else 0,
        }

        metadata_file = self.paths["metadata"] / f"{symbol}_{data_type}_metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
