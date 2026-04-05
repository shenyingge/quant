"""策略状态的持久化适配层。"""

from datetime import date, datetime
from typing import List

from src.infrastructure.db import SessionLocal, StrategySignalHistory
from src.logger_config import logger
from src.strategy.core.models import SignalEvent, StrategyDecision


class StrategySignalRepository:
    """从数据库读取/写入策略事件，但不参与策略判断。"""

    def __init__(self, strategy_name: str = "t0_601138"):
        self.strategy_name = strategy_name

    def load_today_history(self, trade_date: date) -> List[SignalEvent]:
        try:
            db = SessionLocal()
            records = (
                db.query(StrategySignalHistory)
                .filter(
                    StrategySignalHistory.strategy_name == self.strategy_name,
                    StrategySignalHistory.trade_date == trade_date,
                    StrategySignalHistory.signal_action != "observe",
                )
                .order_by(StrategySignalHistory.signal_time.asc())
                .all()
            )
            db.close()
            return [
                SignalEvent(
                    action=record.signal_action,
                    branch=record.branch_locked,
                    price=record.price,
                    volume=record.suggested_volume or 0,
                    signal_time=record.signal_time,
                )
                for record in records
            ]
        except Exception as e:
            logger.warning(f"查询信号历史失败: {e}")
            return []

    def save_signal(self, trade_date: date, regime: str, stock_code: str, signal: StrategyDecision):
        try:
            db = SessionLocal()
            record = StrategySignalHistory(
                strategy_name=self.strategy_name,
                trade_date=trade_date,
                signal_time=datetime.now(),
                regime=regime,
                signal_action=signal.action,
                branch_locked=signal.branch,
                stock_code=stock_code,
                price=signal.price,
                suggested_volume=signal.volume,
            )
            db.add(record)
            db.commit()
            db.close()
            logger.info("信号历史已保存")
        except Exception as e:
            logger.error(f"保存信号历史失败: {e}")
