from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.daily_pnl_calculator import calculate_daily_summary
from src.database import OrderRecord, TradingSignal
from src.strategy.position_syncer import PositionSyncer
from src.trader import QMTTrader


class AccountDataService:
    """Centralize the source-of-truth policy for account-related data."""

    def __init__(self):
        self.positions_snapshot_path = self._resolve_path(settings.account_positions_snapshot_path)

    def get_data_policy(self) -> Dict[str, Any]:
        return {
            "positions": {
                "source_of_truth": "qmt",
                "fallback": "position_cache",
                "storage": str(self.positions_snapshot_path),
                "usage": "runtime risk checks, available volume, latest holdings",
            },
            "orders": {
                "source_of_truth": "local_db",
                "storage": "order_records",
                "usage": "strategy order ledger, paging, audit, troubleshooting",
            },
            "signals": {
                "source_of_truth": "local_db",
                "storage": "trading_signals",
                "usage": "strategy signal ledger and replay context",
            },
            "trades": {
                "source_of_truth": "local_db",
                "storage": "order_records",
                "usage": "filled-order ledger and strategy-side execution history",
            },
            "strategy_pnl": {
                "source_of_truth": "local_db",
                "storage": "order_records",
                "usage": "strategy realized PnL, daily summary, attribution",
            },
            "account_pnl": {
                "source_of_truth": "qmt",
                "storage": None,
                "usage": "real account asset/PnL view from broker side",
            },
        }

    def get_positions_snapshot(self) -> Dict[str, Any]:
        trader = QMTTrader(
            session_id=settings.qmt_session_id_trading_service or settings.qmt_session_id
        )
        try:
            if trader.connect():
                positions = trader.get_positions() or []
                snapshot = {
                    "source": "qmt",
                    "is_live": True,
                    "fallback_used": False,
                    "as_of": date.today().isoformat(),
                    "positions": [
                        {
                            **position,
                            "source": "qmt",
                        }
                        for position in positions
                    ],
                }
                self._save_positions_snapshot(snapshot)
                return snapshot
        finally:
            try:
                trader.disconnect()
            except Exception:
                pass

        cached_snapshot = self._load_positions_snapshot()
        if cached_snapshot:
            cached_snapshot["fallback_used"] = True
            cached_snapshot["is_live"] = False
            return cached_snapshot

        syncer = PositionSyncer()
        if syncer.position_file.exists():
            cached = syncer.load_position()
            if cached:
                return {
                    "source": "position_cache",
                    "is_live": False,
                    "fallback_used": True,
                    "as_of": cached.get("last_sync_time"),
                    "positions": [
                        {
                            "stock_code": cached.get("stock_code"),
                            "volume": cached.get("total_position", 0),
                            "available_volume": cached.get("available_volume", 0),
                            "avg_price": cached.get("cost_price", 0),
                            "market_value": None,
                            "account_id": settings.qmt_account_id,
                            "source": "position_cache",
                            "last_sync_time": cached.get("last_sync_time"),
                        }
                    ],
                }

        raise RuntimeError("QMT is unavailable and no cached position snapshot exists")

    def get_orders_page(self, page: int, limit: int) -> Dict[str, Any]:
        offset = (page - 1) * limit
        with self._open_db_session() as session:
            total = session.query(OrderRecord).count()
            orders = (
                session.query(OrderRecord)
                .order_by(desc(OrderRecord.order_time))
                .offset(offset)
                .limit(limit)
                .all()
            )

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "source": "local_db",
            "data": [
                {
                    "id": o.id,
                    "signal_id": o.signal_id,
                    "order_id": o.order_id,
                    "stock_code": o.stock_code,
                    "direction": o.direction,
                    "volume": o.volume,
                    "price": o.price,
                    "order_status": o.order_status,
                    "filled_volume": o.filled_volume,
                    "filled_price": o.filled_price,
                    "order_time": o.order_time.isoformat() if o.order_time else None,
                    "filled_time": o.filled_time.isoformat() if o.filled_time else None,
                }
                for o in orders
            ],
        }

    def get_signals_page(self, page: int, limit: int) -> Dict[str, Any]:
        offset = (page - 1) * limit
        with self._open_db_session() as session:
            total = session.query(TradingSignal).count()
            signals = (
                session.query(TradingSignal)
                .order_by(desc(TradingSignal.signal_time))
                .offset(offset)
                .limit(limit)
                .all()
            )

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "source": "local_db",
            "data": [
                {
                    "id": s.id,
                    "signal_id": s.signal_id,
                    "stock_code": s.stock_code,
                    "direction": s.direction,
                    "volume": s.volume,
                    "price": s.price,
                    "processed": s.processed,
                    "error_message": s.error_message,
                    "signal_time": s.signal_time.isoformat() if s.signal_time else None,
                }
                for s in signals
            ],
        }

    def get_trades_page(self, page: int, limit: int) -> Dict[str, Any]:
        offset = (page - 1) * limit
        with self._open_db_session() as session:
            total = session.query(OrderRecord).filter(OrderRecord.filled_volume > 0).count()
            trades = (
                session.query(OrderRecord)
                .filter(OrderRecord.filled_volume > 0)
                .order_by(desc(OrderRecord.filled_time))
                .offset(offset)
                .limit(limit)
                .all()
            )

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "source": "local_db",
            "data": [
                {
                    "id": t.id,
                    "order_id": t.order_id,
                    "stock_code": t.stock_code,
                    "direction": t.direction,
                    "filled_volume": t.filled_volume,
                    "filled_price": t.filled_price,
                    "filled_time": t.filled_time.isoformat() if t.filled_time else None,
                }
                for t in trades
            ],
        }

    def get_strategy_pnl_breakdown(self) -> List[Dict[str, Any]]:
        with self._open_db_session() as session:
            trades = session.query(OrderRecord).filter(OrderRecord.filled_volume > 0).all()

        pnl_by_stock: Dict[str, Dict[str, Any]] = {}
        for trade in trades:
            bucket = pnl_by_stock.setdefault(
                trade.stock_code,
                {
                    "stock_code": trade.stock_code,
                    "buy_amount": 0.0,
                    "sell_amount": 0.0,
                    "pnl": 0.0,
                    "source": "local_db",
                },
            )
            amount = float((trade.filled_volume or 0) * (trade.filled_price or 0))
            if str(trade.direction).upper() == "BUY":
                bucket["buy_amount"] += amount
            else:
                bucket["sell_amount"] += amount
                bucket["pnl"] = bucket["sell_amount"] - bucket["buy_amount"]

        return list(pnl_by_stock.values())

    def get_strategy_pnl_summary(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        summary = calculate_daily_summary(target_date)
        summary["source"] = "local_db"
        summary["kind"] = "strategy_realized_pnl_estimate"
        return summary

    def get_account_overview(self) -> Dict[str, Any]:
        overview = {
            "policy": self.get_data_policy(),
            "strategy_pnl_summary": self.get_strategy_pnl_summary(),
        }
        try:
            overview["positions_snapshot"] = self.get_positions_snapshot()
        except Exception as exc:
            overview["positions_snapshot"] = None
            overview["positions_error"] = str(exc)
        return overview

    @contextmanager
    def _open_db_session(self) -> Iterator[Any]:
        engine = create_engine(settings.db_url)
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()

    def _save_positions_snapshot(self, snapshot: Dict[str, Any]) -> None:
        self.positions_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.positions_snapshot_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_positions_snapshot(self) -> Optional[Dict[str, Any]]:
        if not self.positions_snapshot_path.exists():
            return None
        try:
            return json.loads(self.positions_snapshot_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _resolve_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate
        return Path(__file__).resolve().parents[1] / candidate


def parse_pagination(query_params: Dict[str, List[str]]) -> Tuple[int, int, int]:
    page = int(query_params.get("page", ["1"])[0])
    limit = int(query_params.get("limit", ["100"])[0])

    if page < 1:
        raise ValueError("page must be >= 1")
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")

    return page, limit, (page - 1) * limit
