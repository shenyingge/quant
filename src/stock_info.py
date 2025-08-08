#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""股票信息查询模块"""

import time
import threading
from typing import Dict, Optional
from src.logger_config import configured_logger as logger

class StockInfoCache:
    """股票信息缓存"""
    
    def __init__(self):
        self._cache = {}  # {stock_code: {'name': str, 'timestamp': float}}
        self._lock = threading.Lock()
        self._cache_timeout = 3600  # 缓存1小时
        
        # 预设一些常见股票的名称
        self._preset_names = {
            '000001': '平安银行',
            '000002': '万科A',
            '000858': '五粮液',
            '000876': '新希望',
            '002415': '海康威视',
            '002594': '比亚迪',
            '600000': '浦发银行',
            '600036': '招商银行',
            '600519': '贵州茅台',
            '600887': '伊利股份',
            '000858': '五粮液',
            '002230': '科大讯飞',
            '300059': '东方财富',
            '300750': '宁德时代'
        }
    
    def get_stock_name(self, stock_code: str) -> str:
        """获取股票名称"""
        if not stock_code:
            return "未知股票"
        
        # 清理股票代码
        stock_code = str(stock_code).strip()
        
        with self._lock:
            # 检查缓存
            if stock_code in self._cache:
                cache_item = self._cache[stock_code]
                if time.time() - cache_item['timestamp'] < self._cache_timeout:
                    return cache_item['name']
            
            # 尝试从预设名称获取
            if stock_code in self._preset_names:
                name = self._preset_names[stock_code]
                self._cache[stock_code] = {
                    'name': name,
                    'timestamp': time.time()
                }
                return name
            
            # 尝试通过QMT查询股票信息（如果可用）
            name = self._query_stock_name_from_qmt(stock_code)
            if name:
                self._cache[stock_code] = {
                    'name': name,
                    'timestamp': time.time()
                }
                return name
            
            # 如果都失败了，返回默认格式
            default_name = f"股票{stock_code}"
            self._cache[stock_code] = {
                'name': default_name,
                'timestamp': time.time()
            }
            return default_name
    
    def _query_stock_name_from_qmt(self, stock_code: str) -> Optional[str]:
        """尝试从QMT查询股票名称"""
        try:
            # 这里可以集成QMT的股票信息查询API
            # 由于QMT API可能不稳定，我们先用预设数据
            return None
        except Exception as e:
            logger.debug(f"从QMT查询股票名称失败 {stock_code}: {e}")
            return None
    
    def get_stock_display_name(self, stock_code: str) -> str:
        """获取股票显示名称（代码+名称）"""
        name = self.get_stock_name(stock_code)
        if name and name != f"股票{stock_code}":
            return f"{stock_code}({name})"
        return stock_code
    
    def update_stock_name(self, stock_code: str, name: str):
        """手动更新股票名称"""
        with self._lock:
            self._cache[stock_code] = {
                'name': name,
                'timestamp': time.time()
            }
            logger.info(f"更新股票名称: {stock_code} -> {name}")
    
    def clear_cache(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            logger.info("股票名称缓存已清空")
    
    def get_cache_stats(self) -> Dict[str, any]:
        """获取缓存统计信息"""
        with self._lock:
            current_time = time.time()
            valid_count = sum(
                1 for item in self._cache.values()
                if current_time - item['timestamp'] < self._cache_timeout
            )
            
            return {
                'total_cached': len(self._cache),
                'valid_cached': valid_count,
                'expired_cached': len(self._cache) - valid_count,
                'cache_timeout': self._cache_timeout,
                'preset_count': len(self._preset_names)
            }

# 全局股票信息缓存实例
stock_info_cache = StockInfoCache()

def get_stock_name(stock_code: str) -> str:
    """获取股票名称的便捷函数"""
    return stock_info_cache.get_stock_name(stock_code)

def get_stock_display_name(stock_code: str) -> str:
    """获取股票显示名称的便捷函数"""
    return stock_info_cache.get_stock_display_name(stock_code)