# 少妇战法策略 - 聚宽简化版本
# 实现 B1(回踩反包) 和 B2(突破前高) 交易逻辑
# 修复版本 - 2025-08-10

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
    log.set_level("order", "error")
    log.set_level("system", "debug")  # 启用debug级别日志

    # 策略参数（放宽部分条件以增加交易频率）
    g.N_BOLL = 20  # 布林带周期
    g.K = 2  # 布林带标准差倍数
    g.VOL_RATIO = 1.5  # 首阳放量倍数（从2.0降至1.5）
    g.SHRINK = 0.8  # 回踩缩量倍数（从0.6提至0.8）
    g.TAKE1 = 1.02  # 触及前高上浮2%先减仓
    g.SL = 0.98  # 跌破B1当日低点再给2%空间止损
    g.MAX_HOLD_DAYS = 5  # 最长持有天数
    g.MAX_POS = 0.9  # 总仓位上限
    g.POS_PER_STOCK = 0.2  # 单票目标仓位
    g.MAX_STOCKS = 5  # 最大持股数量

    # 状态容器
    g.pool = []
    g.positions_state = {}
    g.today_bought = []

    log.info("少妇战法策略启动")

    # 调度任务
    run_daily(select_universe, time="08:55")
    run_daily(debug_data_fetch, time="08:56")  # 紧跟在选股后测试数据获取
    run_daily(open_buy, time="09:35")
    run_daily(close_ops, time="14:50")
    run_daily(print_position_info, time="15:20")


# ================= 1. 选股逻辑 =================
def select_universe(context):
    """选股与备选池更新"""
    log.info("开始选股...")

    try:
        # 获取全市场股票
        all_stocks = list(get_all_securities(["stock"]).index)
        log.info(f"全市场股票数量: {len(all_stocks)}")
        if len(all_stocks) > 0:
            log.debug(f"股票代码示例: {all_stocks[:5]}")

        # 基础过滤
        stocks = []
        current_data = get_current_data()

        for stock in all_stocks:
            try:
                info = current_data[stock]

                # 排除ST、停牌、科创板、创业板、北交所
                if (
                    info.is_st
                    or info.paused
                    or "ST" in info.name
                    or "*" in info.name
                    or "退" in info.name
                    or stock.startswith(("688", "300", "8", "4"))
                ):
                    continue

                # 排除新股（放宽至30天）
                if (context.previous_date - get_security_info(stock).start_date).days < 30:
                    continue

                stocks.append(stock)

            except:
                continue

        log.info(f"基础过滤后股票数量: {len(stocks)}")

        # 流动性过滤：取前500只做候选（增加候选池）
        stocks = stocks[:500]

        # 行业热度筛选（简化版）
        hot_stocks = []
        try:
            # 获取基本面数据（放宽市值限制）
            q = (
                query(valuation.code, valuation.circulating_market_cap)
                .filter(valuation.code.in_(stocks), valuation.circulating_market_cap <= 300)
                .order_by(valuation.circulating_market_cap.asc())
            )

            df = get_fundamentals(q, date=context.previous_date)
            hot_stocks = list(df.code)

        except Exception as e:
            log.info(f"基本面筛选失败，使用前200只: {e}")
            hot_stocks = stocks[:200]

        g.pool = hot_stocks[:150]  # 增加候选池到150只
        log.info(f"选股完成，候选池: {len(g.pool)}只")
        if len(g.pool) > 0:
            log.info(f"候选池前10只: {g.pool[:10]}")

    except Exception as e:
        log.error(f"选股失败: {e}")
        g.pool = []


def debug_data_fetch(context):
    """调试数据获取功能"""
    if not g.pool:
        log.debug("候选池为空，跳过数据获取测试")
        return

    test_stocks = g.pool[:3]  # 测试前3只股票
    log.debug(f"测试数据获取，股票列表: {test_stocks}")

    for stock in test_stocks:
        try:
            log.debug(f"测试获取 {stock} 的数据...")
            df = get_price(
                stock,
                count=5,
                end_date=context.previous_date,
                fields=["close", "volume"],
                frequency="daily",
            )
            if df is not None and not df.empty:
                log.debug(f"{stock} 数据获取成功，长度: {len(df)}")
                log.debug(f"{stock} 最新收盘价: {df.close.iloc[-1]:.2f}")
            else:
                log.debug(f"{stock} 数据获取失败：数据为空")
        except Exception as e:
            log.debug(f"{stock} 数据获取异常: {e}")


# ================= 2. 技术指标计算 =================
def calc_factors(stocks, context):
    """计算技术指标"""
    if not stocks:
        return {}

    stock_data = {}

    for stock in stocks:
        try:
            # 增加调试信息
            log.debug(f"正在获取 {stock} 的价格数据...")

            # 使用前一交易日作为结束日期，避免盘中数据获取问题
            df = get_price(
                stock,
                count=25,
                end_date=context.previous_date,
                fields=["open", "high", "low", "close", "volume"],
                frequency="daily",
                skip_paused=True,
            )

            if df is None or df.empty:
                log.debug(f"{stock} 数据为空，跳过")
                continue

            if len(df) < 25:
                log.debug(f"{stock} 数据长度不足: {len(df)} < 25")
                continue

            # 计算布林带
            df["ma20"] = df.close.rolling(g.N_BOLL).mean()
            df["std20"] = df.close.rolling(g.N_BOLL).std()
            df["upper"] = df.ma20 + g.K * df.std20
            df["lower"] = df.ma20 - g.K * df.std20

            # 计算移动平均线
            df["ma5"] = df.close.rolling(5).mean()
            df["ma10"] = df.close.rolling(10).mean()
            df["ma5_vol"] = df.volume.rolling(5).mean()

            # 数据清理：先处理NaN值
            df = df.fillna(method="ffill").fillna(0)

            # 形态判定
            df["is_yang"] = df.close > df.open
            df["is_first_sun"] = (df.is_yang) & (df.volume >= df.ma5_vol * g.VOL_RATIO)
            df["is_pullback"] = ((df.low <= df.ma20) | (df.low <= df.ma10)) & (
                df.volume <= df.volume.shift(1) * g.SHRINK
            )
            df["is_rebound"] = df.is_yang

            # 确保布尔值列没有NaN
            df["is_first_sun"] = df["is_first_sun"].fillna(False)
            df["is_pullback"] = df["is_pullback"].fillna(False)
            df["is_rebound"] = df["is_rebound"].fillna(False)

            # 关键价位
            df["prev_high"] = df.high.shift(1).fillna(df.high)  # 如果前一日高点为NaN，用当日高点
            df["b1_low"] = df.low

            stock_data[stock] = df
            log.debug(f"{stock} 技术指标计算成功")

        except Exception as e:
            log.debug(f"{stock} 技术指标计算失败: {e}")
            continue

    return stock_data


# ================= 3. B2突破买入逻辑 =================
def open_buy(context):
    """B2突破前高买入检查"""
    log.info("检查B2突破信号...")

    try:
        # 合并持仓股票和候选池
        current_positions = [
            pos.security for pos in context.portfolio.positions.values() if pos.total_amount > 0
        ]
        check_stocks = list(set(g.pool + current_positions))

        if not check_stocks:
            log.info("候选池为空，跳过B2检查")
            return

        log.info(f"B2检查股票数量: {len(check_stocks)}")

        # 计算技术指标
        stock_data = calc_factors(check_stocks, context)
        log.info(f"成功计算指标的股票数量: {len(stock_data)}")

        buy_signals = []
        checked_count = 0

        for stock, df in stock_data.items():
            if len(df) < 2:
                continue

            checked_count += 1
            # 因为使用previous_date作为end_date，所以最新的数据实际是"昨天"
            day_before = df.iloc[-2]  # 前天
            yesterday = df.iloc[-1]  # 昨天（最新可用数据）

            # 调试信息
            if checked_count <= 5:  # 只打印前5只的详细信息
                log.info(
                    f"{stock}: 前天首阳={day_before.is_first_sun}, "
                    f"前天回踩反包={(day_before.is_pullback and day_before.is_rebound)}, "
                    f"昨收盘={yesterday.close:.2f}, 前天高={day_before.high:.2f}, "
                    f"前天量={day_before.volume:.0f}, 5日均量={day_before.ma5_vol:.0f}"
                )

            # B2条件：前天首阳 + 昨天突破前高 + 前天不是B1
            # 使用前天的高点作为前高参考
            prev_high_price = day_before.high
            if (
                day_before.is_first_sun
                and not (day_before.is_pullback and day_before.is_rebound)
                and yesterday.close >= prev_high_price
            ):

                buy_signals.append(
                    {
                        "stock": stock,
                        "prev_high": prev_high_price,
                        "b1_low": yesterday.b1_low,
                        "current_price": yesterday.close,
                        "signal_type": "B2",
                    }
                )
                log.info(f"发现B2信号: {stock} 突破前高 {prev_high_price:.2f}")

        log.info(f"B2检查完成，发现{len(buy_signals)}个信号，检查了{checked_count}只股票")

        # 执行买入
        executed_count = 0
        for signal in buy_signals:
            if executed_count >= g.MAX_STOCKS:
                break

            stock = signal["stock"]

            # 检查是否已持有
            if context.portfolio.positions[stock].total_amount > 0:
                continue

            # 检查仓位限制
            current_value = sum([pos.value for pos in context.portfolio.positions.values()])
            if current_value >= context.portfolio.total_value * g.MAX_POS:
                break

            # 执行买入
            target_value = context.portfolio.total_value * g.POS_PER_STOCK
            if execute_buy_order(context, stock, target_value, signal):
                g.positions_state[stock] = {
                    "buy_date": context.current_dt.date(),
                    "buy_price": signal["current_price"],
                    "prev_high": signal["prev_high"],
                    "b1_low": signal["b1_low"],
                    "hold_days": 0,
                    "signal_type": signal["signal_type"],
                }
                executed_count += 1

        if executed_count > 0:
            log.info(f"B2买入执行: {executed_count}只股票")
        else:
            log.info("B2无买入执行")

    except Exception as e:
        log.error(f"B2买入检查失败: {e}")


# ================= 4. B1反包买入+风控逻辑 =================
def close_ops(context):
    """B1反包买入 + 风控检查"""
    log.info("执行B1买入和风控检查...")

    try:
        # 重置今日买入列表
        g.today_bought = []

        # 更新持仓天数
        for stock in list(g.positions_state.keys()):
            if stock in g.positions_state:
                g.positions_state[stock]["hold_days"] += 1

        # 风控检查
        execute_risk_control(context)

        # B1信号检查
        execute_b1_signals(context)

    except Exception as e:
        log.error(f"收盘操作失败: {e}")


def execute_risk_control(context):
    """执行风控"""
    current_positions = [
        pos.security for pos in context.portfolio.positions.values() if pos.total_amount > 0
    ]

    if not current_positions:
        return

    try:
        stock_data = calc_factors(current_positions, context)

        for stock in current_positions:
            if stock not in g.positions_state or stock not in stock_data:
                continue

            position_info = g.positions_state[stock]
            df = stock_data[stock]

            if len(df) == 0:
                continue

            today = df.iloc[-1]
            current_price = today.close

            # 止盈条件
            take_profit_price = max(position_info["prev_high"] * g.TAKE1, today.upper)
            if current_price >= take_profit_price:
                execute_sell_order(
                    context,
                    stock,
                    "止盈",
                    f"价格{current_price:.2f} >= 止盈位{take_profit_price:.2f}",
                )
                continue

            # 止损条件
            stop_loss_price = min(position_info["b1_low"] * g.SL, today.ma5)
            if current_price <= stop_loss_price:
                execute_sell_order(
                    context,
                    stock,
                    "止损",
                    f"价格{current_price:.2f} <= 止损位{stop_loss_price:.2f}",
                )
                continue

            # 时限条件
            if position_info["hold_days"] >= g.MAX_HOLD_DAYS:
                execute_sell_order(
                    context, stock, "时限", f"持有{position_info['hold_days']}天达到上限"
                )
                continue

    except Exception as e:
        log.error(f"风控检查失败: {e}")


def execute_b1_signals(context):
    """执行B1反包买入信号"""
    log.info("检查B1反包信号...")

    try:
        current_positions = [
            pos.security for pos in context.portfolio.positions.values() if pos.total_amount > 0
        ]
        check_stocks = list(set(g.pool + current_positions))

        if not check_stocks:
            log.info("候选池为空，跳过B1检查")
            return

        log.info(f"B1检查股票数量: {len(check_stocks)}")

        stock_data = calc_factors(check_stocks, context)
        log.info(f"成功计算指标的股票数量: {len(stock_data)}")

        b1_signals = []
        checked_count = 0

        for stock, df in stock_data.items():
            if len(df) < 2:
                continue

            checked_count += 1
            # 因为使用previous_date作为end_date，所以最新的数据实际是"昨天"
            day_before = df.iloc[-2]  # 前天
            yesterday = df.iloc[-1]  # 昨天（最新可用数据）

            # 调试信息
            if checked_count <= 5:  # 只打印前5只的详细信息
                log.info(
                    f"{stock}: 前天首阳={day_before.is_first_sun}, "
                    f"昨日回踩={yesterday.is_pullback}, 昨日反包={yesterday.is_rebound}, "
                    f"昨日量={yesterday.volume:.0f}, 前天量={day_before.volume:.0f}"
                )

            # B1条件：前天首阳 + 昨天回踩反包
            if day_before.is_first_sun and yesterday.is_pullback and yesterday.is_rebound:

                b1_signals.append(
                    {
                        "stock": stock,
                        "prev_high": day_before.high,  # 前天的高点
                        "b1_low": yesterday.low,  # 昨天的低点
                        "current_price": yesterday.close,  # 昨天收盘价
                        "signal_type": "B1",
                    }
                )
                log.info(f"发现B1信号: {stock} 回踩反包")

        log.info(f"B1检查完成，发现{len(b1_signals)}个信号，检查了{checked_count}只股票")

        # 执行B1买入
        executed_count = 0
        for signal in b1_signals:
            if executed_count >= g.MAX_STOCKS:
                break

            stock = signal["stock"]

            if context.portfolio.positions[stock].total_amount > 0:
                continue

            current_value = sum([pos.value for pos in context.portfolio.positions.values()])
            if current_value >= context.portfolio.total_value * g.MAX_POS:
                break

            target_value = context.portfolio.total_value * g.POS_PER_STOCK
            if execute_buy_order(context, stock, target_value, signal):
                g.positions_state[stock] = {
                    "buy_date": context.current_dt.date(),
                    "buy_price": signal["current_price"],
                    "prev_high": signal["prev_high"],
                    "b1_low": signal["b1_low"],
                    "hold_days": 0,
                    "signal_type": signal["signal_type"],
                }
                executed_count += 1

        if executed_count > 0:
            log.info(f"B1买入执行: {executed_count}只股票")
        else:
            log.info("B1无买入执行")

    except Exception as e:
        log.error(f"B1信号检查失败: {e}")


# ================= 5. 交易执行函数 =================
def execute_buy_order(context, stock, target_value, signal):
    """执行买入订单"""
    try:
        order_obj = order_target_value(stock, target_value)
        if order_obj and order_obj.filled > 0:
            stock_name = get_security_info(stock).display_name
            log.info(
                f"买入: {stock_name}({stock}) "
                f"数量:{order_obj.filled} 价格:{order_obj.price:.2f} "
                f"类型:{signal['signal_type']}"
            )

            g.today_bought.append(stock)
            return True
    except Exception as e:
        log.error(f"买入失败 {stock}: {e}")

    return False


def execute_sell_order(context, stock, reason, detail):
    """执行卖出订单"""
    if stock in g.today_bought:
        return False

    try:
        order_obj = order_target_value(stock, 0)
        if order_obj and order_obj.filled > 0:
            position = context.portfolio.positions[stock]
            profit_rate = (
                (position.price / position.avg_cost - 1) * 100 if position.avg_cost > 0 else 0
            )

            stock_name = get_security_info(stock).display_name
            log.info(
                f"卖出: {stock_name}({stock}) "
                f"数量:{order_obj.filled} 价格:{order_obj.price:.2f} "
                f"原因:{reason} 收益:{profit_rate:.2f}%"
            )

            if stock in g.positions_state:
                del g.positions_state[stock]
            return True
    except Exception as e:
        log.error(f"卖出失败 {stock}: {e}")

    return False


# ================= 6. 持仓信息打印 =================
def print_position_info(context):
    """打印持仓信息"""
    positions = [pos for pos in context.portfolio.positions.values() if pos.total_amount > 0]

    if not positions:
        log.info("当前无持仓")
        return

    log.info("===== 少妇战法持仓信息 =====")
    total_value = 0

    for pos in positions:
        profit_rate = (pos.price / pos.avg_cost - 1) * 100 if pos.avg_cost > 0 else 0

        state_info = g.positions_state.get(pos.security, {})
        signal_type = state_info.get("signal_type", "Unknown")
        hold_days = state_info.get("hold_days", 0)

        log.info(
            f"{pos.security} [{signal_type}][{hold_days}天] "
            f"成本:{pos.avg_cost:.2f} 现价:{pos.price:.2f} "
            f"收益:{profit_rate:.2f}% 持仓:{pos.total_amount} 市值:{pos.value:.0f}"
        )

        total_value += pos.value

    log.info(f"总持仓市值: {total_value:.0f}")
    log.info("=" * 40)
