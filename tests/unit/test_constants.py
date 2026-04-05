#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 QMT 常量系统
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.trading.qmt_constants import (
    OrderStatus,
    get_status_code,
    get_status_name,
    is_filled_status,
    is_finished_status,
    is_pending_status,
)


def test_constants():
    """测试常量系统"""
    print("=== 测试 QMT 常量系统 ===")

    # 测试状态判断函数
    print("\n1. 测试状态判断函数:")

    test_cases = [
        ("已成交", "成交状态", is_filled_status, True),
        ("部分成交", "成交状态", is_filled_status, True),
        ("已报", "成交状态", is_filled_status, False),
        ("已成交", "完成状态", is_finished_status, True),
        ("已撤销", "完成状态", is_finished_status, True),
        ("废单", "完成状态", is_finished_status, True),
        ("已报", "完成状态", is_finished_status, False),
        ("已报", "待处理状态", is_pending_status, True),
        ("已确认", "待处理状态", is_pending_status, True),
        ("部分成交", "待处理状态", is_pending_status, True),
        ("已成交", "待处理状态", is_pending_status, False),
    ]

    for status, desc, func, expected in test_cases:
        result = func(status)
        status_mark = "PASS" if result == expected else "FAIL"
        print(f"  {status_mark} {status} 是否为{desc}: {result} (预期: {expected})")

    # 测试状态列表获取
    print("\n2. 测试状态列表:")
    print(f"  成交状态: {OrderStatus.get_filled_statuses()}")
    print(f"  完成状态: {OrderStatus.get_finished_statuses()}")
    print(f"  待处理状态: {OrderStatus.get_pending_statuses()}")

    # 测试状态代码映射
    print("\n3. 测试状态代码映射:")
    test_statuses = ["已成交", "已撤销", "已报", "未知状态"]
    for status in test_statuses:
        code = get_status_code(status)
        name = get_status_name(code)
        print(f"  {status} -> {code} -> {name}")

    # 测试常量值
    print("\n4. 测试常量值:")
    print(f"  ORDER_SUCCEEDED: {OrderStatus.SUCCEEDED}")
    print(f"  ORDER_CANCELED: {OrderStatus.CANCELED}")
    print(f"  ORDER_REPORTED: {OrderStatus.REPORTED}")


def test_integration_with_notification_fix():
    """测试与通知修复的集成"""
    print("\n=== 测试与通知修复的集成 ===")

    # 重新运行通知修复测试，但使用常量
    scenarios = [
        {"name": "未成交订单", "order_status": "已报", "filled_volume": 0, "should_notify": False},
        {
            "name": "部分成交订单",
            "order_status": "部分成交",
            "filled_volume": 50,
            "should_notify": False,
        },
        {
            "name": "完全成交订单",
            "order_status": "已成交",
            "filled_volume": 100,
            "should_notify": True,
        },
        {"name": "撤销订单", "order_status": "已撤销", "filled_volume": 0, "should_notify": False},
    ]

    for scenario in scenarios:
        print(f"\n--- {scenario['name']} ---")
        current_status = scenario["order_status"]
        filled_volume = scenario["filled_volume"]
        order_volume = 100

        # 使用常量函数检查成交状态
        has_fill = is_filled_status(current_status) or filled_volume > 0

        if has_fill and filled_volume > 0:
            print(f"OK 检测到成交: {filled_volume} (使用常量函数)")
            if filled_volume >= order_volume:
                should_notify = True
                print(f"OK 完全成交，应该发送通知")
            else:
                should_notify = False
                print(f"- 部分成交，不发送通知")
        else:
            should_notify = False
            print(f"- 无成交或状态不符合 (使用常量函数)")

        # 验证结果
        expected = scenario["should_notify"]
        if should_notify == expected:
            print(f"PASS 测试通过: 常量系统工作正常")
        else:
            print(f"FAIL 测试失败: 预期={expected}, 实际={should_notify}")


if __name__ == "__main__":
    test_constants()
    test_integration_with_notification_fix()
    print("\n常量系统测试完成！")
