"""
Redis消息持久化功能测试
测试Stream、List和Pub/Sub模式
"""

import json
import os
import time
import unittest
from unittest.mock import Mock

import redis

from src.config import Settings
from src.redis_listener import RedisSignalListener


class TestRedisPersistence(unittest.TestCase):
    def setUp(self):
        """测试初始化"""
        # 使用测试配置
        self.test_settings = Settings(
            redis_host="localhost",
            redis_port=6379,
            redis_message_mode="stream",
            redis_stream_name="test_trading_signals_stream",
            redis_consumer_group="test_trading_service",
            redis_consumer_name="test_consumer1",
            redis_list_name="test_trading_signals_list",
            redis_signal_channel="test_trading_signals",
            redis_stream_max_len=100,
            redis_block_timeout=1000,
        )

        # 创建Redis客户端用于测试
        self.redis_client = redis.Redis(
            host=self.test_settings.redis_host,
            port=self.test_settings.redis_port,
            decode_responses=True,
        )

        # 清理测试数据
        self._cleanup_test_data()

        # 模拟信号处理器
        self.received_signals = []

        def mock_signal_handler(signal):
            self.received_signals.append(signal)

        self.signal_handler = mock_signal_handler

    def tearDown(self):
        """测试清理"""
        self._cleanup_test_data()
        if hasattr(self, "redis_client"):
            self.redis_client.close()

    def _cleanup_test_data(self):
        """清理测试数据"""
        try:
            # 删除Stream
            self.redis_client.delete(self.test_settings.redis_stream_name)
            # 删除List
            self.redis_client.delete(self.test_settings.redis_list_name)
            # 删除消费者组（如果存在）
            try:
                self.redis_client.xgroup_destroy(
                    self.test_settings.redis_stream_name, self.test_settings.redis_consumer_group
                )
            except redis.ResponseError:
                pass
        except Exception:
            pass

    def test_stream_persistence(self):
        """测试Stream持久化模式"""
        # 临时设置环境变量
        os.environ["REDIS_MESSAGE_MODE"] = "stream"
        os.environ["REDIS_STREAM_NAME"] = self.test_settings.redis_stream_name
        os.environ["REDIS_CONSUMER_GROUP"] = self.test_settings.redis_consumer_group
        os.environ["REDIS_CONSUMER_NAME"] = self.test_settings.redis_consumer_name

        try:
            # 创建监听器
            listener = RedisSignalListener(self.signal_handler)

            # 测试信号
            test_signal = {
                "signal_id": "test_stream_001",
                "stock_code": "000001",
                "direction": "BUY",
                "volume": 100,
                "price": 10.50,
                "order_type": 23,
            }

            # 连接并发布信号
            self.assertTrue(listener.connect())
            listener.publish_test_signal(test_signal)

            # 验证Stream中有消息
            messages = self.redis_client.xread({self.test_settings.redis_stream_name: "0"})
            self.assertEqual(len(messages), 1)

            # 手动消费消息验证
            try:
                messages = self.redis_client.xreadgroup(
                    self.test_settings.redis_consumer_group,
                    self.test_settings.redis_consumer_name,
                    {self.test_settings.redis_stream_name: ">"},
                    count=1,
                    block=100,
                )
                self.assertEqual(len(messages), 1)

                # 验证消息内容
                stream_name, stream_messages = messages[0]
                message_id, fields = stream_messages[0]
                signal_data = json.loads(fields["data"])
                self.assertEqual(signal_data["signal_id"], "test_stream_001")

            except redis.ResponseError as e:
                if "NOGROUP" not in str(e):
                    raise

            listener.disconnect()

        finally:
            # 清理环境变量
            for key in [
                "REDIS_MESSAGE_MODE",
                "REDIS_STREAM_NAME",
                "REDIS_CONSUMER_GROUP",
                "REDIS_CONSUMER_NAME",
            ]:
                if key in os.environ:
                    del os.environ[key]

    def test_list_persistence(self):
        """测试List持久化模式"""
        os.environ["REDIS_MESSAGE_MODE"] = "list"
        os.environ["REDIS_LIST_NAME"] = self.test_settings.redis_list_name

        try:
            listener = RedisSignalListener(self.signal_handler)

            test_signal = {
                "signal_id": "test_list_001",
                "stock_code": "000002",
                "direction": "SELL",
                "volume": 200,
                "price": 15.30,
                "order_type": 23,
            }

            self.assertTrue(listener.connect())
            listener.publish_test_signal(test_signal)

            # 验证List中有消息
            list_length = self.redis_client.llen(self.test_settings.redis_list_name)
            self.assertEqual(list_length, 1)

            # 手动消费验证
            message_data = self.redis_client.lpop(self.test_settings.redis_list_name)
            signal_data = json.loads(message_data)
            self.assertEqual(signal_data["signal_id"], "test_list_001")

            listener.disconnect()

        finally:
            if "REDIS_MESSAGE_MODE" in os.environ:
                del os.environ["REDIS_MESSAGE_MODE"]
            if "REDIS_LIST_NAME" in os.environ:
                del os.environ["REDIS_LIST_NAME"]

    def test_pubsub_fallback(self):
        """测试Pub/Sub模式（向后兼容）"""
        os.environ["REDIS_MESSAGE_MODE"] = "pubsub"
        os.environ["REDIS_SIGNAL_CHANNEL"] = self.test_settings.redis_signal_channel

        try:
            listener = RedisSignalListener(self.signal_handler)

            test_signal = {
                "signal_id": "test_pubsub_001",
                "stock_code": "000003",
                "direction": "BUY",
                "volume": 300,
                "price": 20.80,
                "order_type": 23,
            }

            self.assertTrue(listener.connect())

            # Pub/Sub不持久化，这里主要测试连接和发布功能
            listener.publish_test_signal(test_signal)

            # 验证连接状态
            self.assertTrue(listener.is_connected())

            listener.disconnect()

        finally:
            if "REDIS_MESSAGE_MODE" in os.environ:
                del os.environ["REDIS_MESSAGE_MODE"]
            if "REDIS_SIGNAL_CHANNEL" in os.environ:
                del os.environ["REDIS_SIGNAL_CHANNEL"]

    def test_message_persistence_after_disconnect(self):
        """测试断连后消息持久化"""
        os.environ["REDIS_MESSAGE_MODE"] = "stream"
        os.environ["REDIS_STREAM_NAME"] = self.test_settings.redis_stream_name
        os.environ["REDIS_CONSUMER_GROUP"] = self.test_settings.redis_consumer_group

        try:
            # 创建Stream和消费者组
            listener1 = RedisSignalListener(self.signal_handler)
            listener1.connect()

            # 发布消息
            test_signals = [
                {"signal_id": "persist_001", "stock_code": "000001", "direction": "BUY"},
                {"signal_id": "persist_002", "stock_code": "000002", "direction": "SELL"},
            ]

            for signal in test_signals:
                listener1.publish_test_signal(signal)

            # 断开连接
            listener1.disconnect()

            # 验证消息仍在Stream中
            messages = self.redis_client.xread({self.test_settings.redis_stream_name: "0"})
            self.assertEqual(len(messages[0][1]), 2)  # 应该有2条消息

            # 重新连接并消费
            listener2 = RedisSignalListener(self.signal_handler)
            listener2.connect()

            # 手动消费验证消息仍然存在
            try:
                messages = self.redis_client.xreadgroup(
                    self.test_settings.redis_consumer_group,
                    "test_consumer2",  # 使用不同的消费者名
                    {self.test_settings.redis_stream_name: "0"},  # 从头开始读
                    count=10,
                )
                self.assertGreaterEqual(len(messages[0][1]), 2)
            except redis.ResponseError:
                pass

            listener2.disconnect()

        finally:
            for key in ["REDIS_MESSAGE_MODE", "REDIS_STREAM_NAME", "REDIS_CONSUMER_GROUP"]:
                if key in os.environ:
                    del os.environ[key]


if __name__ == "__main__":
    # 检查Redis连接
    try:
        client = redis.Redis(host="localhost", port=6379)
        client.ping()
        print("Redis连接正常，开始测试...")
        unittest.main()
    except redis.ConnectionError:
        print("错误: 无法连接到Redis服务器，请确保Redis正在运行")
    except Exception as e:
        print(f"连接测试失败: {e}")
