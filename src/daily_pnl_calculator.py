#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
日盈亏统计计算模块
"""

import time
import threading
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from src.config import settings
from src.database import OrderRecord, SessionLocal, TradingSignal
from src.logger_config import configured_logger as logger
from src.stock_info import get_stock_display_name


class DailyPnLCalculator:
    """日盈亏统计计算器"""

    def __init__(self):
        self.today = date.today()
        self._cache_lock = threading.Lock()
        self._summary_cache: Dict[date, Dict[str, Any]] = {}
        self._summary_cache_time: Dict[date, float] = {}
        self._summary_cache_ttl_seconds = 10

    def calculate_daily_summary(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """计算指定日期的交易汇总"""
        if target_date is None:
            target_date = self.today

        with self._cache_lock:
            cached_summary = self._summary_cache.get(target_date)
            cached_at = self._summary_cache_time.get(target_date, 0.0)
            if cached_summary is not None and (time.time() - cached_at) < self._summary_cache_ttl_seconds:
                return dict(cached_summary)

        logger.info(f"计算 {target_date} 的交易汇总")

        with self._cache_lock:
            cached_summary = self._summary_cache.get(target_date)
            cached_at = self._summary_cache_time.get(target_date, 0.0)
            if cached_summary is not None and (time.time() - cached_at) < self._summary_cache_ttl_seconds:
                return dict(cached_summary)

            db = SessionLocal()
            try:
                # 查询当日所有已成交的订单
                start_time = datetime.combine(target_date, datetime.min.time())
                end_time = datetime.combine(target_date, datetime.max.time())

                filled_orders = (
                    db.query(OrderRecord)
                    .filter(
                        and_(
                            OrderRecord.filled_time >= start_time,
                            OrderRecord.filled_time <= end_time,
                            OrderRecord.filled_volume > 0,
                            OrderRecord.filled_price > 0,
                        )
                    )
                    .all()
                )

                if not filled_orders:
                    summary = self._create_empty_summary(target_date)
                else:
                    # 统计数据
                    summary = self._calculate_trading_summary(filled_orders, target_date)

                self._summary_cache[target_date] = dict(summary)
                self._summary_cache_time[target_date] = time.time()
                return dict(summary)

            except Exception as e:
                logger.error(f"计算日交易汇总时发生错误: {e}")
                summary = self._create_empty_summary(target_date)
                self._summary_cache[target_date] = dict(summary)
                self._summary_cache_time[target_date] = time.time()
                return dict(summary)
            finally:
                db.close()

    def _calculate_trading_summary(
        self, orders: List[OrderRecord], target_date: date
    ) -> Dict[str, Any]:
        """计算交易汇总数据"""

        # 基础统计
        total_orders = len(orders)
        buy_orders = [o for o in orders if o.direction.upper() == "BUY"]
        sell_orders = [o for o in orders if o.direction.upper() == "SELL"]

        # 成交金额统计
        buy_amount = sum(float(o.filled_volume * o.filled_price) for o in buy_orders)
        sell_amount = sum(float(o.filled_volume * o.filled_price) for o in sell_orders)
        total_amount = buy_amount + sell_amount

        # 成交量统计
        buy_volume = sum(o.filled_volume for o in buy_orders)
        sell_volume = sum(o.filled_volume for o in sell_orders)
        total_volume = buy_volume + sell_volume

        # 股票分类统计
        stock_stats = self._calculate_stock_stats(orders)

        # 时间段统计
        time_stats = self._calculate_time_stats(orders)

        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "date_display": target_date.strftime("%Y年%m月%d日"),
            "summary": {
                "total_orders": total_orders,
                "buy_orders": len(buy_orders),
                "sell_orders": len(sell_orders),
                "total_amount": round(total_amount, 2),
                "buy_amount": round(buy_amount, 2),
                "sell_amount": round(sell_amount, 2),
                "total_volume": total_volume,
                "buy_volume": buy_volume,
                "sell_volume": sell_volume,
                "avg_price": round(total_amount / total_volume, 2) if total_volume > 0 else 0,
            },
            "stock_breakdown": stock_stats,
            "time_breakdown": time_stats,
            "performance": self._estimate_performance(buy_orders, sell_orders),
        }

    def _calculate_stock_stats(self, orders: List[OrderRecord]) -> List[Dict[str, Any]]:
        """按股票分类统计"""
        stock_data = {}

        for order in orders:
            code = order.stock_code
            if code not in stock_data:
                stock_data[code] = {
                    "stock_code": code,
                    "stock_display": get_stock_display_name(code),
                    "buy_volume": 0,
                    "sell_volume": 0,
                    "buy_amount": 0.0,
                    "sell_amount": 0.0,
                    "orders_count": 0,
                }

            stats = stock_data[code]
            stats["orders_count"] += 1
            amount = float(order.filled_volume * order.filled_price)

            if order.direction.upper() == "BUY":
                stats["buy_volume"] += order.filled_volume
                stats["buy_amount"] += amount
            else:
                stats["sell_volume"] += order.filled_volume
                stats["sell_amount"] += amount

        # 转换为列表并按成交金额排序
        stock_list = list(stock_data.values())
        for stock in stock_list:
            stock["total_amount"] = round(stock["buy_amount"] + stock["sell_amount"], 2)
            stock["buy_amount"] = round(stock["buy_amount"], 2)
            stock["sell_amount"] = round(stock["sell_amount"], 2)
            stock["net_volume"] = stock["buy_volume"] - stock["sell_volume"]

        return sorted(stock_list, key=lambda x: x["total_amount"], reverse=True)

    def _calculate_time_stats(self, orders: List[OrderRecord]) -> Dict[str, Any]:
        """按时间段统计"""
        morning_orders = []  # 9:30-11:30
        afternoon_orders = []  # 13:00-15:00

        for order in orders:
            if not order.filled_time:
                continue

            hour = order.filled_time.hour
            minute = order.filled_time.minute
            time_minutes = hour * 60 + minute

            # 9:30-11:30 (570-690分钟)
            if 570 <= time_minutes <= 690:
                morning_orders.append(order)
            # 13:00-15:00 (780-900分钟)
            elif 780 <= time_minutes <= 900:
                afternoon_orders.append(order)

        return {
            "morning": {
                "orders_count": len(morning_orders),
                "amount": round(
                    sum(float(o.filled_volume * o.filled_price) for o in morning_orders), 2
                ),
                "volume": sum(o.filled_volume for o in morning_orders),
            },
            "afternoon": {
                "orders_count": len(afternoon_orders),
                "amount": round(
                    sum(float(o.filled_volume * o.filled_price) for o in afternoon_orders), 2
                ),
                "volume": sum(o.filled_volume for o in afternoon_orders),
            },
        }

    def _estimate_performance(
        self, buy_orders: List[OrderRecord], sell_orders: List[OrderRecord]
    ) -> Dict[str, Any]:
        """估算交易表现（简单估算，实际盈亏需要考虑持仓成本）"""

        # 如果有买卖配对，可以估算部分盈亏
        performance = {
            "estimated_realized_pnl": 0.0,
            "trading_cost_estimate": 0.0,
            "note": "此为简单估算，实际盈亏需要考虑持仓成本和手续费",
        }

        # 估算交易成本 (假设手续费率0.03%)
        total_amount = sum(
            float(o.filled_volume * o.filled_price) for o in buy_orders + sell_orders
        )
        estimated_commission = total_amount * 0.0003
        performance["trading_cost_estimate"] = round(estimated_commission, 2)

        # 如果同一只股票有买有卖，可以做简单的盈亏估算
        stock_trades = {}

        # 收集买卖记录
        for order in buy_orders:
            code = order.stock_code
            if code not in stock_trades:
                stock_trades[code] = {"buys": [], "sells": []}
            stock_trades[code]["buys"].append(order)

        for order in sell_orders:
            code = order.stock_code
            if code not in stock_trades:
                stock_trades[code] = {"buys": [], "sells": []}
            stock_trades[code]["sells"].append(order)

        # 简单估算已实现盈亏
        realized_pnl = 0.0
        for code, trades in stock_trades.items():
            if trades["buys"] and trades["sells"]:
                # 简单按FIFO匹配
                avg_buy_price = sum(
                    float(o.filled_price * o.filled_volume) for o in trades["buys"]
                ) / sum(o.filled_volume for o in trades["buys"])
                avg_sell_price = sum(
                    float(o.filled_price * o.filled_volume) for o in trades["sells"]
                ) / sum(o.filled_volume for o in trades["sells"])

                # 取较小的成交量作为配对量
                matched_volume = min(
                    sum(o.filled_volume for o in trades["buys"]),
                    sum(o.filled_volume for o in trades["sells"]),
                )

                stock_pnl = (avg_sell_price - avg_buy_price) * matched_volume
                realized_pnl += stock_pnl

        performance["estimated_realized_pnl"] = round(realized_pnl, 2)

        return performance

    def _create_empty_summary(self, target_date: date) -> Dict[str, Any]:
        """创建空的汇总数据"""
        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "date_display": target_date.strftime("%Y年%m月%d日"),
            "summary": {
                "total_orders": 0,
                "buy_orders": 0,
                "sell_orders": 0,
                "total_amount": 0.0,
                "buy_amount": 0.0,
                "sell_amount": 0.0,
                "total_volume": 0,
                "buy_volume": 0,
                "sell_volume": 0,
                "avg_price": 0.0,
            },
            "stock_breakdown": [],
            "time_breakdown": {
                "morning": {"orders_count": 0, "amount": 0.0, "volume": 0},
                "afternoon": {"orders_count": 0, "amount": 0.0, "volume": 0},
            },
            "performance": {
                "estimated_realized_pnl": 0.0,
                "trading_cost_estimate": 0.0,
                "note": "当日无成交记录",
            },
        }

    def get_recent_trading_days_summary(self, days: int = 5) -> List[Dict[str, Any]]:
        """获取最近几个交易日的汇总"""
        summaries = []
        current_date = self.today

        for i in range(days):
            summary = self.calculate_daily_summary(current_date)
            summaries.append(summary)

            # 往前推一天
            current_date = date(current_date.year, current_date.month, current_date.day - 1)

        return summaries


# 全局实例
daily_pnl_calculator = DailyPnLCalculator()


def calculate_daily_summary(target_date: Optional[date] = None) -> Dict[str, Any]:
    """计算日交易汇总的便捷函数"""
    return daily_pnl_calculator.calculate_daily_summary(target_date)
