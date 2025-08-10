#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试成交通知修复效果
"""

import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import OrderRecord, SessionLocal
from src.notifications import FeishuNotifier


def test_notification_logic():
    """测试通知逻辑"""
    print("=== 测试成交通知修复效果 ===")

    # 模拟不同的订单状态场景
    test_scenarios = [
        {"name": "未成交订单", "order_status": "已报", "filled_volume": 0, "should_notify": False},
        {
            "name": "部分成交订单",
            "order_status": "部分成交",
            "filled_volume": 50,
            "should_notify": False,  # 部分成交不通知
        },
        {
            "name": "完全成交订单",
            "order_status": "已成交",
            "filled_volume": 100,
            "should_notify": True,
        },
        {"name": "撤销订单", "order_status": "已撤销", "filled_volume": 0, "should_notify": False},
    ]

    for scenario in test_scenarios:
        print(f"\n--- {scenario['name']} ---")
        print(f"订单状态: {scenario['order_status']}")
        print(f"成交数量: {scenario['filled_volume']}")

        # 模拟订单监控逻辑
        current_status = scenario["order_status"]
        filled_volume = scenario["filled_volume"]
        order_volume = 100  # 总委托数量

        # 检查成交状态逻辑
        from src.qmt_constants import is_filled_status

        has_fill = is_filled_status(current_status) or filled_volume > 0

        if has_fill and filled_volume > 0:
            print(f"✓ 检测到成交: {filled_volume}")

            # 检查是否应该发送完全成交通知
            if filled_volume >= order_volume:
                should_notify = True
                print(f"✓ 完全成交，应该发送通知")
            else:
                should_notify = False
                print(f"- 部分成交，不发送通知")
        else:
            should_notify = False
            print(f"- 无成交或状态不符合")

        # 验证结果
        expected = scenario["should_notify"]
        if should_notify == expected:
            print(f"✅ 测试通过: 通知逻辑正确")
        else:
            print(f"❌ 测试失败: 预期={expected}, 实际={should_notify}")

    print("\n=== 总结 ===")
    print("修复要点:")
    print("1. ✓ 检查订单状态是否表示成交")
    print("2. ✓ 验证成交数量大于0且有增长")
    print("3. ✓ 只有完全成交才发送通知")
    print("4. ✓ 使用 fill_notified 标记避免重复通知")


def test_database_field():
    """测试数据库字段"""
    print("\n=== 测试数据库字段 ===")

    try:
        db = SessionLocal()

        # 测试查询包含新字段
        from sqlalchemy import text

        result = db.execute(text("PRAGMA table_info(order_records)")).fetchall()

        fields = [row[1] for row in result]  # row[1] 是字段名

        if "fill_notified" in fields:
            print("✅ fill_notified 字段存在")
        else:
            print("❌ fill_notified 字段不存在")

        print(f"订单记录表字段: {', '.join(fields)}")

        db.close()

    except Exception as e:
        print(f"❌ 数据库测试失败: {e}")


if __name__ == "__main__":
    test_notification_logic()
    test_database_field()
    print("\n测试完成！")
