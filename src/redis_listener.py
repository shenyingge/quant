import json
import threading
import time
from typing import Any, Callable, Dict, Optional

import redis

from src.config import settings
from src.logger_config import configured_logger as logger


class RedisSignalListener:
    def __init__(self, signal_handler: Callable[[Dict[str, Any]], None]):
        self.signal_handler = signal_handler
        self.is_running = False
        self.pubsub = None
        self.redis_client = None
        self._create_client()
        self.connection_lock = threading.Lock()

    def _create_client(self):
        """创建Redis客户端"""
        try:
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            logger.debug("Redis客户端已创建")
        except Exception as e:
            logger.error(f"创建Redis客户端失败: {e}")
            self.redis_client = None

    def initialize(self):
        """初始化Redis订阅"""
        logger.info(f"初始化Redis订阅: {settings.redis_signal_channel}")
        self.pubsub = self.redis_client.pubsub()
        self.pubsub.subscribe(settings.redis_signal_channel)
        self.is_running = True

    def check_messages(self):
        """非阻塞方式检查Redis消息"""
        if not self.pubsub or not self.is_running:
            return

        try:
            # 非阻塞获取消息
            message = self.pubsub.get_message(timeout=0.01)
            if message and message["type"] == "message":
                try:
                    signal_data = json.loads(message["data"])
                    logger.info(f"收到交易信号: {signal_data}")
                    self.signal_handler(signal_data)
                except json.JSONDecodeError as e:
                    logger.error(f"解析信号数据失败: {e}, 原始数据: {message['data']}")
                except Exception as e:
                    logger.error(f"处理信号时发生错误: {e}")
        except redis.exceptions.TimeoutError:
            # 超时是正常的
            pass
        except Exception as e:
            logger.error(f"检查Redis消息时发生错误: {e}")

    def connect(self) -> bool:
        """连接Redis并订阅频道"""
        with self.connection_lock:
            try:
                if not self.redis_client:
                    self._create_client()

                if not self.redis_client:
                    return False

                # 测试连接
                self.redis_client.ping()

                # 创建订阅
                self.pubsub = self.redis_client.pubsub()
                self.pubsub.subscribe(settings.redis_signal_channel)

                logger.info(f"Redis连接成功，已订阅频道: {settings.redis_signal_channel}")
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
        """开始监听Redis频道（支持自动重连）"""
        logger.info(f"开始监听Redis频道: {settings.redis_signal_channel}")
        self.is_running = True

        try:
            while self.is_running:
                try:
                    # 检查连接状态
                    if not self.pubsub:
                        logger.warning("Redis未连接，尝试重新连接...")
                        if not self.connect():
                            logger.error("Redis重连失败，等待5秒后重试")
                            time.sleep(5)
                            continue

                    # 尝试获取消息
                    message = self.pubsub.get_message(timeout=1.0)
                    if message is None:
                        continue

                    if message["type"] == "message":
                        try:
                            signal_data = json.loads(message["data"])
                            logger.info(f"收到交易信号: {signal_data}")
                            self.signal_handler(signal_data)
                        except json.JSONDecodeError as e:
                            logger.error(f"解析信号数据失败: {e}, 原始数据: {message['data']}")
                        except Exception as e:
                            logger.error(f"处理信号时发生错误: {e}")

                except redis.exceptions.TimeoutError:
                    # 超时是正常的，继续循环
                    continue
                except redis.exceptions.ConnectionError as e:
                    logger.error(f"Redis连接错误: {e}")
                    self.pubsub = None  # 标记连接断开
                    time.sleep(2)  # 短暂等待后重试
                    continue
                except Exception as e:
                    logger.error(f"Redis监听器发生未知错误: {e}")
                    time.sleep(1)  # 短暂等待后重试
                    continue

        except KeyboardInterrupt:
            logger.info("收到停止信号")
        except Exception as e:
            logger.error(f"Redis监听器发生严重错误: {e}")
        finally:
            self.stop()

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
        return self.pubsub is not None

    def publish_test_signal(self, signal: Dict[str, Any]):
        """发布测试信号"""
        try:
            self.redis_client.publish(settings.redis_signal_channel, json.dumps(signal))
            logger.info(f"发布测试信号成功: {signal}")
        except Exception as e:
            logger.error(f"发布测试信号失败: {e}")
