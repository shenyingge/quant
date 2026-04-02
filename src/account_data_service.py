from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Any, Dict, Iterator, List, Optional, Tuple

from sqlalchemy import desc

from src.daily_pnl_calculator import calculate_daily_summary
from src.database import AccountPosition, OrderRecord, SessionLocal, TradingSignal


class AccountDataService:
    """Centralize the source-of-truth policy for account-related data."""

    def get_data_policy(self) -> Dict[str, Any]:
        return {
            "positions": {
                "source_of_truth": "meta_db",
                "fallback": None,
                "storage": "trading.account_positions",
                "usage": "broker-synced position snapshot updated on startup and filled trades",
            },
            "orders": {
                "source_of_truth": "meta_db",
                "storage": "trading.order_records",
                "usage": "strategy order ledger, paging, audit, troubleshooting",
            },
            "signals": {
                "source_of_truth": "meta_db",
                "storage": "trading.trading_signals",
                "usage": "strategy signal ledger and replay context",
            },
            "trades": {
                "source_of_truth": "meta_db",
                "storage": "trading.order_records",
                "usage": "filled-order ledger and strategy-side execution history",
            },
            "strategy_pnl": {
                "source_of_truth": "meta_db",
                "storage": "trading.order_records",
                "usage": "strategy realized PnL, daily summary, attribution",
            },
            "account_pnl": {
                "source_of_truth": "meta_db",
                "storage": "trading.order_records",
                "usage": "API-side estimate derived from the Meta DB execution ledger",
            },
        }

    def get_positions_snapshot(self) -> Dict[str, Any]:
        db_snapshot = self._get_positions_snapshot_from_db()
        if db_snapshot is not None:
            return db_snapshot

        return {
            "source": "meta_db",
            "available": False,
            "is_live": False,
            "fallback_used": False,
            "as_of": None,
            "positions": [],
            "error": "No position data available in Meta DB",
            "position_method": "broker_snapshot",
            "data_mode": "meta_db_snapshot",
        }

    def _get_positions_snapshot_from_db(self) -> Optional[Dict[str, Any]]:
        with self._open_db_session() as session:
            position_rows = (
                session.query(AccountPosition)
                .filter(AccountPosition.total_volume > 0)
                .order_by(
                    desc(AccountPosition.snapshot_time),
                    desc(AccountPosition.market_value),
                    AccountPosition.stock_code,
                )
                .all()
            )

        if not position_rows:
            return None

        latest_timestamp = max(
            (row.snapshot_time for row in position_rows if row.snapshot_time is not None),
            default=None,
        )
        positions = [
            {
                "stock_code": row.stock_code,
                "volume": int(row.total_volume or 0),
                "available_volume": int(row.available_volume or 0),
                "avg_price": float(row.avg_price or 0.0),
                "market_value": row.market_value,
                "last_price": row.last_price,
                "account_id": row.account_id,
                "source": "meta_db",
                "position_method": "broker_snapshot",
                "snapshot_source": row.snapshot_source,
                "snapshot_time": row.snapshot_time.isoformat() if row.snapshot_time else None,
            }
            for row in position_rows
        ]

        return {
            "source": "meta_db",
            "available": True,
            "is_live": False,
            "fallback_used": False,
            "as_of": latest_timestamp.isoformat() if latest_timestamp else None,
            "positions": positions,
            "position_method": "broker_snapshot",
            "data_mode": "meta_db_snapshot",
        }

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
            "source": "meta_db",
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
            "source": "meta_db",
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
            "source": "meta_db",
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
                    "buy_volume": 0,
                    "sell_volume": 0,
                    "net_volume": 0,
                    "pnl": 0.0,
                    "realized_pnl_estimate": 0.0,
                    "source": "meta_db",
                },
            )
            filled_volume = int(trade.filled_volume or 0)
            amount = float(filled_volume * (trade.filled_price or 0))
            if str(trade.direction).upper() == "BUY":
                bucket["buy_amount"] += amount
                bucket["buy_volume"] += filled_volume
            else:
                bucket["sell_amount"] += amount
                bucket["sell_volume"] += filled_volume
                bucket["pnl"] = bucket["sell_amount"] - bucket["buy_amount"]
                bucket["realized_pnl_estimate"] = bucket["pnl"]
            bucket["net_volume"] = bucket["buy_volume"] - bucket["sell_volume"]

        return sorted(pnl_by_stock.values(), key=lambda item: item["stock_code"])

    def get_unrealized_pnl_snapshot(self) -> Dict[str, Any]:
        positions_snapshot = self.get_positions_snapshot()
        positions = positions_snapshot.get("positions") or []

        breakdown: List[Dict[str, Any]] = []
        total_cost_basis = 0.0
        total_market_value = 0.0
        has_complete_totals = False

        for position in positions:
            volume = int(position.get("volume") or 0)
            avg_price = float(position.get("avg_price") or 0.0)
            last_price = self._to_optional_float(position.get("last_price"))
            market_value = self._to_optional_float(position.get("market_value"))
            if market_value is None and last_price is not None:
                market_value = round(last_price * volume, 4)

            cost_basis = round(avg_price * volume, 4)
            unrealized_pnl = (
                round(market_value - cost_basis, 4)
                if market_value is not None
                else None
            )
            unrealized_pnl_pct = (
                round(unrealized_pnl / cost_basis * 100, 4)
                if unrealized_pnl is not None and cost_basis not in (0, None)
                else None
            )

            if market_value is not None:
                total_cost_basis += cost_basis
                total_market_value += market_value
                has_complete_totals = True

            breakdown.append(
                {
                    "stock_code": position.get("stock_code"),
                    "volume": volume,
                    "available_volume": int(position.get("available_volume") or 0),
                    "avg_price": avg_price,
                    "last_price": last_price,
                    "cost_basis": cost_basis,
                    "market_value": market_value,
                    "unrealized_pnl": unrealized_pnl,
                    "unrealized_pnl_pct": unrealized_pnl_pct,
                    "snapshot_source": position.get("snapshot_source"),
                    "snapshot_time": position.get("snapshot_time"),
                    "source": "meta_db",
                }
            )

        total_unrealized_pnl = (
            round(total_market_value - total_cost_basis, 4) if has_complete_totals else None
        )
        total_unrealized_pnl_pct = (
            round(total_unrealized_pnl / total_cost_basis * 100, 4)
            if total_unrealized_pnl is not None and total_cost_basis not in (0, None)
            else None
        )

        return {
            "method": "position_snapshot_mark_to_market",
            "as_of": positions_snapshot.get("as_of"),
            "available": positions_snapshot.get("available", False),
            "summary": {
                "stocks": len(breakdown),
                "cost_basis": round(total_cost_basis, 4) if has_complete_totals else None,
                "market_value": round(total_market_value, 4) if has_complete_totals else None,
                "unrealized_pnl": total_unrealized_pnl,
                "unrealized_pnl_pct": total_unrealized_pnl_pct,
            },
            "breakdown": breakdown,
            "source": "meta_db",
        }

    def get_pnl_snapshot(self) -> Dict[str, Any]:
        realized_breakdown = self.get_strategy_pnl_breakdown()
        realized_buy_amount = round(
            sum(float(item.get("buy_amount") or 0.0) for item in realized_breakdown), 4
        )
        realized_sell_amount = round(
            sum(float(item.get("sell_amount") or 0.0) for item in realized_breakdown), 4
        )
        realized_pnl_estimate = round(
            sum(float(item.get("realized_pnl_estimate") or 0.0) for item in realized_breakdown), 4
        )

        return {
            "source": "meta_db",
            "kind": "realized_and_unrealized_pnl",
            "realized": {
                "method": "execution_ledger_estimate",
                "summary": {
                    "stocks": len(realized_breakdown),
                    "buy_amount": realized_buy_amount,
                    "sell_amount": realized_sell_amount,
                    "realized_pnl_estimate": realized_pnl_estimate,
                },
                "breakdown": realized_breakdown,
            },
            "unrealized": self.get_unrealized_pnl_snapshot(),
        }

    def get_strategy_pnl_summary(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        summary = calculate_daily_summary(target_date)
        summary["source"] = "meta_db"
        summary["kind"] = "strategy_realized_pnl_estimate"
        return summary

    def get_account_overview(self, *, include_positions: bool = False) -> Dict[str, Any]:
        overview = {
            "policy": self.get_data_policy(),
            "strategy_pnl_summary": self.get_strategy_pnl_summary(),
            "positions_included": include_positions,
        }

        if not include_positions:
            overview["positions_snapshot"] = None
            return overview

        try:
            overview["positions_snapshot"] = self.get_positions_snapshot()
        except Exception as exc:
            overview["positions_snapshot"] = None
            overview["positions_error"] = str(exc)
        return overview

    @contextmanager
    def _open_db_session(self) -> Iterator[Any]:
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def _to_optional_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

def parse_pagination(query_params: Dict[str, List[str]]) -> Tuple[int, int, int]:
    page = int(query_params.get("page", ["1"])[0])
    limit = int(query_params.get("limit", ["100"])[0])

    if page < 1:
        raise ValueError("page must be >= 1")
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")

    return page, limit, (page - 1) * limit
