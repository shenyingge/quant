"""Position synchronization helpers for the T+0 runtime."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from src.config import settings
from src.database import OrderRecord, SessionLocal
from src.logger_config import logger
from src.strategy.core.models import PortfolioState


class PositionSyncer:
    """Keeps the strategy position state aligned with QMT and local fills."""

    def __init__(self, output_dir: str = None):
        self.output_dir = Path(output_dir or settings.t0_output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.position_file = self.output_dir / "position_state.json"

    def sync_from_qmt(self, trader, stock_code: str) -> bool:
        """Sync the baseline position snapshot from QMT."""
        try:
            position_data = trader.query_position(stock_code)
            if position_data is None:
                logger.warning("QMT position query returned empty, keeping the existing state")
                return False

            sync_time = self._utcnow()
            position_state = {
                "stock_code": stock_code,
                "total_position": position_data.get("volume", 0),
                "available_volume": position_data.get("can_use_volume", 0),
                "cost_price": position_data.get("open_price", 0),
                "last_sync_time": self._format_timestamp(sync_time),
                "last_sync_source": "qmt",
                "last_qmt_sync_time": self._format_timestamp(sync_time),
                "last_reconciled_fill_time": self._format_timestamp(sync_time),
            }
            position_state = self._normalize_position_state(position_state)
            self._save_position(position_state)

            logger.info(
                "Position sync from QMT succeeded: stock={}, total_position={}, available_volume={}",
                stock_code,
                position_state["total_position"],
                position_state["available_volume"],
            )
            return True
        except Exception as exc:
            logger.error(f"Position sync from QMT failed: {exc}")
            return False

    def needs_qmt_sync(self, trade_date: Optional[date] = None) -> bool:
        """Whether the current trading day still needs a baseline QMT sync."""
        target_date = trade_date or date.today()
        position = self._load_position_file()
        if position is None:
            return True

        last_qmt_sync = self._parse_timestamp(
            position.get("last_qmt_sync_time")
            or (
                position.get("last_sync_time")
                if str(position.get("last_sync_source", "")).lower() == "qmt"
                else None
            )
        )
        if last_qmt_sync is None:
            return True
        return last_qmt_sync.date() != target_date

    def load_position(self) -> Optional[dict]:
        """Load and reconcile the latest position state used by the strategy."""
        try:
            position = self._load_position_file()
            if position is None:
                logger.warning("Position state file does not exist, using the configured default state")
                position = self._get_default_position()

            position = self._normalize_position_state(position)
            position = self._apply_execution_updates(position)

            logger.debug(
                "Loaded strategy position state: stock={} total={} available={} source={}",
                position.get("stock_code"),
                position.get("total_position"),
                position.get("available_volume"),
                position.get("last_sync_source"),
            )
            return position
        except Exception as exc:
            logger.error(f"Failed to load strategy position state: {exc}")
            return self._get_default_position()

    def load_portfolio_state(self) -> PortfolioState:
        """Load the normalized portfolio state object used by the strategy core."""
        position = self.load_position() or self._get_default_position()
        return PortfolioState(
            total_position=int(position.get("total_position", 0)),
            available_volume=int(position.get("available_volume", 0)),
            cost_price=float(position.get("cost_price", 0) or 0),
            base_position=int(position.get("base_position", settings.t0_base_position)),
            tactical_position=int(position.get("tactical_position", settings.t0_tactical_position)),
            max_position=int(
                position.get(
                    "max_position",
                    settings.t0_base_position + settings.t0_tactical_position,
                )
            ),
            t0_sell_available=int(position.get("t0_sell_available", 0)),
            t0_buy_capacity=int(position.get("t0_buy_capacity", 0)),
            cash_available=float(position.get("cash_available", 0) or 0),
        )

    def _save_position(self, position: dict):
        """Persist the current strategy position state to disk."""
        with open(self.position_file, "w", encoding="utf-8") as f:
            json.dump(position, f, ensure_ascii=False, indent=2)

    def _get_default_position(self) -> dict:
        """Build the fallback local state when no baseline has been synced yet."""
        return self._normalize_position_state(
            {
                "stock_code": settings.t0_stock_code,
                "total_position": settings.t0_base_position,
                "available_volume": 0,
                "cost_price": 80.0,
                "last_sync_time": None,
                "last_sync_source": "default",
                "last_qmt_sync_time": None,
                "last_reconciled_fill_time": None,
            }
        )

    def _normalize_position_state(self, position: dict) -> dict:
        """Normalize position fields into the strategy's base/tactical model."""
        normalized = dict(position)

        total_position = int(normalized.get("total_position") or 0)
        available_volume = int(normalized.get("available_volume") or 0)
        base_position = int(normalized.get("base_position") or settings.t0_base_position)
        tactical_position = int(
            normalized.get("tactical_position") or settings.t0_tactical_position
        )
        max_position = base_position + tactical_position

        normalized["base_position"] = base_position
        normalized["tactical_position"] = tactical_position
        normalized["max_position"] = max_position
        normalized["t0_sell_available"] = self._round_down_lot(
            min(available_volume, max(total_position - base_position, 0))
        )
        normalized["t0_buy_capacity"] = self._round_down_lot(max(max_position - total_position, 0))
        return normalized

    def _load_position_file(self) -> Optional[dict]:
        if not self.position_file.exists():
            return None
        with open(self.position_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _apply_execution_updates(self, position: dict) -> dict:
        stock_code = str(position.get("stock_code") or settings.t0_stock_code)
        since_time = self._resolve_reconcile_marker(position)
        filled_orders = self._load_filled_orders_since(stock_code, since_time)
        if not filled_orders:
            return position

        updated = dict(position)
        latest_fill_time = since_time
        for order in filled_orders:
            self._apply_filled_order(updated, order)
            filled_time = getattr(order, "filled_time", None)
            if filled_time and (latest_fill_time is None or filled_time > latest_fill_time):
                latest_fill_time = filled_time

        updated["last_sync_time"] = self._format_timestamp(self._utcnow())
        updated["last_sync_source"] = "local_db_reconciled"
        updated["last_reconciled_fill_time"] = self._format_timestamp(latest_fill_time)
        updated = self._normalize_position_state(updated)
        self._save_position(updated)
        return updated

    def _resolve_reconcile_marker(self, position: dict) -> Optional[datetime]:
        for field in ("last_reconciled_fill_time", "last_qmt_sync_time", "last_sync_time"):
            marker = self._parse_timestamp(position.get(field))
            if marker is not None:
                return marker
        return datetime.combine(date.today(), datetime.min.time())

    def _load_filled_orders_since(self, stock_code: str, since_time: Optional[datetime]):
        db = SessionLocal()
        try:
            query = (
                db.query(OrderRecord)
                .filter(
                    OrderRecord.stock_code == stock_code,
                    OrderRecord.filled_volume > 0,
                    OrderRecord.filled_time.isnot(None),
                )
                .order_by(OrderRecord.filled_time.asc(), OrderRecord.id.asc())
            )
            if since_time is not None:
                query = query.filter(OrderRecord.filled_time > since_time)
            return query.all()
        finally:
            db.close()

    def _apply_filled_order(self, position: dict, order) -> None:
        filled_volume = int(getattr(order, "filled_volume", 0) or 0)
        if filled_volume <= 0:
            return

        direction = str(getattr(order, "direction", "") or "").upper()
        filled_price = float(getattr(order, "filled_price", 0) or getattr(order, "price", 0) or 0)

        total_position = int(position.get("total_position") or 0)
        available_volume = int(position.get("available_volume") or 0)
        cost_price = float(position.get("cost_price") or 0)

        if direction == "BUY":
            cost_basis = total_position * cost_price
            new_total = total_position + filled_volume
            position["total_position"] = new_total
            position["available_volume"] = available_volume + filled_volume
            if new_total > 0 and filled_price > 0:
                position["cost_price"] = (cost_basis + filled_volume * filled_price) / new_total
            return

        if direction == "SELL":
            new_total = max(total_position - filled_volume, 0)
            position["total_position"] = new_total
            position["available_volume"] = max(available_volume - filled_volume, 0)
            if new_total == 0:
                position["cost_price"] = 0

    def _format_timestamp(self, value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat(timespec="seconds")

    def _parse_timestamp(self, value) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value)
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            try:
                return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.warning("Unable to parse position timestamp: {}", text)
                return None

    def _utcnow(self) -> datetime:
        return datetime.utcnow()

    def _round_down_lot(self, volume: int) -> int:
        trade_unit = max(int(settings.t0_trade_unit), 1)
        return max(int(volume) // trade_unit * trade_unit, 0)
