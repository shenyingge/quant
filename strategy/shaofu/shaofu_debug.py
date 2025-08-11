# 少妇战法策略 - 调试版本
# 简化版本用于测试信号生成

import numpy as np
import pandas as pd
from jqdata import *


# ================= 0. 初始化 =================
def initialize(context):
    set_benchmark("000905.XSHG")
    set_option("use_real_price", True)
    set_option("avoid_future_data", True)
    set_slippage(PriceRelatedSlippage(0.003))
    set_order_cost(
        OrderCost(
            open_tax=0,
            close_tax=0.0005,
            open_commission=0.0002,
            close_commission=0.0002,
            close_today_commission=0,
            min_commission=5,
        ),
        type="stock",
    )
    log.set_level("order", "info")  # 显示更多日志

    # 简化的策略参数
    g.VOL_RATIO = 1.2  # 降低首阳放量要求
    g.SHRINK = 1.0  # 取消缩量要求
    g.TAKE1 = 1.05  # 提高止盈位
    g.SL = 0.95  # 降低止损位
    g.MAX_HOLD_DAYS = 10  # 延长持有期
    g.MAX_POS = 0.8  # 总仓位上限
    g.POS_PER_STOCK = 0.25  # 单票目标仓位
    g.MAX_STOCKS = 3  # 减少最大持股数量

    # 状态容器
    g.pool = []
    g.positions_state = {}

    log.info("少妇战法策略启动 - 调试版本")

    # 调度任务
    run_daily(select_simple_universe, time="08:55")
    run_daily(simple_buy_check, time="09:35")
    run_daily(simple_sell_check, time="14:50")


# ================= 1. 简化选股 =================
def select_simple_universe(context):
    """简化选股逻辑"""
    log.info("开始简化选股...")

    try:
        # 直接获取活跃股票池
        stocks = [
            "000001.XSHE",
            "000002.XSHE",
            "600000.XSHG",
            "600036.XSHG",
            "000858.XSHE",
            "002415.XSHE",
            "600519.XSHG",
            "000876.XSHE",
            "002594.XSHE",
            "600276.XSHG",
            "000063.XSHE",
            "002304.XSHE",
            "600887.XSHG",
            "002230.XSHE",
            "000100.XSHE",
            "600585.XSHG",
        ]

        # 过滤停牌股票
        current_data = get_current_data()
        valid_stocks = []

        for stock in stocks:
            try:
                info = current_data[stock]
                if not info.paused and not info.is_st:
                    valid_stocks.append(stock)
            except:
                continue

        g.pool = valid_stocks[:10]  # 取前10只
        log.info(f"简化选股完成，候选池: {len(g.pool)}只 - {g.pool}")

    except Exception as e:
        log.error(f"选股失败: {e}")
        g.pool = []


# ================= 2. 简化买入检查 =================
def simple_buy_check(context):
    """简化买入检查"""
    log.info("开始简化买入检查...")

    if not g.pool:
        log.info("候选池为空")
        return

    try:
        buy_count = 0
        for stock in g.pool:
            if buy_count >= g.MAX_STOCKS:
                break

            # 检查是否已持有
            if context.portfolio.positions[stock].total_amount > 0:
                continue

            # 简化条件：获取价格数据
            df = get_price(
                stock,
                count=5,
                end_date=context.current_dt,
                fields=["open", "high", "low", "close", "volume"],
                frequency="daily",
            )

            if len(df) < 2:
                continue

            yesterday = df.iloc[-2]
            today = df.iloc[-1]

            # 极简化的买入条件：昨日阳线且今日价格上涨
            if (
                yesterday.close > yesterday.open and today.close > yesterday.high * 0.98
            ):  # 接近或突破前高

                # 执行买入
                target_value = context.portfolio.total_value * g.POS_PER_STOCK
                order_obj = order_target_value(stock, target_value)

                if order_obj and order_obj.filled > 0:
                    log.info(f"买入: {stock} 数量:{order_obj.filled} 价格:{order_obj.price:.2f}")

                    g.positions_state[stock] = {
                        "buy_date": context.current_dt.date(),
                        "buy_price": today.close,
                        "hold_days": 0,
                    }
                    buy_count += 1

        if buy_count > 0:
            log.info(f"本次买入执行: {buy_count}只股票")
        else:
            log.info("无买入执行")

    except Exception as e:
        log.error(f"买入检查失败: {e}")


# ================= 3. 简化卖出检查 =================
def simple_sell_check(context):
    """简化卖出检查"""
    log.info("开始简化卖出检查...")

    current_positions = [
        pos.security for pos in context.portfolio.positions.values() if pos.total_amount > 0
    ]

    if not current_positions:
        log.info("当前无持仓")
        return

    try:
        sell_count = 0
        for stock in current_positions:
            if stock not in g.positions_state:
                continue

            # 更新持有天数
            g.positions_state[stock]["hold_days"] += 1
            position = context.portfolio.positions[stock]
            profit_rate = (position.price / position.avg_cost - 1) * 100

            # 简化卖出条件
            should_sell = False
            sell_reason = ""

            # 止盈：盈利超过5%
            if profit_rate >= 5:
                should_sell = True
                sell_reason = "止盈"
            # 止损：亏损超过5%
            elif profit_rate <= -5:
                should_sell = True
                sell_reason = "止损"
            # 时限：持有超过10天
            elif g.positions_state[stock]["hold_days"] >= g.MAX_HOLD_DAYS:
                should_sell = True
                sell_reason = "时限"

            if should_sell:
                order_obj = order_target_value(stock, 0)
                if order_obj and order_obj.filled > 0:
                    log.info(
                        f"卖出: {stock} 数量:{order_obj.filled} 价格:{order_obj.price:.2f} "
                        f"原因:{sell_reason} 收益:{profit_rate:.2f}%"
                    )

                    del g.positions_state[stock]
                    sell_count += 1

        if sell_count > 0:
            log.info(f"本次卖出执行: {sell_count}只股票")

        # 打印持仓信息
        if current_positions:
            log.info("===== 当前持仓 =====")
            for pos in context.portfolio.positions.values():
                if pos.total_amount > 0:
                    profit_rate = (pos.price / pos.avg_cost - 1) * 100
                    hold_days = g.positions_state.get(pos.security, {}).get("hold_days", 0)
                    log.info(
                        f"{pos.security} [{hold_days}天] 成本:{pos.avg_cost:.2f} "
                        f"现价:{pos.price:.2f} 收益:{profit_rate:.2f}%"
                    )

    except Exception as e:
        log.error(f"卖出检查失败: {e}")
