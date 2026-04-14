"""
连接管理器 - 负责处理Redis和QMT的自动重连逻辑
"""

import threading
import time
from enum import Enum
from typing import Any, Callable, Optional

from src.infrastructure.config import settings
from src.infrastructure.logger_config import configured_logger as logger


class ConnectionState(Enum):
    """连接状态枚举"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class ConnectionManager:
    """通用连接管理器"""

    def __init__(
        self,
        name: str,
        connect_func: Callable[[], bool],
        disconnect_func: Callable[[], None],
        health_check_func: Callable[[], bool],
        notifier: Optional[Any] = None,
    ):
        self.name = name
        self.connect_func = connect_func
        self.disconnect_func = disconnect_func
        self.health_check_func = health_check_func
        self.notifier = notifier

        self.state = ConnectionState.DISCONNECTED
        self.is_running = False
        self.reconnect_thread = None
        self.health_check_thread = None
        self.reconnect_attempts = 0
        self.last_connect_time = None
        self.state_lock = threading.Lock()

    def start(self) -> bool:
        """启动连接管理器"""
        logger.info(f"启动 {self.name} 连接管理器")

        with self.state_lock:
            self.is_running = True

        # 首次连接
        if self._connect():
            if settings.auto_reconnect_enabled:
                self._start_health_check()
            return True
        else:
            if settings.auto_reconnect_enabled:
                self._start_reconnect()
                return True  # 即使首次连接失败，也启动重连机制
            with self.state_lock:
                self.is_running = False
            return False

    def stop(self):
        """停止连接管理器"""
        logger.info(f"停止 {self.name} 连接管理器")

        with self.state_lock:
            self.is_running = False

        # 停止健康检查线程
        if self.health_check_thread and self.health_check_thread.is_alive():
            self.health_check_thread.join(timeout=1)

        # 停止重连线程
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            self.reconnect_thread.join(timeout=1)

        # 断开连接
        if self.state == ConnectionState.CONNECTED:
            self._disconnect()

    def get_state(self) -> ConnectionState:
        """获取当前连接状态"""
        with self.state_lock:
            return self.state

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.get_state() == ConnectionState.CONNECTED

    def force_reconnect(self):
        """强制重连"""
        logger.info(f"强制重连 {self.name}")

        with self.state_lock:
            if self.state == ConnectionState.CONNECTED:
                self._disconnect()

            if not settings.auto_reconnect_enabled:
                logger.warning(f"{self.name} 自动重连已禁用，不执行重连")
                return

            if self.state != ConnectionState.RECONNECTING:
                self._start_reconnect()

    def _connect(self) -> bool:
        """执行连接"""
        with self.state_lock:
            if self.state == ConnectionState.CONNECTING:
                return False
            self.state = ConnectionState.CONNECTING

        try:
            logger.info(f"正在连接 {self.name}...")
            success = self.connect_func()

            with self.state_lock:
                if success:
                    self.state = ConnectionState.CONNECTED
                    self.reconnect_attempts = 0
                    self.last_connect_time = time.time()
                    logger.info(f"{self.name} 连接成功")

                    # 发送连接恢复通知
                    if self.notifier and hasattr(self.notifier, "notify_connection_restored"):
                        self.notifier.notify_connection_restored(self.name)
                else:
                    self.state = ConnectionState.DISCONNECTED
                    logger.error(f"{self.name} 连接失败")

            return success

        except Exception as e:
            logger.error(f"{self.name} 连接异常: {e}")
            with self.state_lock:
                self.state = ConnectionState.DISCONNECTED
            return False

    def _disconnect(self):
        """执行断开连接"""
        try:
            logger.info(f"正在断开 {self.name} 连接...")
            self.disconnect_func()

            with self.state_lock:
                self.state = ConnectionState.DISCONNECTED

            logger.info(f"{self.name} 连接已断开")

        except Exception as e:
            logger.error(f"断开 {self.name} 连接时发生错误: {e}")
            with self.state_lock:
                self.state = ConnectionState.DISCONNECTED

    def _start_health_check(self):
        """启动健康检查线程"""
        if self.health_check_thread and self.health_check_thread.is_alive():
            return

        self.health_check_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self.health_check_thread.start()
        logger.info(f"{self.name} 健康检查已启动，间隔: {settings.health_check_interval}秒")

    def _health_check_loop(self):
        """健康检查循环"""
        while self.is_running:
            try:
                time.sleep(settings.health_check_interval)

                if not self.is_running:
                    break

                # 只对已连接状态进行健康检查
                if self.state == ConnectionState.CONNECTED:
                    try:
                        is_healthy = self.health_check_func()
                        if not is_healthy:
                            logger.warning(f"{self.name} 健康检查失败，开始重连")

                            # 发送连接丢失通知
                            if self.notifier and hasattr(self.notifier, "notify_connection_lost"):
                                self.notifier.notify_connection_lost(self.name)

                            with self.state_lock:
                                self.state = ConnectionState.DISCONNECTED

                            self._start_reconnect()
                            break  # 退出健康检查，让重连线程接管
                    except Exception as e:
                        logger.error(f"{self.name} 健康检查异常: {e}")

            except Exception as e:
                logger.error(f"{self.name} 健康检查循环异常: {e}")
                time.sleep(5)  # 异常情况下短暂休眠

        logger.debug(f"{self.name} 健康检查线程已退出")

    def _start_reconnect(self):
        """启动重连线程"""
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            return

        with self.state_lock:
            self.state = ConnectionState.RECONNECTING

        self.reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
        self.reconnect_thread.start()
        logger.info(f"{self.name} 重连线程已启动")

    def _reconnect_loop(self):
        """重连循环"""
        while self.is_running and self.reconnect_attempts < settings.reconnect_max_attempts:
            try:
                self.reconnect_attempts += 1

                # 计算重连延迟（指数退避）
                delay = min(
                    settings.reconnect_initial_delay
                    * (settings.reconnect_backoff_factor ** (self.reconnect_attempts - 1)),
                    settings.reconnect_max_delay,
                )

                logger.info(
                    f"{self.name} 第 {self.reconnect_attempts}/{settings.reconnect_max_attempts} 次重连，"
                    f"将在 {delay:.1f} 秒后尝试"
                )

                # 等待重连延迟
                for _ in range(int(delay)):
                    if not self.is_running:
                        logger.info(f"{self.name} 服务停止，取消重连")
                        return
                    time.sleep(1)

                if not self.is_running:
                    logger.info(f"{self.name} 服务停止，取消重连")
                    return

                # 尝试重连
                if self._connect():
                    logger.info(f"{self.name} 重连成功")
                    self._start_health_check()  # 重新启动健康检查
                    return
                else:
                    logger.warning(f"{self.name} 第 {self.reconnect_attempts} 次重连失败")

            except Exception as e:
                logger.error(f"{self.name} 重连异常: {e}")

        # 重连失败
        with self.state_lock:
            self.state = ConnectionState.FAILED

        logger.error(f"{self.name} 重连失败，已达到最大尝试次数 {settings.reconnect_max_attempts}")

        # 发送重连失败通知
        if self.notifier and hasattr(self.notifier, "notify_reconnect_failed"):
            self.notifier.notify_reconnect_failed(self.name, self.reconnect_attempts)


class MultiConnectionManager:
    """多连接管理器"""

    def __init__(self):
        self.managers = {}
        self.is_running = False

    def add_connection(self, name: str, manager: ConnectionManager):
        """添加连接管理器"""
        self.managers[name] = manager

    def start_all(self) -> bool:
        """启动所有连接管理器"""
        logger.info("启动所有连接管理器")
        self.is_running = True

        all_success = True
        for name, manager in self.managers.items():
            try:
                success = manager.start()
                if not success:
                    all_success = False
                    logger.warning(f"{name} 连接管理器启动失败")
            except Exception as e:
                logger.error(f"启动 {name} 连接管理器时发生错误: {e}")
                all_success = False

        return all_success

    def stop_all(self):
        """停止所有连接管理器"""
        logger.info("停止所有连接管理器")
        self.is_running = False

        for name, manager in self.managers.items():
            try:
                manager.stop()
            except Exception as e:
                logger.error(f"停止 {name} 连接管理器时发生错误: {e}")

    def get_connection_status(self) -> dict:
        """获取所有连接状态"""
        status = {}
        for name, manager in self.managers.items():
            status[name] = {
                "state": manager.get_state().value,
                "connected": manager.is_connected(),
                "reconnect_attempts": manager.reconnect_attempts,
                "last_connect_time": manager.last_connect_time,
            }
        return status

    def force_reconnect_all(self):
        """强制重连所有连接"""
        logger.info("强制重连所有连接")
        for name, manager in self.managers.items():
            try:
                manager.force_reconnect()
            except Exception as e:
                logger.error(f"强制重连 {name} 时发生错误: {e}")
