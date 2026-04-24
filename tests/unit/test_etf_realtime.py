#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
临时测试脚本：获取513100（纳指ETF）的实时数据
测试 subscribe_whole_quote 接口获取实时PE等数据
"""

import time
from datetime import datetime
import xtquant.xtdata as xt_data


def on_data(datas):
    """实时行情回调函数"""
    print("\n" + "="*60)
    print(f"回调时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    for stock_code, data in datas.items():
        print(f"\n股票代码: {stock_code}")
        print(f"时间戳: {data.get('time', 'N/A')}")

        # 价格信息
        print(f"\n【价格信息】")
        print(f"  最新价: {data.get('lastPrice', 'N/A')}")
        print(f"  开盘价: {data.get('open', 'N/A')}")
        print(f"  最高价: {data.get('high', 'N/A')}")
        print(f"  最低价: {data.get('low', 'N/A')}")
        print(f"  昨收价: {data.get('lastClose', 'N/A')}")

        # 成交信息
        print(f"\n【成交信息】")
        print(f"  成交量: {data.get('volume', 'N/A')}")
        print(f"  成交额: {data.get('amount', 'N/A')}")
        print(f"  成交笔数: {data.get('transactionNum', 'N/A')}")

        # 估值信息（重点）
        print(f"\n【估值信息】")
        print(f"  市盈率PE: {data.get('pe', 'N/A')}")

        # 盘口信息
        print(f"\n【盘口信息】")
        print(f"  卖五价: {data.get('askPrice', [])}")
        print(f"  卖五量: {data.get('askVol', [])}")
        print(f"  买五价: {data.get('bidPrice', [])}")
        print(f"  买五量: {data.get('bidVol', [])}")

        # 其他信息
        print(f"\n【其他信息】")
        print(f"  量比: {data.get('volRatio', 'N/A')}")
        print(f"  1分钟涨速: {data.get('speed1Min', 'N/A')}")
        print(f"  5分钟涨速: {data.get('speed5Min', 'N/A')}")


def main():
    print("="*60)
    print("测试脚本：获取513100（纳指ETF）实时数据")
    print("="*60)

    # 连接xtquant
    print("\n正在连接xtquant...")
    try:
        xt_data.connect()
        print("✓ 连接成功")
    except Exception as e:
        print(f"✗ 连接失败: {e}")
        return

    # 订阅513100实时行情
    etf_code = "513100.SH"
    print(f"\n正在订阅 {etf_code} 实时行情...")

    try:
        seq = xt_data.subscribe_whole_quote([etf_code], on_data)
        print(f"✓ 订阅成功，订阅号: {seq}")
    except Exception as e:
        print(f"✗ 订阅失败: {e}")
        return

    # 运行30秒后退出
    print(f"\n开始接收实时数据，将运行30秒...")
    print("按 Ctrl+C 可提前退出\n")

    try:
        start_time = time.time()
        while time.time() - start_time < 30:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n用户中断")

    # 取消订阅
    print("\n正在取消订阅...")
    try:
        xt_data.unsubscribe_quote(seq)
        print("✓ 已取消订阅")
    except Exception as e:
        print(f"✗ 取消订阅失败: {e}")

    print("\n测试完成！")


if __name__ == "__main__":
    main()
