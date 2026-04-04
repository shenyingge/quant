#!/usr/bin/env python3
"""Redis交易记录集成测试脚本"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.live_qmt

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger

from src.config import settings
from src.redis_client import redis_trade_client
from src.trader import QMTTrader


def test_redis_connection():
    """测试Redis连接"""
    logger.info("=== 测试Redis连接 ===")

    try:
        success = redis_trade_client.connect()
        if success:
            logger.info("✓ Redis连接成功")

            # 测试基本操作
            test_data = {"test_key": "test_value", "timestamp": datetime.now().isoformat()}

            # 保存测试数据
            redis_trade_client.redis_client.set("test:connection", json.dumps(test_data), ex=60)

            # 读取测试数据
            retrieved = redis_trade_client.redis_client.get("test:connection")
            if retrieved:
                data = json.loads(retrieved)
                logger.info(f"✓ Redis读写测试成功: {data}")

            # 清理测试数据
            redis_trade_client.redis_client.delete("test:connection")
            logger.info("✓ Redis基本操作测试通过")

        else:
            logger.error("✗ Redis连接失败")

    except Exception as e:
        logger.error(f"Redis连接测试异常: {e}")
    finally:
        redis_trade_client.disconnect()


def test_trade_record_operations():
    """测试交易记录操作"""
    logger.info("=== 测试交易记录操作 ===")

    if not redis_trade_client.connect():
        logger.error("Redis连接失败，跳过测试")
        return

    try:
        # 测试数据
        test_order_id = "TEST001"
        test_trade_id = "TRADE001"
        test_trade_data = {
            "order_id": test_order_id,
            "stock_code": "000001.SZ",
            "direction": "BUY",
            "volume": 100,
            "price": 12.34,
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }

        # 测试保存交易记录
        logger.info("测试保存交易记录...")
        success = redis_trade_client.save_trade_record(
            test_order_id, test_trade_id, test_trade_data
        )
        if success:
            logger.info("✓ 交易记录保存成功")
        else:
            logger.error("✗ 交易记录保存失败")
            return

        # 测试读取交易记录
        logger.info("测试读取交易记录...")
        retrieved_record = redis_trade_client.get_trade_record(test_order_id, test_trade_id)
        if retrieved_record:
            logger.info(
                f"✓ 交易记录读取成功: {json.dumps(retrieved_record, indent=2, ensure_ascii=False)}"
            )
        else:
            logger.error("✗ 交易记录读取失败")

        # 测试获取记录数量
        count = redis_trade_client.get_trade_records_count()
        logger.info(f"当前交易记录数量: {count}")

        # 测试获取所有记录
        all_records = redis_trade_client.get_all_trade_records()
        logger.info(f"所有交易记录: {len(all_records)} 条")

        # 添加更多测试记录
        for i in range(3):
            test_data = {
                "order_id": f"TEST{i:03d}",
                "stock_code": f"00000{i+1}.SZ",
                "direction": "BUY" if i % 2 == 0 else "SELL",
                "volume": (i + 1) * 100,
                "price": 10.0 + i,
                "timestamp": datetime.now().isoformat(),
            }
            redis_trade_client.save_trade_record(f"TEST{i:03d}", f"TRADE{i:03d}", test_data)

        final_count = redis_trade_client.get_trade_records_count()
        logger.info(f"添加测试数据后记录数量: {final_count}")

        # 测试清理操作
        logger.info("测试清理所有记录...")
        deleted_count = redis_trade_client.cleanup_all_trade_records()
        logger.info(f"✓ 清理完成，删除了 {deleted_count} 条记录")

        final_count_after_cleanup = redis_trade_client.get_trade_records_count()
        logger.info(f"清理后记录数量: {final_count_after_cleanup}")

    except Exception as e:
        logger.error(f"交易记录操作测试异常: {e}")
    finally:
        redis_trade_client.disconnect()


def test_trader_redis_integration():
    """测试交易者Redis集成"""
    logger.info("=== 测试交易者Redis集成 ===")

    trader = QMTTrader()

    # 模拟连接（不实际连接QMT）
    logger.info("模拟QMT连接和Redis集成...")

    try:
        # 直接测试Redis连接
        if settings.redis_trade_records_enabled:
            redis_connected = redis_trade_client.connect()
            if redis_connected:
                logger.info("✓ Redis连接成功")

                # 获取Redis信息
                redis_info = trader.get_redis_trade_records_info()
                logger.info(
                    f"Redis交易记录信息: {json.dumps(redis_info, indent=2, ensure_ascii=False)}"
                )

                # 测试保存订单记录
                test_signal = {
                    "stock_code": "000001.SZ",
                    "direction": "BUY",
                    "volume": 100,
                    "price": 12.50,
                }

                logger.info("测试保存订单记录到Redis...")
                trader._save_order_to_redis("TEST_ORDER_001", test_signal, "success")

                # 测试保存成交记录
                test_trade_info = {
                    "stock_code": "000001.SZ",
                    "filled_volume": 100,
                    "avg_price": 12.45,
                    "order_status": "已成交",
                }

                logger.info("测试保存成交记录到Redis...")
                trader._save_trade_execution_to_redis("TEST_ORDER_001", test_trade_info)

                # 检查记录数量
                count = redis_trade_client.get_trade_records_count()
                logger.info(f"保存后Redis记录数量: {count}")

                # 获取所有记录
                all_records = redis_trade_client.get_all_trade_records()
                logger.info("保存的记录:")
                for key, record in all_records.items():
                    logger.info(f"  {key}: {json.dumps(record, ensure_ascii=False)}")

                # 清理测试记录
                redis_trade_client.cleanup_all_trade_records()
                logger.info("测试记录已清理")

            else:
                logger.error("✗ Redis连接失败")
        else:
            logger.info("Redis交易记录存储未启用")

    except Exception as e:
        logger.error(f"交易者Redis集成测试异常: {e}")
    finally:
        if settings.redis_trade_records_enabled:
            redis_trade_client.disconnect()


def test_daily_cleanup_scheduler():
    """测试每日清理调度器"""
    logger.info("=== 测试每日清理调度器 ===")

    if not redis_trade_client.connect():
        logger.error("Redis连接失败，跳过测试")
        return

    try:
        # 添加一些测试数据
        logger.info("添加测试数据...")
        for i in range(5):
            test_data = {
                "order_id": f"CLEANUP_TEST_{i:03d}",
                "timestamp": datetime.now().isoformat(),
            }
            redis_trade_client.save_trade_record(
                f"CLEANUP_TEST_{i:03d}", f"CLEANUP_TRADE_{i:03d}", test_data
            )

        count_before = redis_trade_client.get_trade_records_count()
        logger.info(f"添加测试数据后记录数量: {count_before}")

        # 手动触发清理任务
        logger.info("手动触发清理任务...")
        redis_trade_client._daily_cleanup_task()

        count_after = redis_trade_client.get_trade_records_count()
        logger.info(f"清理后记录数量: {count_after}")
        logger.info(f"清理任务测试完成")

        # 测试调度器配置
        logger.info(f"配置的清理时间: {settings.redis_trade_cleanup_time}")
        logger.info("✓ 每日清理调度器测试完成")

    except Exception as e:
        logger.error(f"每日清理调度器测试异常: {e}")
    finally:
        redis_trade_client.disconnect()


def test_full_integration():
    """完整集成测试"""
    logger.info("=== 完整Redis集成测试 ===")

    # 显示配置信息
    logger.info("Redis配置:")
    logger.info(f"  主机: {settings.redis_host}:{settings.redis_port}")
    logger.info(f"  交易记录存储: {'启用' if settings.redis_trade_records_enabled else '禁用'}")
    logger.info(f"  记录前缀: {settings.redis_trade_records_prefix}")
    logger.info(f"  清理时间: {settings.redis_trade_cleanup_time}")

    try:
        # 模拟完整的交易流程
        trader = QMTTrader()

        # 连接Redis
        if settings.redis_trade_records_enabled:
            redis_connected = redis_trade_client.connect()
            if not redis_connected:
                logger.error("Redis连接失败，集成测试终止")
                return

        logger.info("模拟交易流程...")

        # 模拟多个交易信号
        test_signals = [
            {"stock_code": "000001.SZ", "direction": "BUY", "volume": 100, "price": 12.34},
            {"stock_code": "000002.SZ", "direction": "SELL", "volume": 200, "price": 23.45},
            {"stock_code": "600000.SH", "direction": "BUY", "volume": 500, "price": 34.56},
        ]

        for i, signal in enumerate(test_signals):
            order_id = f"INTEGRATION_TEST_{i:03d}"

            # 保存订单记录
            trader._save_order_to_redis(order_id, signal, "success")
            logger.info(f"✓ 订单 {order_id} 记录已保存")

            # 模拟成交
            trade_info = {
                "stock_code": signal["stock_code"],
                "filled_volume": signal["volume"],
                "avg_price": signal["price"] * 0.999,  # 略低于委托价
                "order_status": "已成交",
            }

            trader._save_trade_execution_to_redis(order_id, trade_info)
            logger.info(f"✓ 订单 {order_id} 成交记录已保存")

        # 检查最终结果
        final_count = redis_trade_client.get_trade_records_count()
        logger.info(f"集成测试完成，总记录数: {final_count}")

        # 获取Redis信息
        redis_info = trader.get_redis_trade_records_info()
        logger.info(f"Redis状态: {json.dumps(redis_info, indent=2, ensure_ascii=False)}")

        # 显示所有记录
        all_records = redis_trade_client.get_all_trade_records()
        logger.info("所有交易记录:")
        for key, record in all_records.items():
            logger.info(f"  {key}")
            logger.info(f"    股票: {record.get('stock_code', 'N/A')}")
            logger.info(f"    方向: {record.get('direction', 'N/A')}")
            logger.info(f"    数量: {record.get('volume', record.get('filled_volume', 'N/A'))}")
            logger.info(f"    价格: {record.get('price', record.get('avg_price', 'N/A'))}")
            logger.info(f"    时间: {record.get('timestamp', record.get('execution_time', 'N/A'))}")

        # 清理测试数据
        deleted_count = redis_trade_client.cleanup_all_trade_records()
        logger.info(f"✓ 集成测试完成，清理了 {deleted_count} 条记录")

    except Exception as e:
        logger.error(f"完整集成测试异常: {e}")
    finally:
        if settings.redis_trade_records_enabled:
            redis_trade_client.disconnect()


def main():
    """主测试函数"""
    logger.info("开始Redis交易记录集成测试")
    logger.info("=" * 60)

    # 测试1: Redis基本连接
    test_redis_connection()
    time.sleep(2)

    # 测试2: 交易记录操作
    test_trade_record_operations()
    time.sleep(2)

    # 测试3: 交易者Redis集成
    test_trader_redis_integration()
    time.sleep(2)

    # 测试4: 每日清理调度器
    test_daily_cleanup_scheduler()
    time.sleep(2)

    # 测试5: 完整集成测试
    test_full_integration()

    logger.info("=" * 60)
    logger.info("Redis交易记录集成测试完成")


if __name__ == "__main__":
    main()
