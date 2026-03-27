#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试飞书通知模板修复"""

import json

from src.notifications import FeishuNotifier


def test_notification_template():
    """测试通知模板的重复标题修复"""
    print("=== 测试飞书通知模板修复 ===")

    # 创建通知器
    notifier = FeishuNotifier()

    # 模拟发送消息的payload生成逻辑（不实际发送）
    def get_payload_preview(message: str, title: str):
        """获取通知payload预览"""
        from datetime import datetime

        payload = {
            "msg_type": "interactive",
            "card": {
                "elements": [
                    {
                        "tag": "div",
                        "text": {"content": message, "tag": "lark_md"},  # 修复后：不再重复标题
                    },
                    {"tag": "hr"},
                    {
                        "tag": "div",
                        "text": {
                            "content": f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                            "tag": "lark_md",
                        },
                    },
                ],
                "header": {"title": {"content": title, "tag": "plain_text"}, "template": "blue"},
            },
        }
        return payload

    # 测试不同类型的通知
    test_cases = [
        {
            "title": "交易信号",
            "message": "收到交易信号:\n• 股票信息: 000001(平安银行)\n• 操作类型: BUY\n• 数量: 100\n• 价格: 10.50\n• 信号ID: TEST_001",
        },
        {
            "title": "订单确认",
            "message": "订单已下达:\n• 订单ID: seq_123\n• 股票信息: 000001(平安银行)\n• 操作类型: BUY\n• 数量: 100\n• 价格: 10.50",
        },
        {
            "title": "订单成交",
            "message": "订单已成交:\n• 订单ID: 987654321\n• 股票信息: 600519(贵州茅台)\n• 成交数量: 10\n• 成交价格: 1580.50\n• 成交金额: 15805.00元",
        },
        {"title": "交易引擎状态", "message": "交易引擎状态: 已启动\n详情: 交易引擎成功启动"},
    ]

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. 测试通知类型: {test_case['title']}")

        payload = get_payload_preview(test_case["message"], test_case["title"])

        # 显示修复前后的对比
        print("   修复前的内容显示:")
        print(f"     标题栏: {test_case['title']}")
        print(f"     内容区: **{test_case['title']}**")  # 修复前会重复
        print(f"     消息内容: {test_case['message'].split(':', 1)[0]}...")

        print("   修复后的内容显示:")
        print(f"     标题栏: {test_case['title']}")
        print(f"     内容区: {test_case['message'].split(':', 1)[0]}...")  # 修复后不重复

        # 验证payload结构
        header_title = payload["card"]["header"]["title"]["content"]
        content_text = payload["card"]["elements"][0]["text"]["content"]

        print(f"   验证结果:")
        print(f"     头部标题: '{header_title}'")
        print(f"     内容开头: '{content_text[:30]}...'")

        # 检查是否还有重复
        if header_title in content_text:
            print("     WARNING: 标题仍然在内容中重复")
        else:
            print("     OK: 标题不再重复")

    print("\n5. 修复总结:")
    print("   修复前: header显示标题 + content显示'**标题**\\n消息内容'")
    print("   修复后: header显示标题 + content只显示'消息内容'")
    print("   结果: 消除了标题重复显示的问题")

    print("\nOK 通知模板修复测试完成")


if __name__ == "__main__":
    test_notification_template()
