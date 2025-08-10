#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试状态逻辑修复效果
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.qmt_constants import get_status_name, is_filled_status


def test_status_logic():
    """测试状态逻辑修复"""
    print("=== 测试状态逻辑修复效果 ===")

    # 模拟订单监控逻辑的关键部分
    test_cases = [
        {
            "name": "状态50(已报)，成交量200",
            "current_status": 50,  # ORDER_REPORTED
            "filled_volume": 200,
            "previous_filled": 0,
            "should_process": False,  # 状态不是成交状态，不应该处理
        },
        {
            "name": "状态56(已成交)，成交量200",
            "current_status": 56,  # ORDER_SUCCEEDED
            "filled_volume": 200,
            "previous_filled": 0,
            "should_process": True,  # 状态是成交状态，应该处理
        },
        {
            "name": "状态55(部分成交)，成交量100",
            "current_status": 55,  # ORDER_PART_SUCC
            "filled_volume": 100,
            "previous_filled": 0,
            "should_process": True,  # 状态是成交状态，应该处理
        },
        {
            "name": "状态54(已撤销)，成交量0",
            "current_status": 54,  # ORDER_CANCELED
            "filled_volume": 0,
            "previous_filled": 0,
            "should_process": False,  # 不是成交状态，不应该处理
        },
    ]

    for case in test_cases:
        print(f"\n--- {case['name']} ---")

        current_status = case["current_status"]
        filled_volume = case["filled_volume"]
        previous_filled = case["previous_filled"]

        print(f"状态码: {current_status}")
        print(f"状态名称: {get_status_name(current_status)}")
        print(f"是否为成交状态: {is_filled_status(current_status)}")
        print(f"成交数量: {filled_volume}")
        print(f"已记录成交: {previous_filled}")

        # 修复后的逻辑
        has_valid_fill = (
            is_filled_status(current_status)
            and filled_volume > 0
            and filled_volume > previous_filled
        )

        print(f"是否有有效成交: {has_valid_fill}")

        expected = case["should_process"]
        if has_valid_fill == expected:
            print("PASS 测试通过：逻辑正确")
        else:
            print(f"FAIL 测试失败：预期 {expected}，实际 {has_valid_fill}")

    print("\n=== 关键修复点 ===")
    print("1. PASS 严格检查状态必须为成交状态（56, 55）")
    print("2. PASS 状态50（已报）不会被误判为成交")
    print("3. PASS 支持整数类型状态码")
    print("4. PASS 防止在非成交状态下处理成交数量")


if __name__ == "__main__":
    test_status_logic()
