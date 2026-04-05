#!/usr/bin/env python3
"""
下单超时和异步功能测试脚本
"""
import os
import sys
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from loguru import logger

from src.config import settings
from src.trading.execution.qmt_trader import QMTTrader


def test_sync_order_timeout():
    """测试同步下单超时机制"""
    logger.info("=== 测试同步下单超时机制 ===")
    logger.info(f"配置: 下单超时={settings.order_submit_timeout}秒")

    trader = QMTTrader()

    if not trader.connect():
        logger.error("无法连接QMT，测试退出")
        return

    try:
        # 测试正常下单
        test_signal = {"stock_code": "000001.SZ", "direction": "BUY", "volume": 100, "price": 1.0}

        logger.info("测试同步下单...")
        start_time = time.time()
        order_id = trader.place_order(test_signal)
        elapsed = time.time() - start_time

        if order_id:
            logger.info(f"同步下单成功，订单ID: {order_id}，耗时: {elapsed:.2f}秒")
        else:
            logger.warning(f"同步下单失败或超时，耗时: {elapsed:.2f}秒")

    except Exception as e:
        logger.error(f"测试同步下单异常: {e}")
    finally:
        trader.disconnect()


def test_async_order():
    """测试异步下单"""
    logger.info("=== 测试异步下单 ===")

    trader = QMTTrader()

    if not trader.connect():
        logger.error("无法连接QMT，测试退出")
        return

    try:
        results = []

        def order_callback(order_id, error):
            if order_id:
                logger.info(f"异步下单成功，订单ID: {order_id}")
                results.append(("success", order_id))
            else:
                logger.error(f"异步下单失败: {error}")
                results.append(("error", error))

        # 测试异步下单
        test_signal = {"stock_code": "000001.SZ", "direction": "BUY", "volume": 100, "price": 1.0}

        logger.info("提交异步下单...")
        trader.place_order_async(test_signal, order_callback)

        # 等待异步结果
        logger.info("等待异步下单结果...")
        for i in range(20):  # 等待最多20秒
            if results:
                break
            time.sleep(1)
            logger.info(f"等待中... {i+1}秒")

        if results:
            result_type, result_value = results[0]
            if result_type == "success":
                logger.info(f"异步下单测试成功，订单ID: {result_value}")
            else:
                logger.error(f"异步下单测试失败: {result_value}")
        else:
            logger.warning("异步下单超时，未收到回调")

    except Exception as e:
        logger.error(f"测试异步下单异常: {e}")
    finally:
        trader.disconnect()


def test_multiple_async_orders():
    """测试多个异步下单"""
    logger.info("=== 测试并发异步下单 ===")

    trader = QMTTrader()

    if not trader.connect():
        logger.error("无法连接QMT，测试退出")
        return

    try:
        results = []

        def order_callback(order_id, error, order_num):
            if order_id:
                logger.info(f"异步订单{order_num} 成功，订单ID: {order_id}")
                results.append(("success", order_num, order_id))
            else:
                logger.error(f"异步订单{order_num} 失败: {error}")
                results.append(("error", order_num, error))

        # 提交多个异步订单
        test_signals = [
            {"stock_code": "000001.SZ", "direction": "BUY", "volume": 100, "price": 1.0},
            {"stock_code": "000002.SZ", "direction": "BUY", "volume": 100, "price": 1.0},
            {"stock_code": "600000.SH", "direction": "BUY", "volume": 100, "price": 1.0},
        ]

        for i, signal in enumerate(test_signals, 1):
            logger.info(f"提交异步订单{i}: {signal}")
            trader.place_order_async(signal, lambda oid, err, num=i: order_callback(oid, err, num))

        # 等待所有异步结果
        logger.info(f"等待{len(test_signals)}个异步下单结果...")
        for i in range(30):  # 等待最多30秒
            if len(results) >= len(test_signals):
                break
            time.sleep(1)
            logger.info(f"等待中... {i+1}秒，已完成: {len(results)}/{len(test_signals)}")

        logger.info("=== 异步下单测试结果 ===")
        success_count = 0
        for result_type, order_num, result_value in results:
            if result_type == "success":
                success_count += 1
                logger.info(f"订单{order_num}: 成功，ID={result_value}")
            else:
                logger.error(f"订单{order_num}: 失败，{result_value}")

        logger.info(f"总计: {success_count}/{len(test_signals)} 个订单成功")

        # 显示当前待处理订单
        pending_count = trader.get_pending_orders_count()
        if pending_count > 0:
            logger.info(f"当前有 {pending_count} 个待处理订单")
            pending_orders = trader.get_pending_orders_info()
            for order in pending_orders:
                logger.info(
                    f"  - 订单 {order['order_id']}: {order['symbol']} {order['action']} "
                    f"{order['quantity']}股@{order['price']}元"
                )

    except Exception as e:
        logger.error(f"测试并发异步下单异常: {e}")
    finally:
        trader.disconnect()


def main():
    """主测试函数"""
    logger.info("开始测试下单超时和异步功能")

    # 测试1: 同步下单超时机制
    test_sync_order_timeout()
    time.sleep(2)

    # 测试2: 异步下单
    test_async_order()
    time.sleep(2)

    # 测试3: 并发异步下单
    test_multiple_async_orders()

    logger.info("所有测试完成")


if __name__ == "__main__":
    main()
