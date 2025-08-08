import redis
import json
from typing import Dict, Any, Callable
from src.logger_config import configured_logger as logger
from src.config import settings
import asyncio
import time

class RedisSignalListener:
    def __init__(self, signal_handler: Callable[[Dict[str, Any]], None]):
        self.redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            decode_responses=True
        )
        self.signal_handler = signal_handler
        self.is_running = False
        self.pubsub = None

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
            if message and message['type'] == 'message':
                try:
                    signal_data = json.loads(message['data'])
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

    def start_listening(self):
        """开始监听Redis频道"""
        logger.info(f"开始监听Redis频道: {settings.redis_signal_channel}")
        self.is_running = True

        self.pubsub = self.redis_client.pubsub()
        self.pubsub.subscribe(settings.redis_signal_channel)

        try:
            while self.is_running:
                try:
                    # 设置超时，让程序能响应停止信号
                    message = self.pubsub.get_message(timeout=1.0)
                    if message is None:
                        continue
                        
                    if message['type'] == 'message':
                        try:
                            signal_data = json.loads(message['data'])
                            logger.info(f"收到交易信号: {signal_data}")
                            self.signal_handler(signal_data)
                        except json.JSONDecodeError as e:
                            logger.error(f"解析信号数据失败: {e}, 原始数据: {message['data']}")
                        except Exception as e:
                            logger.error(f"处理信号时发生错误: {e}")
                except redis.exceptions.TimeoutError:
                    # 超时是正常的，继续循环
                    continue

        except KeyboardInterrupt:
            logger.info("收到停止信号")
        except Exception as e:
            logger.error(f"Redis监听器发生错误: {e}")
        finally:
            if self.pubsub:
                self.pubsub.close()
            self.stop()

    def stop(self):
        """停止监听"""
        if self.is_running:
            self.is_running = False
            if self.pubsub:
                self.pubsub.close()
                self.pubsub = None
            logger.info("Redis监听器已停止")

    def test_connection(self) -> bool:
        """测试Redis连接"""
        try:
            self.redis_client.ping()
            logger.info("Redis连接测试成功")
            return True
        except Exception as e:
            logger.error(f"Redis连接测试失败: {e}")
            return False

    def publish_test_signal(self, signal: Dict[str, Any]):
        """发布测试信号"""
        try:
            self.redis_client.publish(
                settings.redis_signal_channel,
                json.dumps(signal)
            )
            logger.info(f"发布测试信号成功: {signal}")
        except Exception as e:
            logger.error(f"发布测试信号失败: {e}")
