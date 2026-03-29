"""
Trading data backup service.
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
from typing import Any, Dict

from schedule import Scheduler

from src.logger_config import configured_logger as logger
from src.remote_sync import sync_file_via_rsync


def get_backup_config() -> Dict[str, Any]:
    """Load backup configuration from environment variables."""
    return {
        "enabled": os.getenv("BACKUP_ENABLED", "true").lower() == "true",
        "backup_time": os.getenv("BACKUP_TIME", "15:05"),
        "backup_method": os.getenv("BACKUP_METHOD", "local"),
        "backup_format": os.getenv("BACKUP_FORMAT", "json"),
        "compress": os.getenv("BACKUP_COMPRESS", "true").lower() == "true",
        "keep_days": int(os.getenv("BACKUP_KEEP_DAYS", "30")),
        "local_backup_dir": os.getenv("BACKUP_LOCAL_DIR", "./data/backups"),
        "scp_host": os.getenv("SCP_HOST", ""),
        "scp_port": int(os.getenv("SCP_PORT", "22")),
        "scp_username": os.getenv("SCP_USERNAME", ""),
        "scp_password": os.getenv("SCP_PASSWORD", ""),
        "scp_key_file": os.getenv("SCP_KEY_FILE", ""),
        "scp_remote_dir": os.getenv("SCP_REMOTE_DIR", "/data/trading_backups"),
    }


class DatabaseBackupService:
    """Create and ship daily trading backups."""

    def __init__(self, db_path: str = "trading.db"):
        self.db_path = db_path
        self.config = get_backup_config()
        self.is_running = False
        self.scheduler_thread = None
        self.scheduler = Scheduler()

    def start_scheduler(self):
        """Start the daily backup scheduler."""
        if not self.config["enabled"]:
            logger.info("Backup service disabled")
            return

        logger.info(f"Starting backup scheduler, time={self.config['backup_time']}")
        self.scheduler.every().day.at(self.config["backup_time"]).do(self._daily_backup_job)

        self.is_running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()

    def stop_scheduler(self):
        """Stop the backup scheduler."""
        self.is_running = False
        self.scheduler.clear()
        logger.info("Backup scheduler stopped")

    def _run_scheduler(self):
        """Run scheduler loop."""
        while self.is_running:
            self.scheduler.run_pending()
            time.sleep(60)

    def _daily_backup_job(self):
        """Execute the scheduled backup job."""
        try:
            logger.info("Running daily backup job")
            today_data = self.get_today_data()

            if not today_data:
                logger.info("No data found for today, skipping backup")
                return

            backup_file = self.create_backup_file(today_data)
            success = self._dispatch_backup(backup_file)

            if success:
                logger.info("Daily backup completed")
            else:
                logger.error("Daily backup failed")

            if os.path.exists(backup_file) and self.config["backup_method"] != "local":
                os.remove(backup_file)
        except Exception as exc:
            logger.error(f"Daily backup job failed: {exc}")

    def _dispatch_backup(self, backup_file: str) -> bool:
        method = str(self.config["backup_method"]).strip().lower()
        if method == "local":
            return self._backup_to_local(backup_file)
        if method in {"scp", "rsync"}:
            return self._backup_via_rsync(backup_file)

        logger.error(f"Unsupported backup method: {self.config['backup_method']}")
        return False

    def get_today_data(self) -> Dict[str, Any]:
        """Fetch today's trading data from SQLite."""
        if not os.path.exists(self.db_path):
            logger.warning(f"Database file not found: {self.db_path}")
            return {}

        today = datetime.now().strftime("%Y-%m-%d")

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            data = {
                "backup_date": today,
                "backup_time": datetime.now().isoformat(),
                "trading_signals": [],
                "order_records": [],
            }

            cursor.execute(
                """
                SELECT * FROM trading_signals
                WHERE DATE(created_at) = ? OR DATE(signal_time) = ?
                """,
                (today, today),
            )
            data["trading_signals"] = [dict(row) for row in cursor.fetchall()]

            cursor.execute(
                """
                SELECT * FROM order_records
                WHERE DATE(created_at) = ? OR DATE(order_time) = ?
                """,
                (today, today),
            )
            data["order_records"] = [dict(row) for row in cursor.fetchall()]

            conn.close()

            total_records = len(data["trading_signals"]) + len(data["order_records"])
            logger.info(
                f"Fetched today data: signals={len(data['trading_signals'])}, "
                f"orders={len(data['order_records'])}"
            )
            return data if total_records > 0 else {}
        except Exception as exc:
            logger.error(f"Failed to fetch today data: {exc}")
            return {}

    def create_backup_file(self, data: Dict[str, Any]) -> str:
        """Create a backup file in JSON or SQLite format."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if self.config["backup_format"] == "json":
            filename = f"trading_backup_{timestamp}.json"
            content = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        elif self.config["backup_format"] == "sqlite":
            filename = f"trading_backup_{timestamp}.db"
            return self._create_sqlite_backup(data, filename)
        else:
            raise ValueError(f"Unsupported backup format: {self.config['backup_format']}")

        temp_dir = Path("./temp_backups")
        temp_dir.mkdir(exist_ok=True)
        backup_file = temp_dir / filename

        if self.config["compress"]:
            backup_file = backup_file.with_suffix(".json.gz")
            with gzip.open(backup_file, "wt", encoding="utf-8") as handle:
                handle.write(content)
        else:
            backup_file.write_text(content, encoding="utf-8")

        logger.info(f"Created backup file: {backup_file}")
        return str(backup_file)

    def _create_sqlite_backup(self, data: Dict[str, Any], filename: str) -> str:
        """Create a simplified SQLite backup."""
        temp_dir = Path("./temp_backups")
        temp_dir.mkdir(exist_ok=True)
        backup_file = temp_dir / filename

        conn = sqlite3.connect(str(backup_file))
        cursor = conn.cursor()

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

        for signal in data.get("trading_signals", []):
            cursor.execute(
                """
                INSERT INTO trading_signals
                (id, signal_id, stock_code, direction, volume, price, signal_time,
                 processed, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(
                    signal.get(key)
                    for key in [
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
                    order.get(key)
                    for key in [
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
        logger.info(f"Created sqlite backup file: {backup_file}")
        return str(backup_file)

    def _backup_to_local(self, backup_file: str) -> bool:
        """Copy the backup file to local backup storage."""
        try:
            backup_dir = Path(self.config["local_backup_dir"])
            backup_dir.mkdir(parents=True, exist_ok=True)

            target_file = backup_dir / Path(backup_file).name
            shutil.copy2(backup_file, target_file)
            logger.info(f"Local backup completed: {target_file}")

            self._cleanup_old_backups(backup_dir)
            return True
        except Exception as exc:
            logger.error(f"Local backup failed: {exc}")
            return False

    def _backup_via_rsync(self, backup_file: str) -> bool:
        """Upload backup files to the remote host via rsync."""
        if not self.config["scp_host"]:
            logger.error("Remote backup requires SCP_HOST")
            return False

        if self.config["scp_password"] and not self.config["scp_key_file"]:
            logger.error("rsync backup does not support SCP_PASSWORD; use SSH keys or ssh config")
            return False

        try:
            remote_file = sync_file_via_rsync(
                file=backup_file,
                remote_base=self.config["scp_remote_dir"],
                alias_or_host=self.config["scp_host"],
                username=self.config["scp_username"] or None,
                port=self.config["scp_port"],
                identity_file=self.config["scp_key_file"] or None,
                timeout=30,
            )
            logger.info(f"rsync backup completed: {self.config['scp_host']}:{remote_file}")
            return True
        except Exception as exc:
            logger.error(f"rsync backup failed: {type(exc).__name__}: {exc}")
            return False

    def _cleanup_old_backups(self, backup_dir: Path):
        """Delete expired local backup files."""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.config["keep_days"])
            for file_path in backup_dir.glob("trading_backup_*"):
                if file_path.is_file():
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff_date:
                        file_path.unlink()
                        logger.info(f"Deleted expired backup file: {file_path}")
        except Exception as exc:
            logger.error(f"Failed to clean up expired backups: {exc}")

    def manual_backup(self) -> bool:
        """Run a manual backup immediately."""
        logger.info("Starting manual backup")

        try:
            today_data = self.get_today_data()
            if not today_data:
                logger.info("No data to back up")
                return True

            backup_file = self.create_backup_file(today_data)
            success = self._dispatch_backup(backup_file)

            if os.path.exists(backup_file) and self.config["backup_method"] != "local":
                os.remove(backup_file)

            if success:
                logger.info("Manual backup completed")
            else:
                logger.error("Manual backup failed")
            return success
        except Exception as exc:
            logger.error(f"Manual backup failed: {exc}")
            return False


if __name__ == "__main__":
    DatabaseBackupService().manual_backup()
