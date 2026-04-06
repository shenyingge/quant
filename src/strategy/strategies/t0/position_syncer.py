"""Position synchronization helpers for the T+0 runtime."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import redis
from sqlalchemy.orm import Session

from src.infrastructure.config import settings
from src.infrastructure.db import (
    AccountPosition,
    OrderRecord,
    SessionLocal,
    StrategyEventOutbox,
    StrategyPositionState,
    create_tables,
)
from src.infrastructure.logger_config import logger
from src.strategy.core.models import PortfolioState


class _FillProxy:
    """Minimal fill record used by apply_fill to reuse _apply_filled_order logic."""

    def __init__(self, direction: str, volume: int, price: float):
        self.direction = direction.upper()
        self.filled_volume = int(volume)
        self.filled_price = float(price)


class PositionSyncer:
    """Keeps the strategy position state aligned with QMT and local fills."""

    _tables_ready = False

    def __init__(self, output_dir: str = None, strategy_name: str = "t0"):
        self.output_dir = Path(output_dir or settings.t0_output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.position_file = self.output_dir / "position_state.json"
        self.strategy_name = strategy_name
        self._redis_client = None
        self._ensure_tables()

    def needs_qmt_sync(self, trade_date: Optional[date] = None) -> bool:
        """Whether the current trading day still needs a baseline QMT sync."""
        target_date = trade_date or date.today()
        position = self._load_current_position_state()
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

    def sync_from_qmt(self, trader, stock_code: str) -> bool:
        """Sync the baseline position snapshot from QMT."""
        try:
            position_data = trader.query_position(stock_code)
            if position_data is None:
                logger.warning("QMT position query returned empty, keeping the existing state")
                return False

            sync_time = self._utcnow()
            position_state = self._normalize_position_state(
                {
                    "stock_code": stock_code,
                    "total_position": position_data.get("volume", 0),
                    "available_volume": position_data.get("can_use_volume", 0),
                    "cost_price": position_data.get("open_price", 0),
                    "last_sync_time": self._format_timestamp(sync_time),
                    "last_sync_source": "qmt",
                    "last_qmt_sync_time": self._format_timestamp(sync_time),
                    "last_reconciled_fill_time": self._format_timestamp(sync_time),
                    "last_fill_time": self._format_timestamp(sync_time),
                }
            )

            persisted = self._persist_position_state(
                position_state,
                increment_version=True,
                event_type="position_synced",
            )
            self._save_position(persisted)
            self.publish_pending_events(limit=20)

            logger.info(
                "Position sync from QMT succeeded: stock={}, total_position={}, available_volume={}, version={}",
                stock_code,
                persisted["total_position"],
                persisted["available_volume"],
                persisted["position_version"],
            )
            return True
        except Exception as exc:
            logger.error(f"Position sync from QMT failed: {exc}")
            return False

    def load_position(self) -> Optional[dict]:
        """Load and reconcile the latest position state used by the strategy."""
        try:
            position = self._load_current_position_state()
            if position is None:
                logger.warning(
                    "No strategy position snapshot found, using the configured default state"
                )
                position = self._get_default_position()

            position = self._normalize_position_state(position)
            position = self._apply_execution_updates(position)

            logger.debug(
                "Loaded strategy position state: stock={} total={} available={} source={} version={}",
                position.get("stock_code"),
                position.get("total_position"),
                position.get("available_volume"),
                position.get("last_sync_source"),
                position.get("position_version"),
            )
            return position
        except Exception as exc:
            logger.error(f"Failed to load strategy position state: {exc}")
            return self._get_default_position()

    def to_portfolio_state(self, position: Optional[dict]) -> PortfolioState:
        """Convert a raw position dict into the typed strategy-facing state."""
        normalized = self._normalize_position_state(position or self._get_default_position())
        return PortfolioState(
            total_position=int(normalized.get("total_position", 0)),
            available_volume=int(normalized.get("available_volume", 0)),
            cost_price=float(normalized.get("cost_price", 0) or 0),
            base_position=int(normalized.get("base_position", settings.t0_base_position)),
            tactical_position=int(
                normalized.get("tactical_position", settings.t0_tactical_position)
            ),
            max_position=int(
                normalized.get(
                    "max_position",
                    settings.t0_base_position + settings.t0_tactical_position,
                )
            ),
            t0_sell_available=int(normalized.get("t0_sell_available", 0)),
            t0_buy_capacity=int(normalized.get("t0_buy_capacity", 0)),
            cash_available=float(normalized.get("cash_available", 0) or 0),
            position_version=int(normalized.get("position_version", 0) or 0),
        )

    def load_portfolio_state(self) -> PortfolioState:
        """Load the normalized portfolio state object used by the strategy core."""
        return self.to_portfolio_state(self.load_position())

    def get_position_version(self, stock_code: Optional[str] = None) -> int:
        position = self._load_current_position_state(stock_code=stock_code) or {}
        return int(position.get("position_version", 0) or 0)

    def apply_fill(self, direction: str, volume: int, price: float) -> bool:
        """Update the strategy position state immediately upon a trade fill."""
        session = SessionLocal()
        try:
            updated = self.apply_fill_transactional(
                session,
                direction,
                volume,
                price,
                stock_code=settings.t0_stock_code,
                filled_time=self._utcnow(),
                source="trade_callback",
            )
            session.commit()
            self._save_position(updated)
            self.publish_pending_events(limit=20)
            logger.info(
                "apply_fill: position updated direction={} volume={} price={} -> total={} available={} version={}",
                direction,
                volume,
                price,
                updated["total_position"],
                updated["available_volume"],
                updated["position_version"],
            )
            return True
        except Exception as exc:
            session.rollback()
            logger.error(f"apply_fill failed: {exc}")
            return False
        finally:
            session.close()

    def apply_fill_transactional(
        self,
        session: Session,
        direction: str,
        volume: int,
        price: float,
        *,
        stock_code: Optional[str] = None,
        filled_time: Optional[datetime] = None,
        source: str = "trade_callback",
    ) -> dict:
        """Apply a fill inside an existing DB transaction."""
        target_stock_code = str(stock_code or settings.t0_stock_code)
        current = (
            self._load_strategy_position_state(session, target_stock_code)
            or self._load_position_file()
            or self._load_account_position_snapshot(session, target_stock_code)
            or self._get_default_position(target_stock_code)
        )
        current = self._normalize_position_state(current)
        normalized_direction = str(direction or "").upper()
        if normalized_direction not in {"BUY", "SELL"}:
            logger.warning(
                "Skipping strategy position fill apply because direction is unknown: stock={} direction={}",
                target_stock_code,
                direction,
            )
            return current
        updated = self._build_filled_position_state(
            current,
            direction=normalized_direction,
            volume=volume,
            price=price,
            filled_time=filled_time,
            source=source,
        )
        return self._save_strategy_position(
            session,
            updated,
            increment_version=True,
            event_type="position_updated",
        )

    def publish_pending_events(self, limit: int = 20) -> int:
        """Best-effort publish of any pending strategy position outbox events."""
        client = self._get_redis_client()
        if client is None:
            return 0

        session = SessionLocal()
        published = 0
        try:
            events = (
                session.query(StrategyEventOutbox)
                .filter(StrategyEventOutbox.publish_status.in_(("pending", "failed")))
                .order_by(StrategyEventOutbox.created_at.asc(), StrategyEventOutbox.id.asc())
                .limit(max(int(limit), 1))
                .all()
            )

            for event in events:
                try:
                    client.publish(settings.redis_t0_position_channel, event.payload)
                    latest_key = f"{settings.redis_t0_position_latest_prefix}{event.stock_code}"
                    latest_ttl = int(settings.redis_t0_position_latest_ttl)
                    if latest_ttl > 0:
                        client.setex(latest_key, latest_ttl, event.payload)
                    else:
                        client.set(latest_key, event.payload)

                    event.publish_status = "published"
                    event.published_at = self._utcnow()
                    event.last_error = None
                    published += 1
                except Exception as exc:
                    event.publish_status = "failed"
                    event.last_error = str(exc)
                    logger.warning(f"Failed to publish strategy position event {event.id}: {exc}")

            session.commit()
            return published
        except Exception as exc:
            session.rollback()
            logger.warning(f"Unable to flush strategy position outbox: {exc}")
            return published
        finally:
            session.close()

    def _load_current_position_state(self, stock_code: Optional[str] = None) -> Optional[dict]:
        target_stock_code = str(stock_code or settings.t0_stock_code)
        session = SessionLocal()
        try:
            return (
                self._load_strategy_position_state(session, target_stock_code)
                or self._load_position_file()
                or self._load_account_position_snapshot(session, target_stock_code)
            )
        except Exception as exc:
            logger.warning(f"Failed to load strategy position snapshot from DB: {exc}")
            return self._load_position_file()
        finally:
            session.close()

    def _save_position(self, position: dict):
        """Persist the current strategy position state to disk for local inspection."""
        tmp_path = self.position_file.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(position, handle, ensure_ascii=False, indent=2)
        tmp_path.replace(self.position_file)

    def _persist_position_state(
        self,
        position: dict,
        *,
        increment_version: bool,
        event_type: Optional[str],
    ) -> dict:
        session = SessionLocal()
        try:
            persisted = self._save_strategy_position(
                session,
                position,
                increment_version=increment_version,
                event_type=event_type,
            )
            session.commit()
            return persisted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _save_strategy_position(
        self,
        session: Session,
        position: dict,
        *,
        increment_version: bool,
        event_type: Optional[str],
    ) -> dict:
        normalized = self._normalize_position_state(position)
        stock_code = str(normalized.get("stock_code") or settings.t0_stock_code)
        row = (
            session.query(StrategyPositionState)
            .filter(
                StrategyPositionState.strategy_name == self.strategy_name,
                StrategyPositionState.stock_code == stock_code,
            )
            .first()
        )
        if row is None:
            row = StrategyPositionState(strategy_name=self.strategy_name, stock_code=stock_code)
            session.add(row)

        current_version = int(row.position_version or 0)
        if not current_version:
            current_version = int(normalized.get("position_version", 0) or 0)
        next_version = current_version + 1 if increment_version else current_version

        row.total_position = int(normalized.get("total_position", 0) or 0)
        row.available_volume = int(normalized.get("available_volume", 0) or 0)
        row.cost_price = float(normalized.get("cost_price", 0) or 0)
        row.base_position = int(normalized.get("base_position", settings.t0_base_position))
        row.tactical_position = int(
            normalized.get("tactical_position", settings.t0_tactical_position)
        )
        row.max_position = int(
            normalized.get(
                "max_position",
                settings.t0_base_position + settings.t0_tactical_position,
            )
        )
        row.t0_sell_available = int(normalized.get("t0_sell_available", 0) or 0)
        row.t0_buy_capacity = int(normalized.get("t0_buy_capacity", 0) or 0)
        row.last_sync_time = self._parse_timestamp(normalized.get("last_sync_time"))
        row.last_sync_source = str(normalized.get("last_sync_source") or "default")
        row.last_qmt_sync_time = self._parse_timestamp(normalized.get("last_qmt_sync_time"))
        row.last_reconciled_fill_time = self._parse_timestamp(
            normalized.get("last_reconciled_fill_time")
        )
        row.last_fill_time = self._parse_timestamp(normalized.get("last_fill_time"))
        row.position_version = max(next_version, 0)
        session.flush()

        persisted = self._row_to_position_state(row)
        if event_type:
            self._enqueue_outbox_event(session, persisted, event_type)
        return persisted

    def _enqueue_outbox_event(self, session: Session, position: dict, event_type: str) -> None:
        session.add(
            StrategyEventOutbox(
                strategy_name=self.strategy_name,
                stock_code=str(position.get("stock_code") or settings.t0_stock_code),
                event_type=event_type,
                position_version=int(position.get("position_version", 0) or 0),
                payload=json.dumps(
                    self._build_position_event_payload(position, event_type),
                    ensure_ascii=False,
                ),
                publish_status="pending",
            )
        )

    def _build_position_event_payload(self, position: dict, event_type: str) -> dict:
        return {
            "event_type": event_type,
            "strategy_name": self.strategy_name,
            "stock_code": str(position.get("stock_code") or settings.t0_stock_code),
            "position_version": int(position.get("position_version", 0) or 0),
            "total_position": int(position.get("total_position", 0) or 0),
            "available_volume": int(position.get("available_volume", 0) or 0),
            "cost_price": float(position.get("cost_price", 0) or 0),
            "t0_sell_available": int(position.get("t0_sell_available", 0) or 0),
            "t0_buy_capacity": int(position.get("t0_buy_capacity", 0) or 0),
            "last_sync_source": str(position.get("last_sync_source") or "default"),
            "last_sync_time": position.get("last_sync_time"),
            "last_reconciled_fill_time": position.get("last_reconciled_fill_time"),
            "last_fill_time": position.get("last_fill_time"),
        }

    def _get_default_position(self, stock_code: Optional[str] = None) -> dict:
        """Build the fallback local state when no baseline has been synced yet."""
        return self._normalize_position_state(
            {
                "stock_code": stock_code or settings.t0_stock_code,
                "total_position": settings.t0_base_position,
                "available_volume": 0,
                "cost_price": 80.0,
                "last_sync_time": None,
                "last_sync_source": "default",
                "last_qmt_sync_time": None,
                "last_reconciled_fill_time": None,
                "last_fill_time": None,
                "position_version": 0,
            }
        )

    def _normalize_position_state(self, position: Optional[dict]) -> dict:
        """Normalize position fields into the strategy's base/tactical model."""
        normalized = dict(position or {})

        total_position = int(normalized.get("total_position") or 0)
        available_volume = int(normalized.get("available_volume") or 0)
        base_position = int(settings.t0_base_position)
        tactical_position = int(settings.t0_tactical_position)
        max_position = base_position + tactical_position

        normalized["stock_code"] = str(normalized.get("stock_code") or settings.t0_stock_code)
        normalized["base_position"] = base_position
        normalized["tactical_position"] = tactical_position
        normalized["max_position"] = max_position
        normalized["position_version"] = int(normalized.get("position_version", 0) or 0)
        normalized["t0_sell_available"] = self._round_down_lot(
            min(available_volume, max(total_position - base_position, 0))
        )
        normalized["t0_buy_capacity"] = self._round_down_lot(max(max_position - total_position, 0))
        return normalized

    def _load_position_file(self) -> Optional[dict]:
        if not self.position_file.exists():
            return None
        with open(self.position_file, "r", encoding="utf-8") as handle:
            return json.load(handle)

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

        updated = self._finalize_position_state(
            updated,
            source="local_db_reconciled",
            update_time=self._utcnow(),
            last_fill_time=latest_fill_time,
            reconciled_fill_time=latest_fill_time,
        )
        try:
            updated = self._persist_position_state(
                updated,
                increment_version=True,
                event_type="position_reconciled",
            )
        except Exception as exc:
            logger.warning(f"Failed to persist reconciled strategy position state: {exc}")
            updated = self._normalize_position_state(updated)

        self._save_position(updated)
        self.publish_pending_events(limit=20)
        return updated

    def _resolve_reconcile_marker(self, position: dict) -> Optional[datetime]:
        for field in ("last_reconciled_fill_time", "last_qmt_sync_time", "last_sync_time"):
            marker = self._parse_timestamp(position.get(field))
            if marker is not None:
                return marker
        return datetime.combine(date.today(), datetime.min.time())

    def _load_filled_orders_since(self, stock_code: str, since_time: Optional[datetime]):
        session = SessionLocal()
        try:
            query = (
                session.query(OrderRecord)
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
            session.close()

    def _load_strategy_position_state(self, session: Session, stock_code: str) -> Optional[dict]:
        row = (
            session.query(StrategyPositionState)
            .filter(
                StrategyPositionState.strategy_name == self.strategy_name,
                StrategyPositionState.stock_code == stock_code,
            )
            .first()
        )
        if row is None:
            return None
        return self._row_to_position_state(row)

    def _load_account_position_snapshot(self, session: Session, stock_code: str) -> Optional[dict]:
        row = (
            session.query(AccountPosition)
            .filter(
                AccountPosition.account_id == settings.qmt_account_id,
                AccountPosition.stock_code == stock_code,
            )
            .first()
        )
        if row is None:
            return None

        snapshot_time = row.snapshot_time or self._utcnow()
        return self._normalize_position_state(
            {
                "stock_code": row.stock_code,
                "total_position": row.total_volume,
                "available_volume": row.available_volume,
                "cost_price": row.avg_price,
                "last_sync_time": self._format_timestamp(snapshot_time),
                "last_sync_source": row.snapshot_source or "account_position",
                "last_qmt_sync_time": self._format_timestamp(snapshot_time),
                "last_reconciled_fill_time": self._format_timestamp(snapshot_time),
                "last_fill_time": self._format_timestamp(snapshot_time),
                "position_version": 0,
            }
        )

    def _row_to_position_state(self, row: StrategyPositionState) -> dict:
        return self._normalize_position_state(
            {
                "stock_code": row.stock_code,
                "total_position": row.total_position,
                "available_volume": row.available_volume,
                "cost_price": row.cost_price,
                "base_position": row.base_position,
                "tactical_position": row.tactical_position,
                "max_position": row.max_position,
                "t0_sell_available": row.t0_sell_available,
                "t0_buy_capacity": row.t0_buy_capacity,
                "last_sync_time": self._format_timestamp(row.last_sync_time),
                "last_sync_source": row.last_sync_source,
                "last_qmt_sync_time": self._format_timestamp(row.last_qmt_sync_time),
                "last_reconciled_fill_time": self._format_timestamp(row.last_reconciled_fill_time),
                "last_fill_time": self._format_timestamp(row.last_fill_time),
                "position_version": int(row.position_version or 0),
            }
        )

    def _build_filled_position_state(
        self,
        position: dict,
        *,
        direction: str,
        volume: int,
        price: float,
        filled_time: Optional[datetime],
        source: str,
    ) -> dict:
        updated = dict(position)
        self._apply_filled_order(updated, _FillProxy(direction, volume, price))
        fill_time = filled_time or self._utcnow()
        return self._finalize_position_state(
            updated,
            source=source,
            update_time=fill_time,
            last_fill_time=fill_time,
            reconciled_fill_time=fill_time,
        )

    def _finalize_position_state(
        self,
        position: dict,
        *,
        source: str,
        update_time: datetime,
        last_fill_time: Optional[datetime] = None,
        reconciled_fill_time: Optional[datetime] = None,
    ) -> dict:
        updated = dict(position)
        updated["last_sync_time"] = self._format_timestamp(update_time)
        updated["last_sync_source"] = source
        if source == "qmt":
            updated["last_qmt_sync_time"] = self._format_timestamp(update_time)
        if last_fill_time is not None:
            updated["last_fill_time"] = self._format_timestamp(last_fill_time)
        if reconciled_fill_time is not None:
            updated["last_reconciled_fill_time"] = self._format_timestamp(reconciled_fill_time)
        return self._normalize_position_state(updated)

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
        return datetime.now()

    def _round_down_lot(self, volume: int) -> int:
        trade_unit = max(int(settings.t0_trade_unit), 1)
        return max(int(volume) // trade_unit * trade_unit, 0)

    def _get_redis_client(self):
        if self._redis_client is not None:
            return self._redis_client

        try:
            client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password,
                db=0,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            client.ping()
            self._redis_client = client
        except Exception as exc:
            logger.debug(f"Strategy position Redis publisher unavailable: {exc}")
            self._redis_client = None
        return self._redis_client

    def _ensure_tables(self) -> None:
        if PositionSyncer._tables_ready:
            return
        try:
            create_tables()
            PositionSyncer._tables_ready = True
        except Exception as exc:
            logger.warning(f"Unable to ensure strategy position tables exist: {exc}")
