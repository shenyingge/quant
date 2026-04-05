#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试QMT交易功能"""

import json
import time

from src.config import settings
from src.trading.execution.qmt_trader import QMTTrader


def test_qmt_trading():
    """测试QMT交易功能"""
    print("=== QMT交易功能测试 ===")

    # 初始化QMTTrader
    trader = QMTTrader()

    try:
        # 连接QMT
        print("1. 连接QMT...")
        if not trader.connect():
            print("FAIL QMT连接失败")
            return
        print("OK QMT连接成功")

        # 构造测试交易信号
        test_signal = {
            "stock_code": "000001",  # 平安银行
            "direction": "BUY",
            "volume": 100,  # 1手
            "price": 10.50,  # 限价单
        }

        print(f"2. 测试下单功能...")
        print(f"   测试信号: {test_signal}")

        # 测试异步下单
        order_id = trader.place_order(test_signal)
        if order_id:
            print(f"OK 下单成功，订单ID: {order_id}")

            # 等待几秒让回调执行
            print("3. 等待QMT回调响应...")
            time.sleep(3)

            # 检查订单状态
            print("4. 查询订单状态...")
            status = trader.get_order_status(order_id)
            if status:
                print(f"OK 订单状态: {status}")
            else:
                print("⚠️  无法查询订单状态（可能是序列号格式）")

            # 显示待处理订单
            pending_orders = trader.get_pending_orders_info()
            print(f"5. 当前待处理订单数: {len(pending_orders)}")
            for order in pending_orders:
                print(
                    f"   - {order['order_id']}: {order['stock_code']} {order['direction']} {order['volume']}股"
                )

            # 如果订单还在处理中，测试撤单
            if len(pending_orders) > 0:
                print("6. 测试撤单功能...")
                cancel_result = trader.cancel_order(order_id)
                if cancel_result:
                    print("OK 撤单成功")
                else:
                    print("⚠️  撤单失败或不支持")
        else:
            print("FAIL 下单失败")

        # 显示交易统计
        print("7. 交易统计信息:")
        stats = trader.get_trading_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")

        # 测试持仓查询
        print("8. 查询持仓信息...")
        positions = trader.get_positions()
        if positions:
            print(f"OK 当前持仓 ({len(positions)} 个):")
            for pos in positions[:5]:  # 只显示前5个
                print(f"   - {pos['stock_code']}: {pos['volume']}股 @ {pos['avg_price']}元")
        else:
            print("📊 暂无持仓或查询失败")

    except Exception as e:
        print(f"ERROR 测试过程中发生错误: {e}")
    finally:
        # 断开连接
        print("9. 断开QMT连接...")
        trader.disconnect()
        print("OK 测试完成")


if __name__ == "__main__":
    test_qmt_trading()
