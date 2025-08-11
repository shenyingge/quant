# VIP隔夜板+早盘确认策略 - 聚宽版本
# 基于集合竞价封单分析和开盘后主力确认的涨停策略
# 实现时间：2025-08-10

from datetime import datetime, time

import numpy as np
import pandas as pd
from jqdata import *


# ================= 0. 初始化 =================
def initialize(context):
    set_benchmark("000905.XSHG")
    set_option("use_real_price", True)
    set_option("avoid_future_data", True)
    set_slippage(PriceRelatedSlippage(0.002))
    set_order_cost(
        OrderCost(
            open_tax=0,
            close_tax=0.0005,
            open_commission=0.0001,
            close_commission=0.0001,
            close_today_commission=0,
            min_commission=5,
        ),
        type="stock",
    )
    log.set_level("order", "error")
    log.set_level("system", "debug")

    # ================= 策略参数 =================
    g.MIN_AUCTION_AMOUNT = 100000000  # 集合竞价最小封单金额(1亿)
    g.MIN_TURNOVER_RATE = 0.015  # 最小换手率1.5%
    g.MAX_POSITIONS = 3  # 最大持股数量
    g.POSITION_SIZE = 0.3  # 单股仓位
    g.MAX_TOTAL_POSITION = 0.9  # 总仓位上限
    g.STOP_LOSS_RATE = 0.12  # 止损幅度12%
    g.TAKE_PROFIT_RATE = 0.08  # 止盈幅度8%
    g.MAX_HOLD_DAYS = 3  # 最长持有天数

    # ================= 状态变量 =================
    g.candidate_stocks = []  # 候选股票池
    g.position_info = {}  # 持仓信息
    g.auction_data = {}  # 集合竞价数据
    g.today_bought = []  # 今日买入股票

    log.info("VIP隔夜板策略启动")

    # ================= 调度任务 =================
    run_daily(pre_market_analysis, time="09:20")  # 集合竞价分析
    run_daily(auction_final_check, time="09:25")  # 竞价最终检查
    run_daily(opening_confirmation, time="09:32")  # 开盘确认买入
    run_daily(monitor_positions, time="14:30")  # 持仓监控
    run_daily(end_of_day_summary, time="15:10")  # 日终总结


# ================= 1. 盘前分析：候选股票筛选 =================
def pre_market_analysis(context):
    """9:20 集合竞价阶段分析"""
    log.info("开始集合竞价分析...")

    try:
        # 获取基础股票池
        stocks = get_stock_pool(context)
        if not stocks:
            log.info("股票池为空，跳过分析")
            return

        log.info(f"分析股票数量: {len(stocks)}")

        # 分析集合竞价数据
        g.candidate_stocks = []
        g.auction_data = {}

        current_data = get_current_data()

        for stock in stocks:
            try:
                data = current_data[stock]

                # 基础过滤
                if data.paused or data.is_st or "退" in data.name or "*" in data.name:
                    continue

                # 模拟集合竞价封单分析
                auction_info = analyze_auction_data(stock, context)

                if auction_info and auction_info["is_vip_candidate"]:
                    g.candidate_stocks.append(stock)
                    g.auction_data[stock] = auction_info

                    log.info(
                        f"发现VIP候选: {data.name}({stock}) "
                        f"预估封单: {auction_info['estimated_amount']/100000000:.1f}亿 "
                        f"涨停价: {auction_info['limit_up_price']:.2f}"
                    )

            except Exception as e:
                log.debug(f"分析 {stock} 失败: {e}")
                continue

        log.info(f"集合竞价分析完成，发现{len(g.candidate_stocks)}只VIP候选股")

    except Exception as e:
        log.error(f"集合竞价分析失败: {e}")


def get_stock_pool(context):
    """获取基础股票池"""
    try:
        # 获取全A股主板和中小板（排除创业板科创板）
        all_stocks = list(get_all_securities(["stock"]).index)

        # 基础过滤：排除新股、ST、北交所等
        stocks = []
        current_data = get_current_data()

        for stock in all_stocks:
            try:
                if (
                    stock.startswith(("688", "300", "8", "4"))  # 科创板、创业板、北交所
                    or (context.previous_date - get_security_info(stock).start_date).days < 60
                ):  # 新股
                    continue

                info = current_data[stock]
                if not (info.paused or info.is_st):
                    stocks.append(stock)

            except:
                continue

        # 限制分析数量（性能考虑）
        return stocks[:800]

    except Exception as e:
        log.error(f"获取股票池失败: {e}")
        return []


def analyze_auction_data(stock, context):
    """分析集合竞价数据（模拟实现）"""
    try:
        # 获取历史数据用于计算涨停价
        df = get_price(
            stock,
            count=5,
            end_date=context.previous_date,
            fields=["close", "volume", "money"],
            frequency="daily",
        )

        if df.empty:
            return None

        yesterday_close = df.close.iloc[-1]
        limit_up_price = yesterday_close * 1.1  # 涨停价

        # 获取近期成交金额计算活跃度
        avg_money = df.money.mean()

        # 模拟集合竞价封单分析（实际需要Level-2数据）
        # 这里用启发式规则模拟
        estimated_amount = estimate_auction_amount(stock, avg_money, context)

        # VIP候选条件
        is_vip_candidate = (
            estimated_amount >= g.MIN_AUCTION_AMOUNT  # 封单金额足够大
            and avg_money >= 50000000  # 历史成交活跃
            and yesterday_close >= 10.0  # 价格不能太低
            and not is_consecutive_limit_up(stock, context)  # 非连续涨停
        )

        return {
            "limit_up_price": limit_up_price,
            "estimated_amount": estimated_amount,
            "avg_money": avg_money,
            "is_vip_candidate": is_vip_candidate,
            "yesterday_close": yesterday_close,
        }

    except Exception as e:
        log.debug(f"分析竞价数据失败 {stock}: {e}")
        return None


def estimate_auction_amount(stock, avg_money, context):
    """估算集合竞价封单金额（启发式）"""
    try:
        # 获取板块和概念信息
        stock_info = get_security_info(stock)

        # 基于历史成交金额和市场情绪估算
        base_amount = avg_money * 0.3  # 基础估算

        # 热点板块加成（这里简化处理）
        if any(keyword in stock_info.name for keyword in ["军工", "科技", "新能源", "AI"]):
            base_amount *= 2.0

        # 随机因素模拟市场情绪
        import random

        emotion_factor = random.uniform(0.5, 3.0)

        return base_amount * emotion_factor

    except:
        return avg_money * 0.5


def is_consecutive_limit_up(stock, context):
    """检查是否连续涨停"""
    try:
        df = get_price(
            stock,
            count=3,
            end_date=context.previous_date,
            fields=["close", "high"],
            frequency="daily",
        )
        if len(df) < 2:
            return False

        # 检查昨日是否涨停（简化判断）
        yesterday = df.iloc[-1]
        day_before = df.iloc[-2]

        return abs(yesterday.close / day_before.close - 1.1) < 0.001

    except:
        return False


# ================= 2. 竞价最终确认 =================
def auction_final_check(context):
    """9:25 集合竞价最终确认"""
    log.info("执行竞价最终确认...")

    if not g.candidate_stocks:
        log.info("无候选股票，跳过竞价确认")
        return

    try:
        confirmed_stocks = []

        for stock in g.candidate_stocks:
            auction_info = g.auction_data.get(stock)
            if not auction_info:
                continue

            # 模拟获取集合竞价结果
            final_check = get_auction_result(stock, auction_info, context)

            if final_check["confirmed"]:
                confirmed_stocks.append(stock)
                g.auction_data[stock].update(final_check)

                current_data = get_current_data()
                stock_name = current_data[stock].name

                log.info(
                    f"竞价确认: {stock_name}({stock}) "
                    f"竞价: {final_check['auction_price']:.2f} "
                    f"换手率: {final_check['turnover_rate']:.1%}"
                )

        g.candidate_stocks = confirmed_stocks
        log.info(f"竞价确认完成，剩余{len(g.candidate_stocks)}只候选股")

    except Exception as e:
        log.error(f"竞价确认失败: {e}")


def get_auction_result(stock, auction_info, context):
    """获取集合竞价结果（模拟）"""
    try:
        # 实际应该获取集合竞价的成交价、成交量等数据
        # 这里用昨日数据模拟
        df = get_price(
            stock,
            count=2,
            end_date=context.previous_date,
            fields=["close", "volume", "money"],
            frequency="daily",
        )

        if df.empty:
            return {"confirmed": False}

        yesterday_close = df.close.iloc[-1]
        limit_up_price = auction_info["limit_up_price"]

        # 模拟竞价结果
        import random

        auction_price = yesterday_close * random.uniform(1.08, 1.095)  # 接近涨停价
        turnover_rate = random.uniform(0.01, 0.04)  # 1-4% 换手率

        # 确认条件
        confirmed = (
            auction_price >= limit_up_price * 0.99  # 接近涨停价
            and turnover_rate >= g.MIN_TURNOVER_RATE  # 换手率足够
        )

        return {
            "confirmed": confirmed,
            "auction_price": auction_price,
            "turnover_rate": turnover_rate,
        }

    except Exception as e:
        log.debug(f"获取竞价结果失败 {stock}: {e}")
        return {"confirmed": False}


# ================= 3. 开盘确认买入 =================
def opening_confirmation(context):
    """9:32 开盘后主力确认买入"""
    log.info("执行开盘确认买入...")

    if not g.candidate_stocks:
        log.info("无确认候选股，跳过开盘买入")
        return

    try:
        g.today_bought = []
        bought_count = 0

        # 检查现有持仓数量
        current_positions = len(
            [pos for pos in context.portfolio.positions.values() if pos.total_amount > 0]
        )

        for stock in g.candidate_stocks:
            if bought_count >= g.MAX_POSITIONS or current_positions >= g.MAX_POSITIONS:
                break

            # 检查是否已持有
            if context.portfolio.positions[stock].total_amount > 0:
                continue

            auction_info = g.auction_data.get(stock)
            if not auction_info:
                continue

            # 开盘后主力确认检查
            confirmation = check_opening_momentum(stock, auction_info, context)

            if confirmation["buy_signal"]:
                # 执行买入
                if execute_buy_order(stock, context, confirmation):
                    bought_count += 1
                    current_positions += 1

        if bought_count > 0:
            log.info(f"开盘买入执行: {bought_count}只股票")
        else:
            log.info("开盘无买入执行")

    except Exception as e:
        log.error(f"开盘买入失败: {e}")


def check_opening_momentum(stock, auction_info, context):
    """检查开盘后主力动量确认"""
    try:
        # 实际需要实时tick数据分析大单流入
        # 这里用简化的启发式规则

        limit_up_price = auction_info["limit_up_price"]
        current_data = get_current_data()
        current_price = current_data[stock].last_price

        # 模拟主力确认条件
        import random

        momentum_score = random.uniform(0.3, 1.0)

        # 买入信号条件
        buy_signal = (
            current_price >= limit_up_price * 0.98  # 接近或达到涨停
            and momentum_score >= 0.7  # 动量确认
            and not current_data[stock].paused  # 未停牌
        )

        return {
            "buy_signal": buy_signal,
            "momentum_score": momentum_score,
            "current_price": current_price,
        }

    except Exception as e:
        log.debug(f"动量确认失败 {stock}: {e}")
        return {"buy_signal": False}


def execute_buy_order(stock, context, confirmation):
    """执行买入订单"""
    try:
        # 计算买入金额
        target_value = context.portfolio.total_value * g.POSITION_SIZE

        # 检查总仓位限制
        current_value = sum([pos.value for pos in context.portfolio.positions.values()])
        if current_value + target_value > context.portfolio.total_value * g.MAX_TOTAL_POSITION:
            log.info(f"总仓位限制，跳过买入 {stock}")
            return False

        # 涨停价买入
        limit_up_price = g.auction_data[stock]["limit_up_price"]
        order_obj = order_target_value(stock, target_value)

        if order_obj and order_obj.filled > 0:
            current_data = get_current_data()
            stock_name = current_data[stock].name

            # 记录持仓信息
            g.position_info[stock] = {
                "buy_date": context.current_dt.date(),
                "buy_price": order_obj.price,
                "limit_up_price": limit_up_price,
                "hold_days": 0,
                "momentum_score": confirmation["momentum_score"],
            }

            g.today_bought.append(stock)

            log.info(
                f"买入成功: {stock_name}({stock}) "
                f"数量:{order_obj.filled} 价格:{order_obj.price:.2f} "
                f"动量:{confirmation['momentum_score']:.2f}"
            )

            return True

    except Exception as e:
        log.error(f"买入失败 {stock}: {e}")

    return False


# ================= 4. 持仓监控 =================
def monitor_positions(context):
    """持仓监控和风控"""
    log.info("执行持仓监控...")

    current_positions = [
        pos.security for pos in context.portfolio.positions.values() if pos.total_amount > 0
    ]

    if not current_positions:
        return

    try:
        # 更新持仓天数
        for stock in list(g.position_info.keys()):
            if stock in g.position_info:
                g.position_info[stock]["hold_days"] += 1

        # 风控检查
        for stock in current_positions:
            position = context.portfolio.positions[stock]
            position_info = g.position_info.get(stock)

            if not position_info:
                continue

            current_price = position.price
            buy_price = position_info["buy_price"]
            profit_rate = current_price / buy_price - 1

            sell_reason = None

            # 止损条件
            if profit_rate <= -g.STOP_LOSS_RATE:
                sell_reason = "止损"

            # 止盈条件
            elif profit_rate >= g.TAKE_PROFIT_RATE:
                sell_reason = "止盈"

            # 持有天数限制
            elif position_info["hold_days"] >= g.MAX_HOLD_DAYS:
                sell_reason = "到期"

            # 涨停板次日冲高回落
            elif (
                position_info["hold_days"] == 1
                and current_price < position_info["limit_up_price"] * 0.95
            ):
                sell_reason = "冲高回落"

            # 执行卖出
            if sell_reason and stock not in g.today_bought:
                execute_sell_order(stock, context, sell_reason, profit_rate)

    except Exception as e:
        log.error(f"持仓监控失败: {e}")


def execute_sell_order(stock, context, reason, profit_rate):
    """执行卖出订单"""
    try:
        order_obj = order_target_value(stock, 0)

        if order_obj and order_obj.filled > 0:
            current_data = get_current_data()
            stock_name = current_data[stock].name

            log.info(
                f"卖出: {stock_name}({stock}) "
                f"数量:{order_obj.filled} 价格:{order_obj.price:.2f} "
                f"收益:{profit_rate:.2%} 原因:{reason}"
            )

            # 清除持仓信息
            if stock in g.position_info:
                del g.position_info[stock]

            return True

    except Exception as e:
        log.error(f"卖出失败 {stock}: {e}")

    return False


# ================= 5. 日终总结 =================
def end_of_day_summary(context):
    """日终总结"""
    positions = [pos for pos in context.portfolio.positions.values() if pos.total_amount > 0]

    if not positions:
        log.info("当前无持仓")
        return

    log.info("===== VIP涨停策略持仓总结 =====")
    total_value = 0

    for pos in positions:
        profit_rate = (pos.price / pos.avg_cost - 1) * 100 if pos.avg_cost > 0 else 0

        position_info = g.position_info.get(pos.security, {})
        hold_days = position_info.get("hold_days", 0)
        momentum_score = position_info.get("momentum_score", 0)

        current_data = get_current_data()
        stock_name = current_data[pos.security].name

        log.info(
            f"{stock_name}({pos.security}) [{hold_days}天] "
            f"成本:{pos.avg_cost:.2f} 现价:{pos.price:.2f} "
            f"收益:{profit_rate:.2%} 动量:{momentum_score:.2f} "
            f"市值:{pos.value:.0f}"
        )

        total_value += pos.value

    total_profit_rate = (
        ((context.portfolio.total_value / context.portfolio.starting_cash - 1) * 100)
        if context.portfolio.starting_cash > 0
        else 0
    )

    log.info(f"持仓市值: {total_value:.0f} 总收益: {total_profit_rate:.2%}")
    log.info("=" * 40)
