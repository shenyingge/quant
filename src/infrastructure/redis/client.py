"""Redis客户端工具模块"""

import json
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import redis
from schedule import Scheduler

from src.config import settings
from src.logger_config import configured_logger as logger


class RedisTradeRecordsClient:
    """Redis交易记录客户端"""

    def __init__(self):
        self.redis_client = None
        self.cleanup_scheduler_running = False
        self.cleanup_thread = None
        self._shutdown = False
        self.scheduler = Scheduler()  # 使用独立的调度器实例

    def connect(self) -> bool:
        """连接Redis"""
        try:
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )

            # 测试连接
            self.redis_client.ping()
            logger.info("Redis连接成功")

            # 启动清理调度器
            if settings.redis_trade_records_enabled:
                self._start_cleanup_scheduler()

            return True

        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            self.redis_client = None
            return False

    def disconnect(self):
        """断开Redis连接"""
        try:
            self._shutdown = True
            self.cleanup_scheduler_running = False
            self.scheduler.clear()  # 清理调度器任务

            if self.cleanup_thread and self.cleanup_thread.is_alive():
                self.cleanup_thread.join(timeout=2)

            if self.redis_client:
                self.redis_client.close()
                logger.info("Redis连接已断开")

        except Exception as e:
            logger.error(f"断开Redis连接时发生错误: {e}")

    def save_trade_record(self, order_id: str, trade_id: str, trade_data: Dict[str, Any]) -> bool:
        """保存交易记录到Redis"""
        if not self.redis_client or not settings.redis_trade_records_enabled:
            return False

        try:
            # 构建Redis key: trade_record:order_id_trade_id
            redis_key = f"{settings.redis_trade_records_prefix}{order_id}_{trade_id}"

            # 添加时间戳
            trade_data_with_timestamp = {
                **trade_data,
                "save_timestamp": datetime.now().isoformat(),
                "order_id": order_id,
                "trade_id": trade_id,
            }

            # 保存到Redis (24小时过期)
            result = self.redis_client.setex(
                redis_key,
                86400,  # 24小时过期
                json.dumps(trade_data_with_timestamp, ensure_ascii=False),
            )

            if result:
                logger.info(f"交易记录已保存到Redis: {redis_key}")
                return True
            else:
                logger.error(f"保存交易记录到Redis失败: {redis_key}")
                return False

        except Exception as e:
            logger.error(f"保存交易记录到Redis异常: {e}")
            return False

    def get_trade_record(self, order_id: str, trade_id: str) -> Optional[Dict[str, Any]]:
        """从Redis获取交易记录"""
        if not self.redis_client:
            return None

        try:
            redis_key = f"{settings.redis_trade_records_prefix}{order_id}_{trade_id}"
            data = self.redis_client.get(redis_key)

            if data:
                return json.loads(data)
            return None

        except Exception as e:
            logger.error(f"从Redis获取交易记录异常: {e}")
            return None

    def get_all_trade_records(self) -> Dict[str, Dict[str, Any]]:
        """获取所有交易记录"""
        if not self.redis_client:
            return {}

        try:
            pattern = f"{settings.redis_trade_records_prefix}*"
            keys = self.redis_client.keys(pattern)

            records = {}
            for key in keys:
                data = self.redis_client.get(key)
                if data:
                    records[key] = json.loads(data)

            return records

        except Exception as e:
            logger.error(f"获取所有交易记录异常: {e}")
            return {}

    def delete_trade_record(self, order_id: str, trade_id: str) -> bool:
        """删除交易记录"""
        if not self.redis_client:
            return False

        try:
            redis_key = f"{settings.redis_trade_records_prefix}{order_id}_{trade_id}"
            result = self.redis_client.delete(redis_key)

            if result:
                logger.info(f"交易记录已删除: {redis_key}")
                return True
            return False

        except Exception as e:
            logger.error(f"删除交易记录异常: {e}")
            return False

    def cleanup_all_trade_records(self) -> int:
        """清理所有交易记录"""
        if not self.redis_client:
            return 0

        try:
            pattern = f"{settings.redis_trade_records_prefix}*"
            keys = self.redis_client.keys(pattern)

            if not keys:
                logger.info("没有需要清理的交易记录")
                return 0

            deleted_count = self.redis_client.delete(*keys)
            logger.info(f"交易记录清理完成，删除了 {deleted_count} 条记录")
            return deleted_count

        except Exception as e:
            logger.error(f"清理交易记录异常: {e}")
            return 0

    def get_trade_records_count(self) -> int:
        """获取交易记录数量"""
        if not self.redis_client:
            return 0

        try:
            pattern = f"{settings.redis_trade_records_prefix}*"
            keys = self.redis_client.keys(pattern)
            return len(keys)

        except Exception as e:
            logger.error(f"获取交易记录数量异常: {e}")
            return 0

    def _start_cleanup_scheduler(self):
        """启动清理调度器"""
        if self.cleanup_scheduler_running:
            return

        logger.info(f"启动Redis交易记录清理调度器，清理时间: {settings.redis_trade_cleanup_time}")

        # 设置调度任务
        self.scheduler.clear()
        self.scheduler.every().day.at(settings.redis_trade_cleanup_time).do(
            self._daily_cleanup_task
        )

        self.cleanup_scheduler_running = True
        self.cleanup_thread = threading.Thread(target=self._cleanup_scheduler_worker, daemon=True)
        self.cleanup_thread.start()

    def _cleanup_scheduler_worker(self):
        """清理调度器工作线程"""
        while not self._shutdown and self.cleanup_scheduler_running:
            try:
                self.scheduler.run_pending()
                time.sleep(60)  # 每分钟检查一次
            except Exception as e:
                logger.error(f"清理调度器异常: {e}")
                time.sleep(60)

    def _daily_cleanup_task(self):
        """每日清理任务"""
        logger.info("开始执行每日交易记录清理任务")
        try:
            count_before = self.get_trade_records_count()
            deleted_count = self.cleanup_all_trade_records()

            logger.info(
                f"每日清理任务完成: 清理前 {count_before} 条记录，删除了 {deleted_count} 条记录"
            )

        except Exception as e:
            logger.error(f"每日清理任务异常: {e}")


# 全局Redis客户端实例
redis_trade_client = RedisTradeRecordsClient()
