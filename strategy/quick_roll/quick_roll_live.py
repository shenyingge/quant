# 克隆自聚宽文章：https://www.joinquant.com/post/50995
# 修改：集成飞书通知、修复 numpy.sum 冲突、修正 context 作用域
# 实盘版本：使用 Redis 信号发送，15:10 读取成交记录
# 日期：2025-08-10

from jqdata import *
from jqfactor import get_factor_values
from itertools import chain
import pandas as pd
import datetime
from feishu import push_order_msg, send_msg
from redis_signal_sender import RedisSignalSender, send_order_signal, get_today_trades, get_yesterday_positions


# ================= 0. 初始化 =================
def initialize(context):

    set_benchmark('000905.XSHG')
    set_option('use_real_price', True)
    set_option("avoid_future_data", True)
    set_slippage(FixedSlippage(0))
    set_order_cost(
        OrderCost(open_tax=0, close_tax=0.0005,
                  open_commission=0.0001, close_commission=0.0001,
                  close_today_commission=0, min_commission=5),
        type='fund'
    )
    log.set_level('order', 'error')

    g.stock_num  = 10     # 最大持仓数
    g.limit_days = 20     # 回避最近 N 天已买过的票
    g.limit_up_list = []
    g.hold_list      = []
    g.history_hold_list = []
    g.not_buy_again_list = []
    g.today_bought = []

    # 实盘模式标志
    g.is_live_trading = True  # 设置为 True 时使用 Redis 信号

    # 初始化 Redis 发送器
    if g.is_live_trading:
        g.redis_sender = RedisSignalSender()
        g.pending_signals = {}  # 记录待成交的信号 {stock_code: signal_id}

    # 虚拟持仓（实盘时用于跟踪）
    g.virtual_positions = {}  # {stock_code: {'volume': xxx, 'avg_cost': xxx}}

    run_daily(prepare_stock_list,  time='9:05', reference_security='000300.XSHG')
    run_weekly(weekly_adjustment,  weekday=1, time='9:40', reference_security='000300.XSHG')
    run_daily(check_limit_up,      time='11:00', reference_security='000300.XSHG')
    run_daily(update_from_redis,   time='15:10', reference_security='000300.XSHG')  # 更新成交记录
    run_daily(print_position_info, time='15:20', reference_security='000300.XSHG')  # 改到 15:20
    run_daily(stop_loss_check,     time='14:30', reference_security='000300.XSHG')

def is_market_ok(context):
    index = '000300.XSHG'
    close = get_price(index, count=20, end_date=context.previous_date, frequency='daily')['close']
    return close[-5:].mean() > close.mean()



# ================ 1. 选股逻辑 ================
def get_factor_filter_list(context, stock_list, jqfactor, ascend, p1, p2):
    y = context.previous_date
    scores = get_factor_values(stock_list, jqfactor, end_date=y, count=1)[jqfactor].iloc[0]
    df = pd.DataFrame({'code': stock_list, 'score': scores})
    df.dropna(inplace=True)
    df.sort_values('score', ascending=ascend, inplace=True)
    return df.code.tolist()[int(p1*len(df)): int(p2*len(df))]


def stop_loss_check(context):
    send_msg("stop loss check")

    # 实盘模式使用虚拟持仓
    if g.is_live_trading:
        for stock_code, position_data in g.virtual_positions.items():
            current_price = get_current_data()[stock_code].last_price
            avg_cost = position_data['avg_cost']
            if avg_cost > 0 and current_price / avg_cost < 0.9:  # 跌超10%
                log.info(f"止损触发：{stock_code} 当前价{current_price:.2f}  成本{avg_cost:.2f}")
                close_position(context, stock_code, position_data)
    else:
        # 回测模式使用真实持仓
        for position in context.portfolio.positions.values():
            current_price = position.price
            avg_cost = position.avg_cost
            if avg_cost > 0 and current_price / avg_cost < 0.9:
                log.info(f"止损触发：{position.security} 当前价{current_price:.2f}  成本{avg_cost:.2f}")
                close_position(context, position.security, position)

def get_stock_list(context):
    y = context.previous_date
    all_sec = get_all_securities().index.tolist()
    all_sec = filter_kcbj_stock(all_sec)
    all_sec = filter_st_stock(all_sec)

    pool1 = filter_new_stock(context, all_sec, 250)
    roa   = get_factor_filter_list(context, pool1, 'roa_ttm_8y', True, 0, 0.1)
    reps  = get_factor_filter_list(context, pool1, 'retained_earnings_per_share', True, 0, 0.1)

    pool2 = filter_new_stock(context, all_sec, 125)
    nls   = get_factor_filter_list(context, pool2, 'non_linear_size', True, 0, 0.1)

    union = list(set(roa) | set(reps) | set(nls))
    q = query(valuation.code, valuation.circulating_market_cap)\
        .filter(valuation.code.in_(union))\
        .order_by(valuation.circulating_market_cap.asc())
    df = get_fundamentals(q, date=y)
    return df.code.tolist()


# ================ 1-3 准备股票池 ================
def prepare_stock_list(context):
    send_msg("prepare stock list")
    g.today_bought = []

    # 实盘模式：9:05 从 Redis 同步昨日持仓
    if g.is_live_trading:
        # 从 Redis 获取昨日持仓
        yesterday_positions = get_yesterday_positions()

        if yesterday_positions:
            log.info(f"从 Redis 同步昨日持仓: {len(yesterday_positions)} 只")
            # 清空虚拟持仓，使用 Redis 的数据
            g.virtual_positions = {}

            for stock_code, position_data in yesterday_positions.items():
                g.virtual_positions[stock_code] = {
                    'volume': position_data['volume'],
                    'avg_cost': position_data['avg_cost'],
                    'signal_id': None,  # 昨日持仓没有今日的 signal_id
                    'pending': False  # 已确认的持仓
                }
                log.info(f"同步持仓: {stock_code}, 数量: {position_data['volume']}, 成本: {position_data['avg_cost']:.2f}")

            send_msg(f"📊 从 Redis 同步昨日持仓\n持仓数量: {len(g.virtual_positions)} 只")
        else:
            log.info("Redis 中没有昨日持仓数据")

        g.hold_list = list(g.virtual_positions.keys())
    else:
        # 回测模式：使用真实持仓
        g.hold_list = [pos.security for pos in context.portfolio.positions.values()]

    # 最近 N 日持仓历史
    g.history_hold_list.append(g.hold_list)
    if len(g.history_hold_list) > g.limit_days:
        g.history_hold_list = g.history_hold_list[-g.limit_days:]

    flat = chain.from_iterable(g.history_hold_list)
    g.not_buy_again_list = list(set(flat))

    # 昨日涨停股票
    if g.hold_list:
        df = get_price(g.hold_list, end_date=context.previous_date,
                       frequency='daily', fields=['close', 'high_limit'],
                       count=1, panel=False)
        g.limit_up_list = df[df.close == df.high_limit].code.tolist()
    else:
        g.limit_up_list = []


# ================ 1-4 周度调仓 =================
def weekly_adjustment(context):
    send_msg('weekly adjust')

    targets = get_stock_list(context)
    targets = filter_paused_stock(targets)
    targets = filter_limitup_stock(context, targets)
    targets = filter_limitdown_stock(context, targets)
    targets = filter_paused_stock(targets)

    recent = get_recent_limit_up_stock(context, targets, g.limit_days)
    blacklist = set(g.not_buy_again_list) & set(recent)
    targets = [s for s in targets if s not in blacklist][:g.stock_num]

    # 卖出
    for s in g.hold_list:
        if s not in targets and s not in g.limit_up_list:
            if g.is_live_trading:
                position_data = g.virtual_positions.get(s)
                if position_data:
                    close_position(context, s, position_data)
            else:
                close_position(context, s, context.portfolio.positions[s])

    # 买入
    if g.is_live_trading:
        need_buy = len(targets) - len(g.virtual_positions)
    else:
        need_buy = len(targets) - len(context.portfolio.positions)

    if need_buy > 0:
        cash_per = context.portfolio.cash / need_buy
        for s in targets:
            should_buy = False
            if g.is_live_trading:
                should_buy = s not in g.virtual_positions
            else:
                should_buy = context.portfolio.positions[s].total_amount == 0

            if should_buy:
                if open_position(context, s, cash_per):
                    if g.is_live_trading:
                        if len(g.virtual_positions) == len(targets):
                            break
                    else:
                        if len(context.portfolio.positions) == len(targets):
                            break


# ================ 1-5 日内涨停检查 ==============
def check_limit_up(context):
    send_msg("check limit up")
    if not g.limit_up_list:
        return
    for s in g.limit_up_list:
        df = get_price(s, end_date=context.current_dt, frequency='1m',
                       fields=['close', 'high_limit'], count=1, panel=False)
        if df.iloc[0, 0] < df.iloc[0, 1]:
            if g.is_live_trading:
                position_data = g.virtual_positions.get(s)
                if position_data:
                    close_position(context, s, position_data)
            else:
                close_position(context, s, context.portfolio.positions[s])


# ================ 2. 过滤工具 ===================
def filter_paused_stock(stocks):
    cd = get_current_data()
    return [s for s in stocks if not cd[s].paused]


def filter_st_stock(stocks):
    cd = get_current_data()
    return [s for s in stocks
            if not cd[s].is_st and 'ST' not in cd[s].name
            and '*' not in cd[s].name and '退' not in cd[s].name]


def get_recent_limit_up_stock(context, stocks, days):
    y = context.previous_date
    res = []
    for s in stocks:
        df = get_price(s, end_date=y, frequency='daily',
                       fields=['close', 'high_limit'], count=days, panel=False)
        if (df.close == df.high_limit).any():
            res.append(s)
    return res


def filter_limitup_stock(context, stocks):
    last = history(1, unit='1m', field='close', security_list=stocks)
    cd = get_current_data()
    if g.is_live_trading:
        return [s for s in stocks if s in g.virtual_positions or last[s][-1] < cd[s].high_limit]
    else:
        return [s for s in stocks if s in context.portfolio.positions or last[s][-1] < cd[s].high_limit]


def filter_limitdown_stock(context, stocks):
    last = history(1, unit='1m', field='close', security_list=stocks)
    cd = get_current_data()
    if g.is_live_trading:
        return [s for s in stocks if s in g.virtual_positions or last[s][-1] > cd[s].low_limit]
    else:
        return [s for s in stocks if s in context.portfolio.positions or last[s][-1] > cd[s].low_limit]


def filter_kcbj_stock(stocks):
    return [s for s in stocks if not (s.startswith(('4', '8')) or s.startswith('68') or s.startswith('300'))]


def filter_new_stock(context, stocks, days):
    y = context.previous_date
    return [s for s in stocks if (y - get_security_info(s).start_date).days >= days]

def filter_paused_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused]


# ================ 3. 交易封装（Redis 版本）===================
def order_target_value_(security, value):
    """
    实盘时发送 Redis 信号，回测时正常下单
    """
    if g.is_live_trading:
        # 实盘模式：不真实下单，返回模拟的 order 对象
        class MockOrder:
            def __init__(self):
                self.filled = 0
                self.price = 0
                self.order_id = None
                self.status = None
                self.amount = 0
        return MockOrder()
    else:
        # 回测模式：正常下单
        return order_target_value(security, value)


# ＝ open_position ＝
def open_position(context, security, value):
    """开仓（实盘时发送买入信号）"""

    if g.is_live_trading:
        # 计算买入数量
        current_price = get_current_data()[security].last_price
        if current_price <= 0:
            return False

        volume = int(value / current_price / 100) * 100  # 取整到100股
        if volume < 100:
            return False

        # 发送买入信号到 Redis
        signal_id = send_order_signal(
            stock_code=security,
            direction='BUY',
            volume=volume,
            price=current_price,  # 使用当前价作为限价
            strategy_name="quick_roll",
            extra={
                "target_value": value,
                "strategy": "牛市板块快速轮动"
            }
        )

        if signal_id:
            # 记录待成交信号
            g.pending_signals[security] = signal_id

            # 预先记录虚拟持仓（15:10 会根据实际成交更新）
            g.virtual_positions[security] = {
                'volume': volume,
                'avg_cost': current_price,
                'signal_id': signal_id,
                'pending': True  # 标记为待成交
            }

            # 发送飞书通知
            push_order_msg(
                symbol=security,
                name=get_security_info(security).display_name,
                side='BUY',
                volume=volume,
                price=current_price,
                order_id=signal_id,
                strategy_name="牛市板块快速轮动",
                extra=f"[Redis信号] 目标金额 {value:.0f}"
            )

            g.today_bought.append(security)
            return True
        return False

    else:
        # 回测模式：正常下单
        order = order_target_value_(security, value)
        if order and order.filled > 0:
            push_order_msg(
                symbol=security,
                name=get_security_info(security).display_name,
                side='BUY',
                volume=order.filled,
                price=order.price,
                order_id=order.order_id,
                strategy_name="牛市板块快速轮动",
                extra=f"剩余现金 {context.portfolio.cash:.0f}"
            )
            g.today_bought.append(security)
            return True
        return False


# ＝ close_position ＝
def close_position(context, security, position_data):
    """平仓（实盘时发送卖出信号）"""

    if security in g.today_bought:
        return False

    if g.is_live_trading:
        # 实盘模式：发送卖出信号
        if security not in g.virtual_positions:
            return False

        position = g.virtual_positions[security]
        volume = position['volume']
        avg_cost = position['avg_cost']
        current_price = get_current_data()[security].last_price

        # 发送卖出信号到 Redis
        signal_id = send_order_signal(
            stock_code=security,
            direction='SELL',
            volume=volume,
            price=current_price,  # 使用当前价作为限价
            strategy_name="quick_roll",
            extra={
                "avg_cost": avg_cost,
                "profit_rate": (current_price / avg_cost - 1) * 100 if avg_cost > 0 else 0
            }
        )

        if signal_id:
            profit = (current_price / avg_cost - 1) * 100 if avg_cost > 0 else 0

            # 发送飞书通知
            push_order_msg(
                symbol=security,
                name=get_security_info(security).display_name,
                side='SELL',
                volume=volume,
                price=current_price,
                order_id=signal_id,
                strategy_name="牛市板块快速轮动",
                extra=f"[Redis信号] 收益 {profit:.2f}%"
            )

            # 从虚拟持仓中移除
            del g.virtual_positions[security]
            return True
        return False

    else:
        # 回测模式：正常下单
        order = order_target_value_(position_data.security, 0)
        if order and order.filled > 0:
            profit = (position_data.price / position_data.avg_cost - 1) * 100
            push_order_msg(
                symbol=position_data.security,
                name=get_security_info(position_data.security).display_name,
                side='SELL',
                volume=order.filled,
                price=order.price,
                order_id=order.order_id,
                strategy_name="牛市板块快速轮动",
                extra=f"收益 {profit:.2f}%"
            )
            return order.status == OrderStatus.held and order.filled == order.amount
        return False


# ================ 4. Redis 成交更新 ===================
def update_from_redis(context):
    """
    15:10 从 Redis 读取今日成交记录，更新虚拟持仓
    主要处理今日新发出的交易信号的成交情况
    """
    if not g.is_live_trading:
        return

    send_msg("从 Redis 更新今日成交记录")

    # 获取今日所有成交记录
    trade_records = get_today_trades()

    # 按信号ID分组
    trades_by_signal = {}
    for trade in trade_records:
        signal_id = trade.get('signal_id')
        if signal_id:
            trades_by_signal[signal_id] = trade

    # 更新今日发出信号的持仓状态
    updated_count = 0
    removed_count = 0

    for stock_code, position in list(g.virtual_positions.items()):
        signal_id = position.get('signal_id')

        # 只处理今日发出的信号（有 signal_id 的）
        if signal_id:
            if signal_id in trades_by_signal:
                trade = trades_by_signal[signal_id]

                # 更新为实际成交信息
                if trade.get('direction') == 'BUY':
                    position['volume'] = trade.get('filled_volume', position['volume'])
                    position['avg_cost'] = trade.get('filled_price', position['avg_cost'])
                    position['pending'] = False
                    updated_count += 1
                    log.info(f"确认买入成交: {stock_code}, 数量: {position['volume']}, 价格: {position['avg_cost']:.2f}")

                elif trade.get('direction') == 'SELL':
                    # 卖出已成交，从持仓中移除
                    if stock_code in g.virtual_positions:
                        del g.virtual_positions[stock_code]
                        removed_count += 1
                        log.info(f"确认卖出成交: {stock_code}")
            else:
                # 今日信号未成交，移除虚拟持仓
                if position.get('pending', False):
                    del g.virtual_positions[stock_code]
                    removed_count += 1
                    log.warning(f"信号未成交，移除虚拟持仓: {stock_code}, signal_id: {signal_id}")

    # 汇总信息
    summary = g.redis_sender.get_today_summary("quick_roll")
    log.info(f"今日成交汇总: 买入{summary['buy_trades']}笔, 卖出{summary['sell_trades']}笔")
    log.info(f"买入金额: {summary['total_buy_amount']:.0f}, 卖出金额: {summary['total_sell_amount']:.0f}")
    log.info(f"更新 {updated_count} 个持仓，移除 {removed_count} 个持仓")

    # 发送飞书通知
    send_msg(f"""
📊 收盘成交确认
- 今日买入: {summary['buy_trades']}笔, 金额: {summary['total_buy_amount']:.0f}
- 今日卖出: {summary['sell_trades']}笔, 金额: {summary['total_sell_amount']:.0f}
- 成交更新: {updated_count}个, 移除: {removed_count}个
- 最新持仓: {len(g.virtual_positions)}只
    """)


# ================ 5. 打印持仓 ===================
def print_position_info(context):
    """打印持仓信息（实盘时显示虚拟持仓）"""

    if g.is_live_trading:
        log.info("===== 虚拟持仓信息 =====")
        for stock_code, position in g.virtual_positions.items():
            current_price = get_current_data()[stock_code].last_price
            avg_cost = position['avg_cost']
            volume = position['volume']
            ret = (current_price / avg_cost - 1) * 100 if avg_cost > 0 else 0
            value = current_price * volume
            pending = position.get('pending', False)
            status = "[待成交]" if pending else ""

            log.info(f"{stock_code} {status} 成本{avg_cost:.2f} 现价{current_price:.2f} "
                    f"收益{ret:.2f}% 持仓{volume} 市值{value:.0f}")
    else:
        # 回测模式：显示真实持仓
        for t in get_trades().values():
            print('成交记录:', t)
        for p in context.portfolio.positions.values():
            ret = (p.price / p.avg_cost - 1) * 100
            print(f"{p.security} 成本{p.avg_cost:.2f} 现价{p.price:.2f} "
                  f"收益{ret:.2f}% 持仓{p.total_amount} 市值{p.value:.0f}")

    print('-----------------------------')
