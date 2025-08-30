"""
数据备份服务
简化版本，配置从环境变量读取
"""

import gzip
import json
import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from schedule import Scheduler

from src.logger_config import configured_logger as logger

try:
    import paramiko

    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False
    logger.warning("paramiko未安装，无法使用SCP备份功能")

try:
    from ftplib import FTP

    HAS_FTP = True
except ImportError:
    HAS_FTP = False

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def get_backup_config():
    """从环境变量获取备份配置"""
    return {
        "enabled": os.getenv("BACKUP_ENABLED", "true").lower() == "true",
        "backup_time": os.getenv("BACKUP_TIME", "15:05"),
        "backup_method": os.getenv("BACKUP_METHOD", "local"),
        "backup_format": os.getenv("BACKUP_FORMAT", "json"),
        "compress": os.getenv("BACKUP_COMPRESS", "true").lower() == "true",
        "keep_days": int(os.getenv("BACKUP_KEEP_DAYS", "30")),
        "local_backup_dir": os.getenv("BACKUP_LOCAL_DIR", "./data/backups"),
        # SCP配置
        "scp_host": os.getenv("SCP_HOST", ""),
        "scp_port": int(os.getenv("SCP_PORT", "22")),
        "scp_username": os.getenv("SCP_USERNAME", ""),
        "scp_password": os.getenv("SCP_PASSWORD", ""),
        "scp_key_file": os.getenv("SCP_KEY_FILE", ""),
        "scp_remote_dir": os.getenv("SCP_REMOTE_DIR", "/data/trading_backups"),
    }


class DatabaseBackupService:
    """数据库备份服务"""

    def __init__(self, db_path: str = "trading.db"):
        self.db_path = db_path
        self.config = get_backup_config()
        self.is_running = False
        self.scheduler_thread = None
        self.scheduler = Scheduler()  # 使用独立的调度器实例

    def start_scheduler(self):
        """启动定时备份调度器"""
        if not self.config["enabled"]:
            logger.info("数据备份功能已禁用")
            return

        logger.info(f"启动备份调度器，备份时间: {self.config['backup_time']}")

        # 设置定时任务
        self.scheduler.every().day.at(self.config["backup_time"]).do(self._daily_backup_job)

        self.is_running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()

    def stop_scheduler(self):
        """停止定时备份调度器"""
        self.is_running = False
        self.scheduler.clear()
        logger.info("备份调度器已停止")

    def _run_scheduler(self):
        """运行调度器"""
        while self.is_running:
            self.scheduler.run_pending()
            time.sleep(60)  # 每分钟检查一次

    def _daily_backup_job(self):
        """每日备份任务"""
        try:
            logger.info("开始执行每日数据备份...")

            # 获取今日数据
            today_data = self.get_today_data()

            if not today_data:
                logger.info("今日无数据，跳过备份")
                return

            # 创建备份文件
            backup_file = self.create_backup_file(today_data)

            # 根据配置选择备份方式
            success = False
            if self.config["backup_method"] == "local":
                success = self._backup_to_local(backup_file)
            elif self.config["backup_method"] == "scp":
                success = self._backup_via_scp(backup_file)

            if success:
                logger.info("每日数据备份完成")
            else:
                logger.error("每日数据备份失败")

            # 清理临时文件
            if os.path.exists(backup_file) and self.config["backup_method"] != "local":
                os.remove(backup_file)

        except Exception as e:
            logger.error(f"每日备份任务异常: {e}")

    def get_today_data(self) -> Dict[str, Any]:
        """获取今日数据"""
        if not os.path.exists(self.db_path):
            logger.warning(f"数据库文件不存在: {self.db_path}")
            return {}

        today = datetime.now().strftime("%Y-%m-%d")

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # 返回字典格式
            cursor = conn.cursor()

            data = {
                "backup_date": today,
                "backup_time": datetime.now().isoformat(),
                "trading_signals": [],
                "order_records": [],
                "service_logs": [],
            }

            # 获取今日交易信号
            cursor.execute(
                """
                SELECT * FROM trading_signals
                WHERE DATE(created_at) = ? OR DATE(signal_time) = ?
            """,
                (today, today),
            )
            data["trading_signals"] = [dict(row) for row in cursor.fetchall()]

            # 获取今日订单记录
            cursor.execute(
                """
                SELECT * FROM order_records
                WHERE DATE(created_at) = ? OR DATE(order_time) = ?
            """,
                (today, today),
            )
            data["order_records"] = [dict(row) for row in cursor.fetchall()]

            # 获取今日服务日志（可选）
            cursor.execute(
                """
                SELECT * FROM service_logs
                WHERE DATE(timestamp) = ?
            """,
                (today,),
            )
            data["service_logs"] = [dict(row) for row in cursor.fetchall()]

            conn.close()

            total_records = (
                len(data["trading_signals"])
                + len(data["order_records"])
                + len(data["service_logs"])
            )
            logger.info(
                f"获取今日数据: 信号{len(data['trading_signals'])}条, "
                f"订单{len(data['order_records'])}条, "
                f"日志{len(data['service_logs'])}条"
            )

            return data if total_records > 0 else {}

        except Exception as e:
            logger.error(f"获取今日数据失败: {e}")
            return {}

    def create_backup_file(self, data: Dict[str, Any]) -> str:
        """创建备份文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if self.config["backup_format"] == "json":
            filename = f"trading_backup_{timestamp}.json"
            content = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        elif self.config["backup_format"] == "sqlite":
            filename = f"trading_backup_{timestamp}.db"
            return self._create_sqlite_backup(data, filename)
        else:
            raise ValueError(f"不支持的备份格式: {self.config['backup_format']}")

        # 写入文件
        temp_dir = Path("./temp_backups")
        temp_dir.mkdir(exist_ok=True)
        backup_file = temp_dir / filename

        if self.config["compress"] and self.config["backup_format"] == "json":
            # 压缩JSON文件
            backup_file = backup_file.with_suffix(".json.gz")
            with gzip.open(backup_file, "wt", encoding="utf-8") as f:
                f.write(content)
        else:
            with open(backup_file, "w", encoding="utf-8") as f:
                f.write(content)

        logger.info(f"创建备份文件: {backup_file}")
        return str(backup_file)

    def _create_sqlite_backup(self, data: Dict[str, Any], filename: str) -> str:
        """创建SQLite格式备份"""
        temp_dir = Path("./temp_backups")
        temp_dir.mkdir(exist_ok=True)
        backup_file = temp_dir / filename

        # 创建备份数据库
        conn = sqlite3.connect(str(backup_file))
        cursor = conn.cursor()

        # 创建表结构（简化版）
        cursor.execute(
            """
            CREATE TABLE trading_signals (
                id INTEGER PRIMARY KEY,
                signal_id TEXT,
                stock_code TEXT,
                direction TEXT,
                volume INTEGER,
                price REAL,
                signal_time TEXT,
                processed INTEGER,
                error_message TEXT,
                created_at TEXT
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE order_records (
                id INTEGER PRIMARY KEY,
                signal_id TEXT,
                order_id TEXT,
                stock_code TEXT,
                direction TEXT,
                volume INTEGER,
                price REAL,
                order_status TEXT,
                order_time TEXT,
                filled_price REAL,
                filled_volume INTEGER,
                filled_time TEXT,
                error_message TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """
        )

        # 插入数据
        for signal in data.get("trading_signals", []):
            cursor.execute(
                """
                INSERT INTO trading_signals
                (id, signal_id, stock_code, direction, volume, price, signal_time,
                 processed, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                tuple(
                    signal.get(k)
                    for k in [
                        "id",
                        "signal_id",
                        "stock_code",
                        "direction",
                        "volume",
                        "price",
                        "signal_time",
                        "processed",
                        "error_message",
                        "created_at",
                    ]
                ),
            )

        for order in data.get("order_records", []):
            cursor.execute(
                """
                INSERT INTO order_records
                (id, signal_id, order_id, stock_code, direction, volume, price,
                 order_status, order_time, filled_price, filled_volume, filled_time,
                 error_message, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                tuple(
                    order.get(k)
                    for k in [
                        "id",
                        "signal_id",
                        "order_id",
                        "stock_code",
                        "direction",
                        "volume",
                        "price",
                        "order_status",
                        "order_time",
                        "filled_price",
                        "filled_volume",
                        "filled_time",
                        "error_message",
                        "created_at",
                        "updated_at",
                    ]
                ),
            )

        conn.commit()
        conn.close()

        return str(backup_file)

    def _backup_to_local(self, backup_file: str) -> bool:
        """本地备份"""
        try:
            backup_dir = Path(self.config["local_backup_dir"])
            backup_dir.mkdir(parents=True, exist_ok=True)

            target_file = backup_dir / Path(backup_file).name
            shutil.copy2(backup_file, target_file)

            logger.info(f"本地备份完成: {target_file}")

            # 清理过期备份
            self._cleanup_old_backups(backup_dir)

            return True
        except Exception as e:
            logger.error(f"本地备份失败: {e}")
            return False

    def _backup_via_scp(self, backup_file: str) -> bool:
        """通过SCP备份到Ubuntu服务器"""
        if not HAS_PARAMIKO:
            logger.error("SCP备份需要安装paramiko: pip install paramiko")
            return False

        try:
            # 创建SSH客户端
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # 连接参数
            key_file = None
            if self.config["scp_key_file"]:
                key_file = str(Path(self.config["scp_key_file"]).expanduser().resolve())

            logger.info(
                f"尝试SCP连接: {self.config['scp_username']}@{self.config['scp_host']}:{self.config['scp_port']}"
            )

            if key_file and os.path.exists(key_file):
                logger.info(f"使用SSH密钥: {key_file}")
                # 加载私钥
                try:
                    pkey = paramiko.RSAKey.from_private_key_file(key_file)
                    ssh.connect(
                        hostname=self.config["scp_host"],
                        port=self.config["scp_port"],
                        username=self.config["scp_username"],
                        pkey=pkey,
                        timeout=30,
                    )
                except paramiko.ssh_exception.PasswordRequiredException:
                    logger.error("私钥需要密码，但未提供")
                    return False
                except Exception as key_error:
                    logger.error(f"加载私钥失败: {key_error}")
                    return False
            elif self.config["scp_password"]:
                logger.info("使用密码认证")
                ssh.connect(
                    hostname=self.config["scp_host"],
                    port=self.config["scp_port"],
                    username=self.config["scp_username"],
                    password=self.config["scp_password"],
                    timeout=30,
                )
            else:
                logger.error("既没有找到有效的SSH密钥，也没有提供密码")
                return False

            logger.info("SSH连接成功")

            # 创建SFTP客户端
            sftp = ssh.open_sftp()

            # 确保远程目录存在
            remote_dir = self.config["scp_remote_dir"]
            # 如果是相对路径（以~开始），让SFTP自己处理
            if remote_dir.startswith("~/"):
                # SFTP会自动处理~路径
                pass

            try:
                sftp.listdir(remote_dir)
                logger.info(f"远程目录已存在: {remote_dir}")
            except OSError:
                try:
                    # 使用SSH命令创建目录，更可靠
                    stdin, stdout, stderr = ssh.exec_command(f'mkdir -p "{remote_dir}"')
                    exit_status = stdout.channel.recv_exit_status()
                    if exit_status == 0:
                        logger.info(f"创建远程目录成功: {remote_dir}")
                    else:
                        error_msg = stderr.read().decode()
                        logger.error(f"创建远程目录失败: {error_msg}")
                        return False
                except Exception as mkdir_error:
                    logger.error(f"创建远程目录失败: {mkdir_error}")
                    return False

            # 上传文件
            remote_file = f"{self.config['scp_remote_dir']}/{Path(backup_file).name}"
            logger.info(f"开始上传文件: {backup_file} -> {remote_file}")

            sftp.put(backup_file, remote_file)

            # 验证上传成功
            remote_stat = sftp.stat(remote_file)
            local_stat = os.stat(backup_file)
            if remote_stat.st_size == local_stat.st_size:
                logger.info(f"文件上传成功，大小: {remote_stat.st_size} 字节")
            else:
                logger.warning(
                    f"文件大小不匹配: 本地{local_stat.st_size}，远程{remote_stat.st_size}"
                )

            sftp.close()
            ssh.close()

            logger.info(f"SCP备份完成: {self.config['scp_host']}:{remote_file}")
            return True

        except Exception as e:
            logger.error(f"SCP备份失败: {type(e).__name__}: {e}")
            return False

    def _cleanup_old_backups(self, backup_dir: Path):
        """清理过期的本地备份文件"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.config["keep_days"])

            for file_path in backup_dir.glob("trading_backup_*"):
                if file_path.is_file():
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff_date:
                        file_path.unlink()
                        logger.info(f"删除过期备份文件: {file_path}")

        except Exception as e:
            logger.error(f"清理过期备份失败: {e}")

    def manual_backup(self) -> bool:
        """手动备份"""
        logger.info("开始手动备份...")

        try:
            # 获取今日数据
            today_data = self.get_today_data()

            if not today_data:
                logger.info("无数据需要备份")
                return True

            # 创建备份文件
            backup_file = self.create_backup_file(today_data)

            # 根据配置选择备份方式
            success = False
            if self.config["backup_method"] == "local":
                success = self._backup_to_local(backup_file)
            elif self.config["backup_method"] == "scp":
                success = self._backup_via_scp(backup_file)

            # 清理临时文件
            if os.path.exists(backup_file) and self.config["backup_method"] != "local":
                os.remove(backup_file)

            if success:
                logger.info("手动备份完成")
            else:
                logger.error("手动备份失败")

            return success

        except Exception as e:
            logger.error(f"手动备份异常: {e}")
            return False


if __name__ == "__main__":
    # 测试用例
    backup_service = DatabaseBackupService()
    backup_service.manual_backup()
