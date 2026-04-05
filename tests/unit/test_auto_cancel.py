#!/usr/bin/env python3
"""
超时撤单功能测试脚本
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


def test_auto_cancel():
    """测试自动撤单功能"""
    logger.info("开始测试超时撤单功能")
    logger.info(
        f"配置: 超时时间={settings.order_timeout_seconds}秒, 自动撤单={settings.auto_cancel_enabled}"
    )

    trader = QMTTrader()

    # 连接QMT
    if not trader.connect():
        logger.error("无法连接QMT，测试退出")
        return

    try:
        logger.info("等待5秒让系统初始化...")
        time.sleep(5)

        # 模拟下单（使用一个不太可能成交的价格）
        test_signal = {
            "stock_code": "000001.SZ",  # 平安银行
            "direction": "BUY",
            "volume": 100,
            "price": 1.0,  # 设置一个极低的价格，确保不会立即成交
        }

        logger.info(f"提交测试订单: {test_signal}")
        order_id = trader.place_order(test_signal)

        if order_id:
            logger.info(f"订单提交成功，ID: {order_id}")
            logger.info("开始监控订单状态...")

            # 监控订单状态
            for i in range(int(settings.order_timeout_seconds) + 30):  # 监控超时时间+30秒
                pending_count = trader.get_pending_orders_count()
                pending_orders = trader.get_pending_orders_info()

                logger.info(f"[{i+1}s] 待处理订单数量: {pending_count}")

                if pending_orders:
                    for order in pending_orders:
                        logger.info(
                            f"  - 订单 {order['order_id']}: {order['stock_code']} {order['direction']} "
                            f"{order['volume']}股@{order['price']}元, 已等待{order['elapsed_seconds']:.1f}秒"
                        )

                # 检查订单状态
                order_status = trader.get_order_status(order_id)
                if order_status:
                    logger.info(f"  订单状态: {order_status}")

                if pending_count == 0:
                    logger.info("所有订单已处理完成")
                    break

                time.sleep(1)

        else:
            logger.error("测试订单提交失败")

    except KeyboardInterrupt:
        logger.info("用户中断测试")
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")
    finally:
        logger.info("断开QMT连接")
        trader.disconnect()
        logger.info("测试完成")


if __name__ == "__main__":
    test_auto_cancel()
