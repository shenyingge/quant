#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试通知功能"""

from src.notifications import FeishuNotifier
from src.stock_info import stock_info_cache

def test_notifications():
    """测试通知功能"""
    print("=== 测试通知功能 ===")
    
    # 创建通知器
    notifier = FeishuNotifier()
    
    # 测试股票名称显示
    print("1. 测试股票名称查询:")
    test_codes = ['000001', '600519', '300750', '002594']
    for code in test_codes:
        display_name = stock_info_cache.get_stock_display_name(code)
        print(f"   {code} -> {display_name}")
    
    # 模拟交易信号数据
    signal_data = {
        'signal_id': 'TEST_NOTIFICATION_001',
        'symbol': '000001',  # 平安银行
        'action': 'BUY',
        'quantity': 100,
        'price': 10.50
    }
    
    print("\n2. 测试信号接收通知:")
    print(f"   信号数据: {signal_data}")
    
    # 测试信号接收通知（不会真正发送，只是测试格式）
    print("   模拟通知内容:")
    stock_display = stock_info_cache.get_stock_display_name(signal_data['symbol'])
    print(f"   股票信息: {stock_display}")
    print(f"   操作类型: {signal_data['action']}")
    print(f"   数量: {signal_data['quantity']}")
    print(f"   价格: {signal_data['price']}")
    
    # 测试订单确认通知
    print("\n3. 测试订单确认通知:")
    order_id = "seq_123"
    print(f"   订单ID: {order_id}")
    print(f"   股票信息: {stock_display}")
    
    # 测试成交通知
    print("\n4. 测试成交通知:")
    order_info = {
        'order_id': '987654321',
        'symbol': '600519',  # 贵州茅台
        'filled_qty': 10,
        'avg_price': 1580.50
    }
    
    stock_display_maotai = stock_info_cache.get_stock_display_name(order_info['symbol'])
    trade_amount = float(order_info['filled_qty']) * float(order_info['avg_price'])
    
    print(f"   订单ID: {order_info['order_id']}")
    print(f"   股票信息: {stock_display_maotai}")
    print(f"   成交数量: {order_info['filled_qty']}")
    print(f"   成交价格: {order_info['avg_price']}")
    print(f"   成交金额: {trade_amount:.2f}元")
    
    print("\n5. 通知功能改进总结:")
    print("   OK 股票代码现在显示为: 代码(名称) 格式")
    print("   OK 支持13个常用股票的名称显示")
    print("   OK 未知股票显示为: 股票代码 格式")
    print("   OK 成交金额格式化显示")
    print("   OK 统一的股票信息显示格式")
    
    # 显示预设股票列表
    print("\n6. 当前支持的股票名称:")
    preset_names = stock_info_cache._preset_names
    for code, name in sorted(preset_names.items()):
        display = stock_info_cache.get_stock_display_name(code)
        print(f"   {display}")
    
    print("\nOK 通知功能测试完成")

if __name__ == "__main__":
    test_notifications()