#!/usr/bin/env python
# coding=utf-8
import os
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parents[2]
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

import threading
import time

from config import settings
from trader import QMTTrader


def test_async_architecture():
    """测试异步交易架构"""
    print("Testing async trading architecture...")

    # 创建交易实例（不实际连接）
    trader = QMTTrader()

    # 检查关键组件
    print("Checking key components:")
    print(f"- xtquant_queue: {trader.xtquant_queue is not None}")
    print(f"- trade_executor: {trader.trade_executor is not None}")
    print(f"- xtquant_running: {trader.xtquant_running}")
    print(f"- trade_executor max_workers: {trader.trade_executor._max_workers}")

    # 测试队列操作（不需要实际连接QMT）
    print("\nTesting queue operations:")

    # 模拟启动xtquant线程
    trader._start_xtquant_thread()
    time.sleep(0.1)  # 让线程启动

    print(f"- xtquant_thread alive: {trader.xtquant_thread.is_alive()}")
    print(f"- xtquant_running: {trader.xtquant_running}")

    # 测试队列大小
    initial_size = trader.xtquant_queue.qsize()
    print(f"- Initial queue size: {initial_size}")

    # 添加一个测试任务
    test_callback_called = threading.Event()

    def test_callback(result):
        print(f"- Test callback received: {result}")
        test_callback_called.set()

    trader.xtquant_queue.put(("test", "test_data", test_callback))
    queue_size_after = trader.xtquant_queue.qsize()
    print(f"- Queue size after adding task: {queue_size_after}")

    # 等待一小段时间看是否处理
    time.sleep(0.2)
    final_size = trader.xtquant_queue.qsize()
    print(f"- Queue size after processing: {final_size}")

    # 关闭
    trader.xtquant_running = False
    trader.xtquant_queue.put(("shutdown", None, None))
    trader.xtquant_thread.join(timeout=2)

    print(f"- xtquant_thread alive after shutdown: {trader.xtquant_thread.is_alive()}")

    # 关闭线程池
    trader.trade_executor.shutdown(wait=True)
    print("- trade_executor shutdown completed")

    print("\nAsync architecture test completed!")


if __name__ == "__main__":
    test_async_architecture()
