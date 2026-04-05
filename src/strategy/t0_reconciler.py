"""End-of-day T0 position and trade reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Dict, Iterable, List, Optional

from src.config import settings
from src.infrastructure.db import AccountPosition, OrderRecord, SessionLocal
from src.logger_config import configured_logger as logger
from src.infrastructure.notifications import FeishuNotifier
from src.strategy.position_syncer import PositionSyncer


@dataclass
class TradeSummary:
    filled_orders: int = 0
    buy_volume: int = 0
    sell_volume: int = 0
    buy_amount: float = 0.0
    sell_amount: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filled_orders": self.filled_orders,
            "buy_volume": self.buy_volume,
            "sell_volume": self.sell_volume,
            "buy_amount": round(self.buy_amount, 4),
            "sell_amount": round(self.sell_amount, 4),
            "net_volume": self.buy_volume - self.sell_volume,
            "net_amount": round(self.buy_amount - self.sell_amount, 4),
        }


class T0Reconciler:
    """Read-only reconciliation between QMT, Meta DB, and local T0 state."""

    def __init__(
        self,
        stock_code: Optional[str] = None,
        account_id: Optional[str] = None,
        notifier: Optional[FeishuNotifier] = None,
    ) -> None:
        self.stock_code = stock_code or settings.t0_stock_code
        self.account_id = account_id or settings.qmt_account_id
        self.notifier = notifier or FeishuNotifier()

    def run(
        self,
        trader: Any,
        *,
        trade_date: Optional[date] = None,
        notify: bool = True,
    ) -> Dict[str, Any]:
        target_date = trade_date or date.today()
        issues: List[str] = []

        qmt_position = trader.query_position(self.stock_code)
        if qmt_position is None:
            issues.append("QMT position query returned no data")
            qmt_position = self._empty_position()

        qmt_orders = trader.get_today_orders(self.stock_code)
        if qmt_orders is None:
            issues.append("QMT order query returned no data")
            qmt_orders = []

        strategy_position = PositionSyncer().load_position() or {}
        db_position, db_orders = self._load_meta_db_state(target_date)

        issues.extend(self._compare_positions("Meta DB", qmt_position, db_position))
        issues.extend(self._compare_positions("Strategy state", qmt_position, strategy_position))

        qmt_trade_summary = self._summarize_qmt_orders(qmt_orders)
        db_trade_summary = self._summarize_db_orders(db_orders)
        issues.extend(self._compare_trade_summaries(qmt_trade_summary, db_trade_summary))

        report = {
            "trade_date": target_date.isoformat(),
            "stock_code": self.stock_code,
            "account_id": self.account_id,
            "ok": not issues,
            "issues": issues,
            "position_comparison": {
                "qmt": self._position_snapshot_to_dict(qmt_position),
                "meta_db": self._position_snapshot_to_dict(db_position),
                "strategy_state": self._position_snapshot_to_dict(strategy_position),
            },
            "trade_comparison": {
                "qmt": qmt_trade_summary.to_dict(),
                "meta_db": db_trade_summary.to_dict(),
            },
        }

        if issues:
            logger.warning(
                "T0 end-of-day reconciliation found {} issue(s) for {}: {}",
                len(issues),
                self.stock_code,
                " | ".join(issues),
            )
            if notify:
                self.notifier.notify_runtime_event(
                    "策略引擎",
                    "收盘对账异常",
                    self._format_issue_message(issues, report),
                    "warning",
                )
        else:
            logger.info(
                "T0 end-of-day reconciliation passed for {}: position and trade summaries match",
                self.stock_code,
            )

        return report

    def _load_meta_db_state(self, trade_date: date) -> tuple[Dict[str, Any], List[OrderRecord]]:
        session = SessionLocal()
        try:
            db_position = (
                session.query(AccountPosition)
                .filter(
                    AccountPosition.account_id == self.account_id,
                    AccountPosition.stock_code == self.stock_code,
                )
                .first()
            )

            day_start = datetime.combine(trade_date, time.min)
            day_end = datetime.combine(trade_date, time.max)
            db_orders = (
                session.query(OrderRecord)
                .filter(
                    OrderRecord.stock_code == self.stock_code,
                    OrderRecord.filled_volume > 0,
                    OrderRecord.filled_time.isnot(None),
                    OrderRecord.filled_time >= day_start,
                    OrderRecord.filled_time <= day_end,
                )
                .order_by(OrderRecord.filled_time.asc(), OrderRecord.id.asc())
                .all()
            )
            return self._account_position_to_dict(db_position), db_orders
        finally:
            session.close()

    def _compare_positions(
        self,
        label: str,
        qmt_position: Dict[str, Any],
        other_position: Dict[str, Any],
    ) -> List[str]:
        issues: List[str] = []
        other_key = label.lower().replace(" ", "_")
        qmt_snapshot = self._position_snapshot_to_dict(qmt_position)
        other_snapshot = self._position_snapshot_to_dict(other_position)
        if int(qmt_snapshot.get("volume", 0)) != int(other_snapshot.get("volume", 0)):
            issues.append(
                f"{label} total volume mismatch: qmt={int(qmt_snapshot.get('volume', 0))}, "
                f"{other_key}={int(other_snapshot.get('volume', 0))}"
            )
        if int(qmt_snapshot.get("can_use_volume", 0)) != int(other_snapshot.get("can_use_volume", 0)):
            issues.append(
                f"{label} available volume mismatch: qmt={int(qmt_snapshot.get('can_use_volume', 0))}, "
                f"{other_key}={int(other_snapshot.get('can_use_volume', 0))}"
            )
        return issues

    def _compare_trade_summaries(
        self,
        qmt_summary: TradeSummary,
        db_summary: TradeSummary,
    ) -> List[str]:
        issues: List[str] = []
        if qmt_summary.buy_volume != db_summary.buy_volume:
            issues.append(
                f"Buy volume mismatch: qmt={qmt_summary.buy_volume}, meta_db={db_summary.buy_volume}"
            )
        if qmt_summary.sell_volume != db_summary.sell_volume:
            issues.append(
                f"Sell volume mismatch: qmt={qmt_summary.sell_volume}, meta_db={db_summary.sell_volume}"
            )
        if qmt_summary.filled_orders != db_summary.filled_orders:
            issues.append(
                f"Filled order count mismatch: qmt={qmt_summary.filled_orders}, meta_db={db_summary.filled_orders}"
            )
        if abs(qmt_summary.buy_amount - db_summary.buy_amount) > 1.0:
            issues.append(
                f"Buy amount mismatch: qmt={qmt_summary.buy_amount:.2f}, meta_db={db_summary.buy_amount:.2f}"
            )
        if abs(qmt_summary.sell_amount - db_summary.sell_amount) > 1.0:
            issues.append(
                f"Sell amount mismatch: qmt={qmt_summary.sell_amount:.2f}, meta_db={db_summary.sell_amount:.2f}"
            )
        return issues

    def _summarize_qmt_orders(self, orders: Iterable[Dict[str, Any]]) -> TradeSummary:
        summary = TradeSummary()
        for order in orders:
            traded_volume = int(order.get("traded_volume") or 0)
            traded_price = float(order.get("traded_price") or 0.0)
            if traded_volume <= 0:
                continue

            summary.filled_orders += 1
            direction = str(order.get("direction") or "").upper()
            if direction == "BUY":
                summary.buy_volume += traded_volume
                summary.buy_amount += traded_volume * traded_price
            elif direction == "SELL":
                summary.sell_volume += traded_volume
                summary.sell_amount += traded_volume * traded_price
        return summary

    def _summarize_db_orders(self, orders: Iterable[OrderRecord]) -> TradeSummary:
        summary = TradeSummary()
        for order in orders:
            filled_volume = int(getattr(order, "filled_volume", 0) or 0)
            filled_price = float(
                getattr(order, "filled_price", 0) or getattr(order, "price", 0) or 0.0
            )
            if filled_volume <= 0:
                continue

            summary.filled_orders += 1
            direction = str(getattr(order, "direction", "") or "").upper()
            if direction == "BUY":
                summary.buy_volume += filled_volume
                summary.buy_amount += filled_volume * filled_price
            elif direction == "SELL":
                summary.sell_volume += filled_volume
                summary.sell_amount += filled_volume * filled_price
        return summary

    def _account_position_to_dict(self, row: Optional[AccountPosition]) -> Dict[str, Any]:
        if row is None:
            return self._empty_position()
        return {
            "stock_code": row.stock_code,
            "volume": int(row.total_volume or 0),
            "can_use_volume": int(row.available_volume or 0),
            "open_price": float(row.avg_price or 0.0),
            "snapshot_time": row.snapshot_time.isoformat() if row.snapshot_time else None,
            "snapshot_source": row.snapshot_source,
        }

    def _position_snapshot_to_dict(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "stock_code": snapshot.get("stock_code") or self.stock_code,
            "volume": int(snapshot.get("volume", snapshot.get("total_position", 0)) or 0),
            "can_use_volume": int(
                snapshot.get("can_use_volume", snapshot.get("available_volume", 0)) or 0
            ),
            "open_price": float(
                snapshot.get("open_price", snapshot.get("cost_price", 0.0)) or 0.0
            ),
            "snapshot_time": snapshot.get("snapshot_time") or snapshot.get("last_sync_time"),
            "snapshot_source": snapshot.get("snapshot_source") or snapshot.get("last_sync_source"),
        }

    def _empty_position(self) -> Dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "volume": 0,
            "can_use_volume": 0,
            "open_price": 0.0,
            "snapshot_time": None,
            "snapshot_source": None,
        }

    def _format_issue_message(self, issues: List[str], report: Dict[str, Any]) -> str:
        position = report["position_comparison"]
        trades = report["trade_comparison"]
        lines = [
            f"股票: {self.stock_code}",
            f"问题数: {len(issues)}",
            f"QMT持仓: total={position['qmt']['volume']}, available={position['qmt']['can_use_volume']}",
            f"Meta DB持仓: total={position['meta_db']['volume']}, available={position['meta_db']['can_use_volume']}",
            f"策略状态持仓: total={position['strategy_state']['volume']}, available={position['strategy_state']['can_use_volume']}",
            (
                f"QMT成交汇总: buy={trades['qmt']['buy_volume']}, sell={trades['qmt']['sell_volume']}, "
                f"filled_orders={trades['qmt']['filled_orders']}"
            ),
            (
                f"Meta DB成交汇总: buy={trades['meta_db']['buy_volume']}, sell={trades['meta_db']['sell_volume']}, "
                f"filled_orders={trades['meta_db']['filled_orders']}"
            ),
        ]
        lines.extend(f"- {issue}" for issue in issues[:8])
        if len(issues) > 8:
            lines.append(f"- ... and {len(issues) - 8} more issue(s)")
        return "\n".join(lines)
