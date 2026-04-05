#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
日盈亏统计计算模块
"""

import time
import threading
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_

from src.config import settings
from src.infrastructure.db import OrderRecord, SessionLocal
from src.logger_config import configured_logger as logger
from src.data_manager.stock_info import get_stock_display_name
from src.trading.trading_costs import TradingFeeSchedule, analyze_filled_trades


class DailyPnLCalculator:
    """日盈亏统计计算器"""

    def __init__(self):
        self.today = date.today()
        self.fee_schedule = TradingFeeSchedule.from_settings(settings)
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
            if (
                cached_summary is not None
                and (time.time() - cached_at) < self._summary_cache_ttl_seconds
            ):
                return dict(cached_summary)

        logger.info(f"计算 {target_date} 的交易汇总")

        with self._cache_lock:
            cached_summary = self._summary_cache.get(target_date)
            cached_at = self._summary_cache_time.get(target_date, 0.0)
            if (
                cached_summary is not None
                and (time.time() - cached_at) < self._summary_cache_ttl_seconds
            ):
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
        analytics = analyze_filled_trades(orders, self.fee_schedule)
        trades = analytics["trades"]
        per_stock = analytics["per_stock"]

        # 基础统计
        total_orders = len(orders)
        buy_orders = [trade for trade in trades if trade["direction"] == "BUY"]
        sell_orders = [trade for trade in trades if trade["direction"] == "SELL"]

        # 成交金额统计
        buy_amount = sum(float(trade["notional"]) for trade in buy_orders)
        sell_amount = sum(float(trade["notional"]) for trade in sell_orders)
        total_amount = buy_amount + sell_amount

        # 成交量统计
        buy_volume = sum(int(trade["filled_volume"]) for trade in buy_orders)
        sell_volume = sum(int(trade["filled_volume"]) for trade in sell_orders)
        total_volume = buy_volume + sell_volume

        # 股票分类统计
        stock_stats = self._calculate_stock_stats(orders, per_stock)

        # 时间段统计
        time_stats = self._calculate_time_stats(trades)

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
            "performance": self._estimate_performance(analytics),
        }

    def _calculate_stock_stats(
        self,
        orders: List[OrderRecord],
        per_stock: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
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
                    "buy_fees": 0.0,
                    "sell_fees": 0.0,
                    "total_fees": 0.0,
                    "estimated_realized_pnl": 0.0,
                    "gross_realized_pnl": 0.0,
                    "matched_volume": 0,
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
            fee_stats = per_stock.get(stock["stock_code"], {})
            stock["total_amount"] = round(stock["buy_amount"] + stock["sell_amount"], 2)
            stock["buy_amount"] = round(stock["buy_amount"], 2)
            stock["sell_amount"] = round(stock["sell_amount"], 2)
            stock["net_volume"] = stock["buy_volume"] - stock["sell_volume"]
            stock["buy_fees"] = round(float(fee_stats.get("buy_fees", 0.0)), 2)
            stock["sell_fees"] = round(float(fee_stats.get("sell_fees", 0.0)), 2)
            stock["total_fees"] = round(float(fee_stats.get("total_fees", 0.0)), 2)
            stock["gross_realized_pnl"] = round(float(fee_stats.get("gross_realized_pnl", 0.0)), 2)
            stock["estimated_realized_pnl"] = round(
                float(fee_stats.get("net_realized_pnl", 0.0)),
                2,
            )
            stock["matched_volume"] = int(fee_stats.get("matched_volume", 0) or 0)

        return sorted(stock_list, key=lambda x: x["total_amount"], reverse=True)

    def _calculate_time_stats(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """按时间段统计"""
        morning_orders: List[Dict[str, Any]] = []  # 9:30-11:30
        afternoon_orders: List[Dict[str, Any]] = []  # 13:00-15:00

        for trade in trades:
            filled_time = trade.get("filled_time")
            if not filled_time:
                continue

            hour = filled_time.hour
            minute = filled_time.minute
            time_minutes = hour * 60 + minute

            # 9:30-11:30 (570-690分钟)
            if 570 <= time_minutes <= 690:
                morning_orders.append(trade)
            # 13:00-15:00 (780-900分钟)
            elif 780 <= time_minutes <= 900:
                afternoon_orders.append(trade)

        return {
            "morning": {
                "orders_count": len(morning_orders),
                "amount": round(sum(float(trade["notional"]) for trade in morning_orders), 2),
                "volume": sum(int(trade["filled_volume"]) for trade in morning_orders),
                "trading_cost_estimate": round(
                    sum(float(trade["total_fee"]) for trade in morning_orders),
                    2,
                ),
            },
            "afternoon": {
                "orders_count": len(afternoon_orders),
                "amount": round(sum(float(trade["notional"]) for trade in afternoon_orders), 2),
                "volume": sum(int(trade["filled_volume"]) for trade in afternoon_orders),
                "trading_cost_estimate": round(
                    sum(float(trade["total_fee"]) for trade in afternoon_orders),
                    2,
                ),
            },
        }

    def _estimate_performance(self, analytics: Dict[str, Any]) -> Dict[str, Any]:
        """估算交易表现（基于成交配对和统一费率模型）"""
        roundtrips = analytics["roundtrips"]
        trades = analytics["trades"]
        gross_realized_pnl = sum(float(item["gross_pnl"]) for item in roundtrips)
        net_realized_pnl = sum(float(item["net_pnl"]) for item in roundtrips)
        trading_cost = sum(float(item["total_fee"]) for item in trades)

        performance = {
            "estimated_realized_pnl": round(net_realized_pnl, 2),
            "gross_realized_pnl": round(gross_realized_pnl, 2),
            "trading_cost_estimate": round(trading_cost, 2),
            "roundtrip_count": len(roundtrips),
            "matched_volume": sum(int(item["volume"]) for item in roundtrips),
            "note": "已按配置费率估算已配对成交的净盈亏；未闭环仓位不计入已实现盈亏。",
        }
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
                "morning": {
                    "orders_count": 0,
                    "amount": 0.0,
                    "volume": 0,
                    "trading_cost_estimate": 0.0,
                },
                "afternoon": {
                    "orders_count": 0,
                    "amount": 0.0,
                    "volume": 0,
                    "trading_cost_estimate": 0.0,
                },
            },
            "performance": {
                "estimated_realized_pnl": 0.0,
                "gross_realized_pnl": 0.0,
                "trading_cost_estimate": 0.0,
                "roundtrip_count": 0,
                "matched_volume": 0,
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
