#!/usr/bin/env python3
"""
并发下单功能测试脚本
"""
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

pytestmark = pytest.mark.live_qmt

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger

from src.infrastructure.config import settings
from src.trading.execution.qmt_trader import QMTTrader


def test_concurrent_orders():
    """测试并发下单"""
    logger.info("=== 测试并发异步下单 ===")

    trader = QMTTrader()

    if not trader.connect():
        logger.error("无法连接QMT，测试退出")
        return

    try:
        # 准备测试数据
        test_signals = [
            {"stock_code": "000001.SZ", "direction": "BUY", "volume": 100, "price": 1.0},
            {"stock_code": "000002.SZ", "direction": "BUY", "volume": 200, "price": 1.5},
            {"stock_code": "600000.SH", "direction": "BUY", "volume": 300, "price": 2.0},
            {"stock_code": "600036.SH", "direction": "SELL", "volume": 100, "price": 10.0},
            {"stock_code": "000858.SZ", "direction": "BUY", "volume": 500, "price": 1.2},
            {"stock_code": "002415.SZ", "direction": "SELL", "volume": 200, "price": 8.0},
            {"stock_code": "600519.SH", "direction": "BUY", "volume": 100, "price": 1800.0},
            {"stock_code": "000166.SZ", "direction": "BUY", "volume": 1000, "price": 0.5},
        ]

        results = []
        results_lock = threading.Lock()

        def order_callback(order_id, error, signal_info):
            with results_lock:
                if order_id:
                    results.append(
                        ("success", signal_info["stock_code"], signal_info["direction"], order_id)
                    )
                    logger.info(
                        f"✓ {signal_info['stock_code']} {signal_info['direction']} 委托成功: {order_id}"
                    )
                else:
                    results.append(
                        ("failed", signal_info["stock_code"], signal_info["direction"], error)
                    )
                    logger.error(
                        f"✗ {signal_info['stock_code']} {signal_info['direction']} 委托失败: {error}"
                    )

        # 快速提交所有下单任务
        logger.info(f"快速提交 {len(test_signals)} 个下单任务...")
        start_time = time.time()

        for i, signal in enumerate(test_signals):
            callback = lambda oid, err, sig=signal: order_callback(oid, err, sig)
            trader.place_order_async(signal, callback)
            logger.info(
                f"[{i+1}/{len(test_signals)}] 已提交: {signal['stock_code']} {signal['direction']}"
            )

        submit_time = time.time() - start_time
        logger.info(f"所有任务提交完成，耗时: {submit_time:.3f}秒")

        # 监控队列状态和结果
        logger.info("开始监控执行状态...")
        last_completed = 0

        for i in range(60):  # 监控60秒
            queue_status = trader.get_queue_status()
            trading_stats = trader.get_trading_stats()

            completed = len(results)
            if completed != last_completed:
                logger.info(
                    f"[{i+1}s] 已完成: {completed}/{len(test_signals)}, "
                    f"队列中: {queue_status['thread_queue_pending']}, "
                    f"成功率: {queue_status['success_rate']}"
                )
                last_completed = completed

            # 每5秒显示详细统计
            if i % 5 == 0:
                logger.info(f"统计: {trading_stats}")

            if completed >= len(test_signals):
                logger.info("所有订单处理完成")
                break

            time.sleep(1)

        # 最终结果统计
        logger.info("=== 并发下单测试结果 ===")
        success_count = sum(1 for r in results if r[0] == "success")
        failed_count = sum(1 for r in results if r[0] == "failed")

        logger.info(f"总提交: {len(test_signals)} 个订单")
        logger.info(f"成功: {success_count} 个")
        logger.info(f"失败: {failed_count} 个")
        logger.info(f"未完成: {len(test_signals) - len(results)} 个")
        logger.info(f"成功率: {success_count/len(test_signals)*100:.1f}%")
        logger.info(f"提交速度: {len(test_signals)/submit_time:.1f} 订单/秒")

        # 显示成功的订单
        logger.info("成功的订单:")
        for result in results:
            if result[0] == "success":
                logger.info(f"  {result[1]} {result[2]} -> 订单ID: {result[3]}")

        # 显示失败的订单
        if failed_count > 0:
            logger.info("失败的订单:")
            for result in results:
                if result[0] == "failed":
                    logger.error(f"  {result[1]} {result[2]} -> 错误: {result[3]}")

        # 显示最终统计
        final_stats = trader.get_trading_stats()
        logger.info(f"最终统计: {final_stats}")

        # 显示监控中的订单
        pending_orders = trader.get_pending_orders_info()
        if pending_orders:
            logger.info(f"当前监控中的订单 ({len(pending_orders)} 个):")
            for order in pending_orders:
                logger.info(
                    f"  订单 {order['order_id']}: {order['stock_code']} {order['direction']} "
                    f"{order['volume']}股@{order['price']}元, 已等待{order['elapsed_seconds']:.1f}秒"
                )

    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")
    finally:
        logger.info("断开QMT连接")
        trader.disconnect()


def test_rapid_signal_processing():
    """测试快速信号处理（模拟交易服务）"""
    logger.info("=== 测试快速信号处理 ===")

    # 模拟快速接收多个交易信号
    signals = [
        {
            "signal_id": f"SIG_{i:03d}",
            "stock_code": f"{1000+i:06d}.SZ",
            "direction": "BUY",
            "volume": 100 * (i + 1),
            "price": 1.0 + i * 0.1,
        }
        for i in range(10)
    ]

    trader = QMTTrader()

    if not trader.connect():
        logger.error("无法连接QMT，测试退出")
        return

    try:
        logger.info(f"模拟快速接收 {len(signals)} 个交易信号...")

        results = []
        results_lock = threading.Lock()

        def signal_callback(order_id, error, signal):
            with results_lock:
                if order_id:
                    results.append((signal["signal_id"], "success", order_id))
                    logger.info(f"信号 {signal['signal_id']} 处理成功: {order_id}")
                else:
                    results.append((signal["signal_id"], "failed", error))
                    logger.error(f"信号 {signal['signal_id']} 处理失败: {error}")

        # 快速处理所有信号（模拟交易服务的行为）
        start_time = time.time()
        for signal in signals:
            callback = lambda oid, err, sig=signal: signal_callback(oid, err, sig)
            trader.place_order_async(signal, callback)
            logger.info(f"信号 {signal['signal_id']} 已提交处理")

        processing_time = time.time() - start_time
        logger.info(f"所有信号提交处理完成，耗时: {processing_time:.3f}秒")
        logger.info(f"处理速度: {len(signals)/processing_time:.1f} 信号/秒")

        # 等待所有信号处理完成
        for i in range(30):
            if len(results) >= len(signals):
                break
            logger.info(f"等待处理完成... {len(results)}/{len(signals)}")
            time.sleep(1)

        logger.info(f"信号处理完成: {len(results)}/{len(signals)}")

    except Exception as e:
        logger.error(f"测试信号处理异常: {e}")
    finally:
        trader.disconnect()


def main():
    """主测试函数"""
    logger.info("开始并发下单功能测试")

    # 测试1: 并发下单
    test_concurrent_orders()
    time.sleep(3)

    # 测试2: 快速信号处理
    test_rapid_signal_processing()

    logger.info("所有并发测试完成")


if __name__ == "__main__":
    main()
