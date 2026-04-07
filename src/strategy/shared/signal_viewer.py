"""Redis-backed signal viewer shared by strategy runtime tools."""

import json
import time
from pathlib import Path

import redis

from src.infrastructure.config import settings
from src.infrastructure.logger_config import logger
from src.infrastructure.redis.connection import build_redis_client_kwargs


class SignalViewer:
    """Read the latest T0 signal from Redis and mirror it to a local file."""

    def __init__(self, output_file: str = "./output/live_signal_card.json"):
        self.output_file = Path(output_file)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.redis_client = redis.Redis(
                **build_redis_client_kwargs(
                    db=0,
                    decode_responses=True,
                    socket_connect_timeout=3,
                    socket_timeout=3,
                )
            )
            self.redis_client.ping()
            logger.info("Redis 连接成功")
        except Exception as e:
            logger.error(f"Redis 连接失败: {e}")
            raise

    def fetch_and_save(self) -> bool:
        """Fetch the latest signal payload from Redis and persist it locally."""
        try:
            signal_json = self.redis_client.get(settings.redis_t0_signal_key)
            if not signal_json:
                logger.warning(f"Redis 中无信号数据: {settings.redis_t0_signal_key}")
                return False

            signal_dict = json.loads(signal_json)
            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(signal_dict, f, ensure_ascii=False, indent=2)

            logger.info(f"信号已更新到文件: {self.output_file}")
            return True
        except Exception as e:
            logger.error(f"获取或保存信号失败: {e}")
            return False

    def watch(self, interval: int = 5):
        """Keep syncing the latest signal from Redis at a fixed interval."""
        logger.info(f"开始监听 Redis 信号，更新间隔: {interval} 秒")
        logger.info(f"输出文件: {self.output_file}")

        while True:
            try:
                self.fetch_and_save()
                time.sleep(interval)
            except KeyboardInterrupt:
                logger.info("监听已停止")
                break
            except Exception as e:
                logger.error(f"监听异常: {e}")
                time.sleep(interval)


def main():
    """CLI entrypoint."""
    viewer = SignalViewer()
    viewer.watch(interval=settings.t0_poll_interval_seconds)


if __name__ == "__main__":
    main()
