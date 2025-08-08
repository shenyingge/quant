#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试服务停止通知重复问题的修复"""

import time
import threading
from src.trading_service import TradingService

class MockFeishuNotifier:
    """模拟飞书通知器，用于测试"""
    def __init__(self):
        self.notifications = []
        
    def notify_service_status(self, status: str, message: str = "") -> bool:
        notification = {
            'type': 'service_status',
            'status': status,
            'message': message,
            'timestamp': time.time()
        }
        self.notifications.append(notification)
        print(f"[MOCK] 发送通知: {status} - {message}")
        return True
    
    def notify_signal_received(self, signal_data):
        return True
        
    def notify_order_placed(self, signal_data, order_id):
        return True
        
    def notify_order_filled(self, order_info):
        return True
        
    def notify_error(self, error_message, context=""):
        return True

def test_stop_notification_fix():
    """测试停止通知修复"""
    print("=== 测试服务停止通知重复问题修复 ===")
    
    # 创建交易服务
    service = TradingService()
    
    # 替换通知器为模拟版本
    mock_notifier = MockFeishuNotifier()
    service.notifier = mock_notifier
    
    print("1. 测试正常停止流程:")
    
    # 模拟服务运行状态
    service.is_running = True
    
    print("   第一次调用 stop()...")
    service.stop()
    
    print("   第二次调用 stop()（模拟重复调用）...")
    service.stop()
    
    # 检查通知次数
    stop_notifications = [n for n in mock_notifier.notifications if n['status'] == '已停止']
    
    print(f"\n2. 检查结果:")
    print(f"   总通知数: {len(mock_notifier.notifications)}")
    print(f"   停止通知数: {len(stop_notifications)}")
    print(f"   所有通知:")
    
    for i, notification in enumerate(mock_notifier.notifications, 1):
        print(f"     {i}. {notification['status']} - {notification['message']}")
    
    # 验证结果
    if len(stop_notifications) == 1:
        print("\n   OK 修复成功: 停止通知只发送了一次")
    else:
        print(f"\n   ERROR 问题仍存在: 停止通知发送了{len(stop_notifications)}次")
    
    print("\n3. 测试多次快速调用:")
    
    # 重置测试
    mock_notifier.notifications.clear()
    service.is_running = True
    
    # 模拟多次快速调用
    def call_stop():
        service.stop()
    
    threads = []
    for i in range(5):
        t = threading.Thread(target=call_stop)
        threads.append(t)
        t.start()
    
    # 等待所有线程完成
    for t in threads:
        t.join()
    
    stop_notifications = [n for n in mock_notifier.notifications if n['status'] == '已停止']
    
    print(f"   并发调用5次stop()后:")
    print(f"   停止通知数: {len(stop_notifications)}")
    
    if len(stop_notifications) == 1:
        print("   OK 并发测试通过: 仍然只发送了一次通知")
    else:
        print(f"   ERROR 并发测试失败: 发送了{len(stop_notifications)}次通知")
    
    print("\nOK 停止通知测试完成")

if __name__ == "__main__":
    test_stop_notification_fix()