# 克隆自聚宽文章：https://www.joinquant.com/post/50995
# 修改：集成飞书通知、修复 numpy.sum 冲突、修正 context 作用域
# 日期：2025-08-01

from jqdata import *
from jqfactor import get_factor_values
from itertools import chain
import pandas as pd
import datetime
from feishu import push_order_msg, send_msg


# ================= 0. 初始化 =================
def initialize(context):

    set_benchmark('000905.XSHG')
    set_option('use_real_price', True)
    set_option("avoid_future_data", True)
    set_slippage(FixedSlippage(0))
    set_order_cost(
        OrderCost(open_tax=0, close_tax=0.001,
                  open_commission=0.0003, close_commission=0.0003,
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

    run_daily(prepare_stock_list,  time='9:05', reference_security='000300.XSHG')
    run_weekly(weekly_adjustment,  weekday=1, time='9:40', reference_security='000300.XSHG')
    run_daily(check_limit_up,      time='11:00', reference_security='000300.XSHG')
    run_daily(print_position_info, time='15:10', reference_security='000300.XSHG')
    run_daily(stop_loss_check, time='14:30', reference_security='000300.XSHG')

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
    for position in context.portfolio.positions.values():
        current_price = position.price
        avg_cost = position.avg_cost
        if avg_cost > 0 and current_price / avg_cost < 0.9:  # 跌超10%
            log.info(f"止损触发：{position.security} 当前价{current_price:.2f}  成本{avg_cost:.2f}")
            close_position(context, position)

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

    # 当前持仓
    g.hold_list = [pos.security for pos in context.portfolio.positions.values()]

    # 最近 N 日持仓历史
    g.history_hold_list.append(g.hold_list)
    if len(g.history_hold_list) > g.limit_days:
        g.history_hold_list = g.history_hold_list[-g.limit_days:]

    flat = chain.from_iterable(g.history_hold_list)     # 避免 numpy.sum 冲突
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
            close_position(context, context.portfolio.positions[s])

    # 买入
    need_buy = len(targets) - len(context.portfolio.positions)
    if need_buy > 0:
        cash_per = context.portfolio.cash / need_buy
        for s in targets:
            if context.portfolio.positions[s].total_amount == 0:
                if open_position(context, s, cash_per):
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
            close_position(context, context.portfolio.positions[s])


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
    return [s for s in stocks if s in context.portfolio.positions or last[s][-1] < cd[s].high_limit]


def filter_limitdown_stock(context, stocks):
    last = history(1, unit='1m', field='close', security_list=stocks)
    cd = get_current_data()
    return [s for s in stocks if s in context.portfolio.positions or last[s][-1] > cd[s].low_limit]


def filter_kcbj_stock(stocks):
    return [s for s in stocks if not (s.startswith(('4', '8')) or s.startswith('68') or s.startswith('300'))]


def filter_new_stock(context, stocks, days):
    y = context.previous_date
    return [s for s in stocks if (y - get_security_info(s).start_date).days >= days]

def filter_paused_stock(stock_list):
    current_data = get_current_data()  # 当前回测时间点的“快照”
    return [stock for stock in stock_list if not current_data[stock].paused]


# ================ 3. 交易封装 ===================
def order_target_value_(security, value):
    return order_target_value(security, value)


# ＝ open_position ＝
def open_position(context, security, value):
    order = order_target_value_(security, value)
    if order and order.filled > 0:
        push_order_msg(
            symbol=security,
            name=get_security_info(security).display_name,
            side='BUY',
            volume=order.filled,
            price=order.price,
            order_id=order.order_id,          # ← 修改这里
            strategy_name="牛市板块快速轮动",
            extra=f"剩余现金 {context.portfolio.cash:.0f}"
        )
        g.today_bought.append(security)
        return True
    return False


# ＝ close_position ＝
def close_position(context, position):
    order = order_target_value_(position.security, 0)
    if position.security in g.today_bought:
        return False
    if order and order.filled > 0:
        profit = (position.price / position.avg_cost - 1) * 100
        push_order_msg(
            symbol=position.security,
            name=get_security_info(position.security).display_name,
            side='SELL',
            volume=order.filled,
            price=order.price,
            order_id=order.order_id,          # ← 以及这里
            strategy_name="牛市板块快速轮动",
            extra=f"收益 {profit:.2f}%"
        )
        return order.status == OrderStatus.held and order.filled == order.amount
    return False



# ================ 4. 打印持仓 ===================
def print_position_info(context):
    for t in get_trades().values():
        print('成交记录:', t)
    for p in context.portfolio.positions.values():
        ret = (p.price / p.avg_cost - 1) * 100
        print(f"{p.security} 成本{p.avg_cost:.2f} 现价{p.price:.2f} "
              f"收益{ret:.2f}% 持仓{p.total_amount} 市值{p.value:.0f}")
    print('-----------------------------')
