"""
数据管理模块
提供市场数据的下载、存储、管理功能
"""

from .downloader import DataDownloader
from .storage import MarketDataStorage
from .universe import StockUniverse
from .validator import DataValidator

__all__ = ["MarketDataStorage", "DataDownloader", "DataValidator", "StockUniverse"]

__version__ = "1.0.0"
