"""Redis signal listener (migrated from src/redis_listener.py)."""

import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import redis

from src.infrastructure.config import settings
from src.infrastructure.logger_config import configured_logger as logger
from src.infrastructure.redis.connection import build_redis_client_kwargs


class RedisSignalListener:
    def __init__(self, signal_handler: Callable[[Dict[str, Any]], None]):
        self.signal_handler = signal_handler
        self.is_running = False
        self.pubsub = None
        self.redis_client = None
        self._create_client()
        self.connection_lock = threading.Lock()
        self.message_mode = settings.redis_message_mode.lower()
        logger.info(f"Redis消息模式: {self.message_mode}")

    def _create_client(self):
        """创建Redis客户端"""
        try:
            self.redis_client = redis.Redis(
                **build_redis_client_kwargs(
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30,
                )
            )
            logger.debug("Redis客户端已创建")
        except Exception as e:
            logger.error(f"创建Redis客户端失败: {e}")
            self.redis_client = None

    def initialize(self):
        """初始化Redis监听"""
        if self.message_mode == "pubsub":
            logger.info(f"初始化Redis Pub/Sub订阅: {settings.redis_signal_channel}")
            self.pubsub = self.redis_client.pubsub()
            self.pubsub.subscribe(settings.redis_signal_channel)
        elif self.message_mode == "stream":
            logger.info(f"初始化Redis Stream消费: {settings.redis_stream_name}")
            self._ensure_stream_consumer_group()
        elif self.message_mode == "list":
            logger.info(f"初始化Redis List监听: {settings.redis_list_name}")

        self.is_running = True

    def _ensure_stream_consumer_group(self):
        """确保Stream消费者组存在"""
        try:
            self.redis_client.xgroup_create(
                settings.redis_stream_name, settings.redis_consumer_group, id="0", mkstream=True
            )
            logger.info(f"创建消费者组: {settings.redis_consumer_group}")
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.debug(f"消费者组已存在: {settings.redis_consumer_group}")
            else:
                raise e

    def _process_stream_messages(self, messages: List[Tuple]):
        """处理Stream消息"""
        for stream_name, stream_messages in messages:
            for message_id, fields in stream_messages:
                try:
                    if "data" in fields:
                        signal_data = json.loads(fields["data"])
                        logger.info(f"收到Stream信号 [{message_id}]: {signal_data}")
                        self.signal_handler(signal_data)

                        # 确认消息已处理
                        self.redis_client.xack(
                            settings.redis_stream_name, settings.redis_consumer_group, message_id
                        )
                    else:
                        logger.warning(f"Stream消息缺少data字段: {fields}")

                except json.JSONDecodeError as e:
                    logger.error(f"解析Stream消息失败 [{message_id}]: {e}")
                except Exception as e:
                    logger.error(f"处理Stream消息失败 [{message_id}]: {e}")

    def _process_list_messages(self, messages: List[Tuple]):
        """处理List消息"""
        for list_name, message_data in messages:
            try:
                signal_data = json.loads(message_data)
                logger.info(f"收到List信号: {signal_data}")
                self.signal_handler(signal_data)
            except json.JSONDecodeError as e:
                logger.error(f"解析List消息失败: {e}")
            except Exception as e:
                logger.error(f"处理List消息失败: {e}")

    def check_messages(self):
        """非阻塞方式检查Redis消息"""
        if not self.is_running:
            return

        try:
            if self.message_mode == "pubsub":
                if not self.pubsub:
                    return
                message = self.pubsub.get_message(timeout=0.01)
                if message and message["type"] == "message":
                    try:
                        signal_data = json.loads(message["data"])
                        logger.info(f"收到Pub/Sub信号: {signal_data}")
                        self.signal_handler(signal_data)
                    except json.JSONDecodeError as e:
                        logger.error(f"解析Pub/Sub数据失败: {e}, 原始数据: {message['data']}")
                    except Exception as e:
                        logger.error(f"处理Pub/Sub信号时发生错误: {e}")

            elif self.message_mode == "stream":
                messages = self.redis_client.xreadgroup(
                    settings.redis_consumer_group,
                    settings.redis_consumer_name,
                    {settings.redis_stream_name: ">"},
                    count=1,
                    block=1,
                )
                if messages:
                    self._process_stream_messages(messages)

            elif self.message_mode == "list":
                result = self.redis_client.blpop(settings.redis_list_name, timeout=1)
                if result:
                    self._process_list_messages([result])

        except redis.exceptions.TimeoutError:
            pass
        except Exception as e:
            logger.error(f"检查Redis消息时发生错误: {e}")

    def connect(self) -> bool:
        """连接Redis并初始化消息监听"""
        with self.connection_lock:
            try:
                if not self.redis_client:
                    self._create_client()

                if not self.redis_client:
                    return False

                # 测试连接
                self.redis_client.ping()

                # 根据模式初始化
                if self.message_mode == "pubsub":
                    self.pubsub = self.redis_client.pubsub()
                    self.pubsub.subscribe(settings.redis_signal_channel)
                    logger.info(f"Redis连接成功，已订阅频道: {settings.redis_signal_channel}")
                elif self.message_mode == "stream":
                    self._ensure_stream_consumer_group()
                    logger.info(f"Redis连接成功，Stream消费者组: {settings.redis_consumer_group}")
                elif self.message_mode == "list":
                    logger.info(f"Redis连接成功，List监听: {settings.redis_list_name}")

                return True

            except Exception as e:
                logger.error(f"Redis连接失败: {e}")
                self.pubsub = None
                return False

    def disconnect(self):
        """断开Redis连接"""
        with self.connection_lock:
            try:
                if self.pubsub:
                    self.pubsub.close()
                    self.pubsub = None

                if self.redis_client:
                    self.redis_client.close()

                logger.info("Redis连接已断开")

            except Exception as e:
                logger.error(f"断开Redis连接时发生错误: {e}")

    def start_listening(self):
        """开始监听Redis消息（支持自动重连）"""
        logger.info(f"开始监听Redis消息，模式: {self.message_mode}")
        self.is_running = True

        try:
            while self.is_running:
                try:
                    # 检查连接状态
                    if not self._is_connected():
                        logger.warning("Redis未连接，尝试重新连接...")
                        if not self.connect():
                            logger.error("Redis重连失败，等待5秒后重试")
                            time.sleep(5)
                            continue

                    # 根据模式获取消息
                    if self.message_mode == "pubsub":
                        message = self.pubsub.get_message(timeout=1.0)
                        if message is None:
                            continue
                        if message["type"] == "message":
                            try:
                                signal_data = json.loads(message["data"])
                                logger.info(f"收到Pub/Sub信号: {signal_data}")
                                self.signal_handler(signal_data)
                            except json.JSONDecodeError as e:
                                logger.error(
                                    f"解析Pub/Sub数据失败: {e}, 原始数据: {message['data']}"
                                )
                            except Exception as e:
                                logger.error(f"处理Pub/Sub信号时发生错误: {e}")

                    elif self.message_mode == "stream":
                        messages = self.redis_client.xreadgroup(
                            settings.redis_consumer_group,
                            settings.redis_consumer_name,
                            {settings.redis_stream_name: ">"},
                            count=1,
                            block=settings.redis_block_timeout,
                        )
                        if messages:
                            self._process_stream_messages(messages)

                    elif self.message_mode == "list":
                        result = self.redis_client.blpop(
                            settings.redis_list_name, timeout=settings.redis_block_timeout // 1000
                        )
                        if result:
                            self._process_list_messages([result])

                except redis.exceptions.TimeoutError:
                    continue
                except redis.exceptions.ConnectionError as e:
                    logger.error(f"Redis连接错误: {e}")
                    self.pubsub = None
                    time.sleep(2)
                    continue
                except Exception as e:
                    logger.error(f"Redis监听器发生未知错误: {e}")
                    time.sleep(1)
                    continue

        except KeyboardInterrupt:
            logger.info("收到停止信号")
        except Exception as e:
            logger.error(f"Redis监听器发生严重错误: {e}")
        finally:
            self.stop()

    def _is_connected(self) -> bool:
        """检查连接状态"""
        if self.message_mode == "pubsub":
            return self.pubsub is not None
        else:
            return self.redis_client is not None

    def stop(self):
        """停止监听"""
        if self.is_running:
            self.is_running = False
            self.disconnect()
            logger.info("Redis监听器已停止")

    def test_connection(self) -> bool:
        """测试Redis连接"""
        try:
            if not self.redis_client:
                self._create_client()

            if self.redis_client:
                self.redis_client.ping()
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"Redis连接测试失败: {e}")
            return False

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._is_connected()

    def publish_test_signal(self, signal: Dict[str, Any]):
        """发布测试信号"""
        try:
            signal_json = json.dumps(signal)

            if self.message_mode == "pubsub":
                self.redis_client.publish(settings.redis_signal_channel, signal_json)
                logger.info(f"发布Pub/Sub测试信号成功: {signal}")
            elif self.message_mode == "stream":
                self.redis_client.xadd(
                    settings.redis_stream_name,
                    {"data": signal_json},
                    maxlen=settings.redis_stream_max_len,
                )
                logger.info(f"发布Stream测试信号成功: {signal}")
            elif self.message_mode == "list":
                self.redis_client.rpush(settings.redis_list_name, signal_json)
                logger.info(f"发布List测试信号成功: {signal}")

        except Exception as e:
            logger.error(f"发布测试信号失败: {e}")

    def publish_signal(self, signal: Dict[str, Any]):
        """发布交易信号（生产环境使用）"""
        try:
            signal_json = json.dumps(signal)

            if self.message_mode == "pubsub":
                self.redis_client.publish(settings.redis_signal_channel, signal_json)
                logger.info(f"发布Pub/Sub信号: {signal}")
            elif self.message_mode == "stream":
                message_id = self.redis_client.xadd(
                    settings.redis_stream_name,
                    {"data": signal_json, "timestamp": int(time.time() * 1000)},
                    maxlen=settings.redis_stream_max_len,
                )
                logger.info(f"发布Stream信号 [{message_id}]: {signal}")
            elif self.message_mode == "list":
                self.redis_client.rpush(settings.redis_list_name, signal_json)
                logger.info(f"发布List信号: {signal}")

        except Exception as e:
            logger.error(f"发布信号失败: {e}")
            raise
