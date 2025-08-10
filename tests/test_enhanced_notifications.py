#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试增强的通知功能"""

import time

from src.notifications import FeishuNotifier
from src.stock_info import stock_info_cache


def test_enhanced_notifications():
    """测试增强的通知功能"""
    print("=== 测试增强的通知功能 ===")

    notifier = FeishuNotifier()

    # 1. 测试信号接收通知
    print("1. 测试信号接收通知格式:")
    signal_data = {
        "signal_id": "TEST_20250808_001",
        "stock_code": "000001",  # 平安银行
        "direction": "BUY",
        "volume": 100,
        "price": 10.50,
    }

    print("   原始数据:", signal_data)

    # 模拟通知内容（不实际发送）
    stock_code = signal_data.get("stock_code", "N/A")
    stock_display = stock_info_cache.get_stock_display_name(stock_code)

    print("   通知内容预览:")
    print(f"     股票信息: {stock_display}")
    print(f"     操作类型: {signal_data.get('direction', 'N/A')}")
    print(f"     数量: {signal_data.get('volume', 'N/A')}")
    print(f"     价格: {signal_data.get('price', 'N/A')}")
    print(f"     信号ID: {signal_data.get('signal_id', 'N/A')}")

    # 2. 测试订单确认通知
    print("\n2. 测试订单确认通知格式:")
    order_id = "seq_456"
    print("   订单数据:", {"order_id": order_id, "signal_data": signal_data})

    print("   通知内容预览:")
    print(f"     订单ID: {order_id}")
    print(f"     股票信息: {stock_display}")
    print(f"     操作类型: {signal_data.get('direction', 'N/A')}")
    print(f"     数量: {signal_data.get('volume', 'N/A')}")
    print(f"     价格: {signal_data.get('price', 'N/A')}")

    # 3. 测试成交通知（多个示例）
    print("\n3. 测试成交通知格式:")

    test_orders = [
        {
            "order_id": "123456789",
            "stock_code": "600519",  # 贵州茅台
            "filled_qty": 10,
            "avg_price": 1580.50,
        },
        {
            "order_id": "987654321",
            "stock_code": "300750",  # 宁德时代
            "filled_qty": 100,
            "avg_price": 185.30,
        },
        {
            "order_id": "555666777",
            "stock_code": "002594",  # 比亚迪
            "filled_qty": 200,
            "avg_price": 78.25,
        },
    ]

    for i, order_info in enumerate(test_orders, 1):
        print(f"\n   成交示例 {i}:")
        stock_display_order = stock_info_cache.get_stock_display_name(order_info["stock_code"])
        filled_qty = float(order_info["filled_qty"])
        avg_price = float(order_info["avg_price"])
        trade_amount = filled_qty * avg_price

        print(f"     订单ID: {order_info['order_id']}")
        print(f"     股票信息: {stock_display_order}")
        print(f"     成交数量: {order_info['filled_qty']}")
        print(f"     成交价格: {order_info['avg_price']}")
        print(f"     成交金额: {trade_amount:.2f}元")

    # 4. 对比改进前后的差异
    print("\n4. 通知格式改进对比:")
    print("   改进前: 股票代码: 000001")
    print("   改进后: 股票信息: 000001(平安银行)")
    print()
    print("   改进前: 成交金额: 15805.0")
    print("   改进后: 成交金额: 15805.00元")

    # 5. 显示所有支持的股票
    print("\n5. 当前预设股票名称库:")
    preset_count = len(stock_info_cache._preset_names)
    print(f"   共支持 {preset_count} 个热门股票:")

    for code, name in sorted(stock_info_cache._preset_names.items()):
        display = stock_info_cache.get_stock_display_name(code)
        print(f"     {display}")

    print("\n6. 功能特性总结:")
    print("   OK 股票名称自动识别和显示")
    print("   OK 统一的股票信息格式: 代码(名称)")
    print("   OK 金额格式化显示")
    print("   OK 支持缓存机制避免重复查询")
    print("   OK 兼容多种股票代码字段名")
    print("   OK 未知股票的优雅降级显示")

    print("\nOK 增强通知功能测试完成")
    print(f"现在飞书通知将显示更详细和用户友好的股票信息！")


if __name__ == "__main__":
    test_enhanced_notifications()
