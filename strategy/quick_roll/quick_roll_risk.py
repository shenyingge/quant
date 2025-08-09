# 克隆自聚宽文章：https://www.joinquant.com/post/50995
# 修改：集成飞书通知、修复 numpy.sum 冲突、修正 context 作用域、添加组合层风险控制
# 日期：2025-08-09

from jqdata import *
from jqfactor import get_factor_values
from itertools import chain
import pandas as pd
import numpy as np
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

    # ========= 原始参数 =========
    g.stock_num  = 10     # 最大持仓数
    g.limit_days = 20     # 回避最近 N 天已买过的票
    g.limit_up_list = []
    g.hold_list      = []
    g.history_hold_list = []
    g.not_buy_again_list = []
    g.today_bought = []

    # ========= 风控参数 =========
    # 1. 回撤控制
    g.risk_state = 'NORMAL'  # NORMAL/REDUCE1/REDUCE2/EXIT
    g.dd_thresholds = {
        'REDUCE1': 0.10,  # 10%回撤降仓到50%
        'REDUCE2': 0.15,  # 15%回撤降仓到30%
        'EXIT': 0.20      # 20%回撤清仓
    }
    g.position_scale = {
        'NORMAL': 1.0,
        'REDUCE1': 0.5,
        'REDUCE2': 0.3,
        'EXIT': 0.0
    }
    g.pause_days = {
        'REDUCE1': 3,
        'REDUCE2': 5,
        'EXIT': 10
    }
    g.pause_until = None  # 暂停买入截止日期

    # 2. 波动率目标
    g.vol_target = 0.15  # 目标年化波动率15%
    g.vol_lookback = 20  # 滚动天数
    g.vol_exposure = 1.0  # 波动率调整系数
    g.daily_returns = []  # 存储每日收益率

    # 3. 市场择时
    g.market_exposure = 1.0  # 市场择时系数
    g.timing_indices = ['000905.XSHG', '000300.XSHG', '399006.XSHE']  # 中证500/沪深300/创业板
    g.weak_market_days = 0  # 弱势市场天数计数

    # 4. 峰值追踪
    g.portfolio_peak = context.portfolio.total_value
    g.current_drawdown = 0.0

    run_daily(update_risk_metrics,  time='9:00', reference_security='000300.XSHG')
    run_daily(prepare_stock_list,  time='9:05', reference_security='000300.XSHG')
    run_weekly(weekly_adjustment,  weekday=1, time='9:40', reference_security='000300.XSHG')
    run_daily(check_limit_up,      time='11:00', reference_security='000300.XSHG')
    run_daily(print_position_info, time='15:10', reference_security='000300.XSHG')
    run_daily(stop_loss_check, time='14:30', reference_security='000300.XSHG')
    run_daily(update_daily_return, time='15:00', reference_security='000300.XSHG')

# ================ 风险管理模块 ================

def update_risk_metrics(context):
    """每日更新风险指标"""
    # 1. 更新组合峰值和回撤
    current_value = context.portfolio.total_value
    if current_value > g.portfolio_peak:
        g.portfolio_peak = current_value

    g.current_drawdown = (g.portfolio_peak - current_value) / g.portfolio_peak

    # 2. 更新风险状态（增加EXIT恢复机制）
    old_state = g.risk_state

    # 先检查是否可以恢复
    if g.risk_state == 'EXIT':
        # EXIT状态恢复条件：回撤收窄到18%以下，且暂停期已过，且市场转好
        if g.current_drawdown < 0.18:
            if g.pause_until and context.current_dt >= g.pause_until:
                # 检查市场是否转好
                index = '000300.XSHG'
                close = get_price(index, count=20, end_date=context.previous_date, frequency='daily')['close']
                if close[-3:].mean() > close[-20:].mean():  # 近3日均线高于20日均线
                    g.risk_state = 'REDUCE2'
                    g.pause_until = None
                    send_msg(f"✅ 风险缓解，从清仓恢复到二级减仓，回撤{g.current_drawdown:.1%}")
    elif g.risk_state == 'REDUCE2':
        if g.current_drawdown < 0.12:
            g.risk_state = 'REDUCE1'
            g.pause_until = None
            send_msg(f"✅ 风险继续缓解，恢复到一级减仓")
    elif g.risk_state == 'REDUCE1':
        if g.current_drawdown < 0.08:
            g.risk_state = 'NORMAL'
            g.pause_until = None
            send_msg(f"✅ 风险解除，恢复正常交易")

    # 再检查是否需要加码风控
    if g.current_drawdown >= g.dd_thresholds['EXIT'] and g.risk_state != 'EXIT':
        g.risk_state = 'EXIT'
        g.pause_until = context.current_dt + datetime.timedelta(days=g.pause_days['EXIT'])
        send_msg(f"⚠️ 触发清仓线！回撤{g.current_drawdown:.1%}，暂停买入{g.pause_days['EXIT']}天")
    elif g.current_drawdown >= g.dd_thresholds['REDUCE2'] and g.risk_state not in ['REDUCE2', 'EXIT']:
        g.risk_state = 'REDUCE2'
        g.pause_until = context.current_dt + datetime.timedelta(days=g.pause_days['REDUCE2'])
        send_msg(f"⚠️ 触发二级减仓！回撤{g.current_drawdown:.1%}，降仓到30%")
    elif g.current_drawdown >= g.dd_thresholds['REDUCE1'] and g.risk_state == 'NORMAL':
        g.risk_state = 'REDUCE1'
        g.pause_until = context.current_dt + datetime.timedelta(days=g.pause_days['REDUCE1'])
        send_msg(f"⚠️ 触发一级减仓！回撤{g.current_drawdown:.1%}，降仓到50%")

    # 3. 计算波动率调整系数
    if len(g.daily_returns) >= g.vol_lookback:
        recent_returns = g.daily_returns[-g.vol_lookback:]
        daily_vol = np.std(recent_returns)
        annual_vol = daily_vol * np.sqrt(252)
        if annual_vol > 0.01:  # 避免除零
            g.vol_exposure = np.clip(g.vol_target / annual_vol, 0.3, 1.0)
        else:
            g.vol_exposure = 1.0

    # 4. 更新市场择时
    update_market_timing(context)

    # 记录风控状态
    log.info(f"风控状态: {g.risk_state}, 回撤: {g.current_drawdown:.2%}, "
             f"波动率调整: {g.vol_exposure:.2f}, 市场择时: {g.market_exposure:.2f}")


def update_market_timing(context):
    """更新市场择时系数"""
    weak_count = 0
    strong_count = 0

    for index in g.timing_indices:
        df = get_price(index, count=60, end_date=context.previous_date,
                      frequency='daily', fields=['close'])
        ma20 = df['close'][-20:].mean()
        ma60 = df['close'].mean()
        current = df['close'][-1]

        if current < ma60:
            weak_count += 1
        if current > ma20:
            strong_count += 1

    # 计算涨跌家数比（简化版：用中证500成分股代替）
    stocks = get_index_stocks('000905.XSHG')[:100]  # 取前100只避免太慢
    df = get_price(stocks, count=1, end_date=context.previous_date,
                  frequency='daily', fields=['close', 'pre_close'], panel=False)
    if not df.empty:
        up_count = (df['close'] > df['pre_close']).sum()
        down_count = (df['close'] < df['pre_close']).sum()
        advance_decline_ratio = up_count / max(down_count, 1)
    else:
        advance_decline_ratio = 1.0

    # 判断市场状态（不再直接设置EXIT，避免死锁）
    old_exposure = g.market_exposure
    if weak_count >= 2 and advance_decline_ratio < 0.6:
        g.market_exposure = 0.5
        g.weak_market_days += 1
        if weak_count == 3 and g.risk_state == 'NORMAL':  # 三个指数全弱，且当前正常状态
            g.risk_state = 'REDUCE2'  # 改为触发二级减仓而非清仓
            g.pause_until = context.current_dt + datetime.timedelta(days=g.pause_days['REDUCE2'])
            send_msg(f"⚠️ 市场极度弱势，触发二级减仓")
    elif strong_count >= 2:
        g.weak_market_days = 0
        g.market_exposure = 1.0  # 市场转强直接恢复

    if old_exposure != g.market_exposure:
        send_msg(f"市场择时调整: {old_exposure:.1f} -> {g.market_exposure:.1f}")


def update_daily_return(context):
    """记录每日收益率"""
    if len(g.daily_returns) == 0:
        g.daily_returns.append(0)
    else:
        prev_value = context.portfolio.total_value / (1 + context.portfolio.returns)
        daily_return = (context.portfolio.total_value - prev_value) / prev_value
        g.daily_returns.append(daily_return)

        # 保留最近60天数据
        if len(g.daily_returns) > 60:
            g.daily_returns = g.daily_returns[-60:]


def calculate_total_exposure(context):
    """计算总体风险敞口"""
    base_exposure = g.position_scale[g.risk_state]
    total_exposure = base_exposure * g.vol_exposure * g.market_exposure

    # 如果在暂停期内且是EXIT状态，禁止新开仓
    # 其他状态的暂停期可以考虑逐步恢复
    if g.risk_state == 'EXIT' and g.pause_until and context.current_dt < g.pause_until:
        total_exposure = 0
    elif g.risk_state in ['REDUCE1', 'REDUCE2'] and g.pause_until and context.current_dt < g.pause_until:
        # 减仓状态下，暂停期内允许小仓位试探
        total_exposure = min(total_exposure, 0.1)  # 最多10%仓位

    return np.clip(total_exposure, 0, 1)


def is_market_ok(context):
    """原市场判断函数，现在结合风控状态"""
    if g.risk_state == 'EXIT':
        return False

    index = '000300.XSHG'
    close = get_price(index, count=20, end_date=context.previous_date, frequency='daily')['close']
    basic_ok = close[-5:].mean() > close.mean()

    # 结合风控状态
    return basic_ok and g.market_exposure > 0.5



# ================ 1. 选股逻辑 ================
def get_factor_filter_list(context, stock_list, jqfactor, ascend, p1, p2):
    y = context.previous_date
    scores = get_factor_values(stock_list, jqfactor, end_date=y, count=1)[jqfactor].iloc[0]
    df = pd.DataFrame({'code': stock_list, 'score': scores})
    df.dropna(inplace=True)
    df.sort_values('score', ascending=ascend, inplace=True)
    return df.code.tolist()[int(p1*len(df)): int(p2*len(df))]


def stop_loss_check(context):
    """个股止损 + 风控状态下的强制减仓"""
    send_msg("stop loss check")

    # 1. 个股止损
    for position in context.portfolio.positions.values():
        current_price = position.price
        avg_cost = position.avg_cost
        if avg_cost > 0 and current_price / avg_cost < 0.9:  # 跌超10%
            log.info(f"止损触发：{position.security} 当前价{current_price:.2f}  成本{avg_cost:.2f}")
            close_position(context, position)

    # 2. 风控状态下的强制减仓
    if g.risk_state == 'EXIT':
        # 清仓所有持仓
        for position in context.portfolio.positions.values():
            close_position(context, position)
        send_msg("执行清仓")
    elif g.risk_state in ['REDUCE1', 'REDUCE2']:
        # 按比例减仓
        target_value = context.portfolio.total_value * g.position_scale[g.risk_state]
        current_position_value = context.portfolio.positions_value

        if current_position_value > target_value * 1.1:  # 留10%缓冲
            reduce_ratio = 1 - (target_value / current_position_value)
            for position in context.portfolio.positions.values():
                target = position.value * (1 - reduce_ratio)
                order_target_value(position.security, target)
            send_msg(f"风控减仓，目标仓位{g.position_scale[g.risk_state]:.0%}")

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
    send_msg(f"prepare stock list [风控:{g.risk_state} 敞口:{calculate_total_exposure(context):.1%}]")
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
    total_exposure = calculate_total_exposure(context)
    send_msg(f'weekly adjust [总敞口:{total_exposure:.1%}]')

    # 风控状态为EXIT且在暂停期内，只卖不买
    if g.risk_state == 'EXIT' and g.pause_until and context.current_dt < g.pause_until:
        log.info("风控EXIT状态暂停期内，禁止买入")
        # 仍然执行卖出逻辑
        targets = get_stock_list(context)
        for s in g.hold_list:
            if s not in targets and s not in g.limit_up_list:
                close_position(context, context.portfolio.positions[s])
        return

    # 如果总敞口为0，也只卖不买
    if total_exposure <= 0:
        log.info(f"总敞口为0，只卖不买")
        return

    targets = get_stock_list(context)
    targets = filter_paused_stock(targets)
    targets = filter_limitup_stock(context, targets)
    targets = filter_limitdown_stock(context, targets)
    targets = filter_paused_stock(targets)

    recent = get_recent_limit_up_stock(context, targets, g.limit_days)
    blacklist = set(g.not_buy_again_list) & set(recent)

    # 根据风控调整目标股票数
    adjusted_stock_num = int(g.stock_num * total_exposure)
    adjusted_stock_num = max(adjusted_stock_num, 3)  # 至少保留3只

    targets = [s for s in targets if s not in blacklist][:adjusted_stock_num]

    # 卖出
    for s in g.hold_list:
        if s not in targets and s not in g.limit_up_list:
            close_position(context, context.portfolio.positions[s])

    # 买入（应用风控调整）
    need_buy = len(targets) - len(context.portfolio.positions)
    if need_buy > 0 and total_exposure > 0:
        # 计算每只股票的买入金额，考虑风控调整
        available_cash = context.portfolio.cash * total_exposure
        cash_per = available_cash / need_buy

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
            order_id=order.order_id,
            strategy_name="牛市板块快速轮动(风控版)",
            extra=f"剩余现金 {context.portfolio.cash:.0f} 风控:{g.risk_state}"
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
            order_id=order.order_id,
            strategy_name="牛市板块快速轮动(风控版)",
            extra=f"收益 {profit:.2f}% 风控:{g.risk_state}"
        )
        return order.status == OrderStatus.held and order.filled == order.amount
    return False



# ================ 4. 打印持仓 ===================
def print_position_info(context):
    """打印持仓信息和风控状态"""
    print(f"========= 风控状态 =========")
    print(f"风险等级: {g.risk_state}")
    print(f"当前回撤: {g.current_drawdown:.2%}")
    print(f"波动率调整: {g.vol_exposure:.2f}")
    print(f"市场择时: {g.market_exposure:.2f}")
    print(f"总敞口: {calculate_total_exposure(context):.1%}")

    if g.pause_until:
        days_left = (g.pause_until - context.current_dt).days
        print(f"暂停买入剩余: {days_left}天")

    print(f"========= 持仓明细 =========")
    for t in get_trades().values():
        print('成交记录:', t)
    for p in context.portfolio.positions.values():
        ret = (p.price / p.avg_cost - 1) * 100
        print(f"{p.security} 成本{p.avg_cost:.2f} 现价{p.price:.2f} "
              f"收益{ret:.2f}% 持仓{p.total_amount} 市值{p.value:.0f}")

    print(f"总市值: {context.portfolio.total_value:.0f}")
    print(f"持仓市值: {context.portfolio.positions_value:.0f}")
    print(f"可用现金: {context.portfolio.cash:.0f}")
    print(f"仓位比例: {context.portfolio.positions_value/context.portfolio.total_value:.1%}")
    print('-----------------------------')
