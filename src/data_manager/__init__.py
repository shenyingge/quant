"""
数据管理模块
提供市场数据的下载、存储、管理功能
"""

__all__ = ["MarketDataStorage", "DataDownloader", "DataValidator", "StockUniverse"]

__version__ = "1.0.0"


def __getattr__(name: str):
    if name == "DataDownloader":
        from .downloader import DataDownloader

        return DataDownloader
    if name == "MarketDataStorage":
        from .storage import MarketDataStorage

        return MarketDataStorage
    if name == "StockUniverse":
        from .universe import StockUniverse

        return StockUniverse
    if name == "DataValidator":
        from .validator import DataValidator

        return DataValidator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
