#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试序列号委托的超时处理机制"""

import json
import time

from src.config import settings
from src.trader import QMTTrader


def test_timeout_handling():
    """测试序列号委托超时处理"""
    print("=== 测试序列号委托超时处理 ===")

    trader = QMTTrader()

    try:
        # 连接QMT
        print("1. 连接QMT...")
        if not trader.connect():
            print("FAIL QMT连接失败")
            return
        print("OK QMT连接成功")

        # 显示回调注册信息
        print("2. 回调注册状态:")
        print(f"   回调对象: {trader.callback is not None}")
        if trader.callback:
            callback_methods = [m for m in dir(trader.callback) if m.startswith("on_")]
            print(f"   回调方法: {callback_methods}")

        # 构造测试信号（使用较短超时时间进行测试）
        test_signal = {"stock_code": "000001", "direction": "BUY", "volume": 100, "price": 9.50}

        # 临时修改超时时间为15秒以便快速测试
        original_timeout = settings.order_timeout_seconds
        settings.order_timeout_seconds = 15
        print(f"3. 临时设置订单超时时间为 {settings.order_timeout_seconds} 秒")

        print(f"4. 提交测试订单: {test_signal}")
        order_id = trader.place_order(test_signal)

        if order_id:
            print(f"OK 订单已提交: {order_id}")

            # 显示当前待处理订单
            pending = trader.get_pending_orders_info()
            print(f"5. 当前待处理订单: {len(pending)} 个")
            for order in pending:
                print(f"   - {order['order_id']}: {order['stock_code']} {order['direction']}")

            # 等待超时发生
            print(f"6. 等待 {settings.order_timeout_seconds + 5} 秒观察超时处理...")
            for i in range(settings.order_timeout_seconds + 5):
                time.sleep(1)
                remaining_orders = trader.get_pending_orders_count()
                if remaining_orders == 0:
                    print(f"   第 {i+1} 秒: 订单已被处理，剩余 {remaining_orders} 个")
                    break
                elif i % 5 == 4:  # 每5秒显示一次状态
                    print(f"   第 {i+1} 秒: 剩余订单 {remaining_orders} 个")

            # 检查最终状态
            final_pending = trader.get_pending_orders_count()
            if final_pending == 0:
                print("OK 超时订单已被正确处理和移除")
            else:
                print(f"WARNING 仍有 {final_pending} 个订单待处理")
                final_orders = trader.get_pending_orders_info()
                for order in final_orders:
                    print(f"   - 剩余: {order['order_id']} ({order['elapsed_seconds']:.1f}秒)")

        else:
            print("FAIL 订单提交失败")

        # 恢复原始超时设置
        settings.order_timeout_seconds = original_timeout
        print(f"7. 恢复原始超时时间: {original_timeout} 秒")

        # 显示交易统计
        print("8. 最终交易统计:")
        stats = trader.get_trading_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")

    except Exception as e:
        print(f"ERROR 测试异常: {e}")
    finally:
        print("9. 断开连接...")
        trader.disconnect()
        print("OK 测试完成")


if __name__ == "__main__":
    test_timeout_handling()
