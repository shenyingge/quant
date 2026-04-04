from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, Optional


BROKER_CENT = Decimal("0.01")


@dataclass(frozen=True)
class FeeBreakdown:
    notional: float
    commission: float
    transfer_fee: float
    stamp_duty: float
    total_fee: float

    def to_dict(self) -> Dict[str, float]:
        payload = asdict(self)
        return {key: round(float(value), 6) for key, value in payload.items()}


@dataclass(frozen=True)
class TradingFeeSchedule:
    commission_rate: float = 0.0001
    min_commission: float = 5.0
    transfer_fee_rate: float = 0.00001
    stamp_duty_rate: float = 0.0005

    @classmethod
    def from_settings(cls, settings_obj: Any) -> "TradingFeeSchedule":
        return cls(
            commission_rate=float(
                getattr(settings_obj, "t0_commission_rate", cls.commission_rate) or 0.0
            ),
            min_commission=float(
                getattr(settings_obj, "t0_min_commission", cls.min_commission) or 0.0
            ),
            transfer_fee_rate=float(
                getattr(settings_obj, "t0_transfer_fee_rate", cls.transfer_fee_rate) or 0.0
            ),
            stamp_duty_rate=float(
                getattr(settings_obj, "t0_stamp_duty_rate", cls.stamp_duty_rate) or 0.0
            ),
        )

    @classmethod
    def from_t0_params(cls, params_obj: Any) -> "TradingFeeSchedule":
        return cls(
            commission_rate=float(
                getattr(params_obj, "t0_commission_rate", cls.commission_rate) or 0.0
            ),
            min_commission=float(
                getattr(params_obj, "t0_min_commission", cls.min_commission) or 0.0
            ),
            transfer_fee_rate=float(
                getattr(params_obj, "t0_transfer_fee_rate", cls.transfer_fee_rate) or 0.0
            ),
            stamp_duty_rate=float(
                getattr(params_obj, "t0_stamp_duty_rate", cls.stamp_duty_rate) or 0.0
            ),
        )

    def calculate(
        self,
        *,
        side: str,
        price: float,
        volume: int,
        trade_breakdown: Any = None,
    ) -> FeeBreakdown:
        normalized_side = normalize_side(side)
        normalized_breakdown = normalize_trade_breakdown_payload(trade_breakdown)
        if normalized_breakdown:
            notional = sum(float(item["amount"]) for item in normalized_breakdown)
        else:
            notional = max(float(price) * int(volume), 0.0)
            normalized_breakdown = [
                {
                    "trade_id": None,
                    "filled_time": None,
                    "volume": int(volume),
                    "price": float(price),
                    "amount": round(notional, 6),
                }
            ]

        if notional > 0:
            commission = max(
                _round_money(notional * self.commission_rate, rounding=ROUND_HALF_UP),
                round(float(self.min_commission), 2),
            )
        else:
            commission = 0.0

        transfer_fee = _sum_broker_leg_fees(
            normalized_breakdown,
            rate=self.transfer_fee_rate,
        )
        stamp_duty = (
            _sum_broker_leg_fees(normalized_breakdown, rate=self.stamp_duty_rate)
            if normalized_side == "SELL"
            else 0.0
        )
        total_fee = commission + transfer_fee + stamp_duty
        return FeeBreakdown(
            notional=round(notional, 6),
            commission=round(float(commission), 6),
            transfer_fee=round(float(transfer_fee), 6),
            stamp_duty=round(float(stamp_duty), 6),
            total_fee=round(float(total_fee), 6),
        )

    def estimate_roundtrip(
        self, *, buy_price: float, sell_price: float, volume: int
    ) -> Dict[str, float]:
        buy_fees = self.calculate(side="BUY", price=buy_price, volume=volume)
        sell_fees = self.calculate(side="SELL", price=sell_price, volume=volume)
        gross_pnl = sell_fees.notional - buy_fees.notional
        net_pnl = (sell_fees.notional - sell_fees.total_fee) - (
            buy_fees.notional + buy_fees.total_fee
        )
        return {
            "buy_notional": round(buy_fees.notional, 6),
            "sell_notional": round(sell_fees.notional, 6),
            "buy_total_fee": round(buy_fees.total_fee, 6),
            "sell_total_fee": round(sell_fees.total_fee, 6),
            "total_fee": round(buy_fees.total_fee + sell_fees.total_fee, 6),
            "gross_pnl": round(gross_pnl, 6),
            "net_pnl": round(net_pnl, 6),
        }


def normalize_side(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"sell", "positive_t_sell", "reverse_t_sell"} or text.endswith("_sell"):
        return "SELL"
    if (
        text in {"buy", "positive_t_buyback", "reverse_t_buy"}
        or text.endswith("_buy")
        or text.endswith("_buyback")
    ):
        return "BUY"
    raise ValueError(f"Unsupported trade side: {value!r}")


def build_trade_cost_fields(
    *,
    side: str,
    price: float,
    volume: int,
    fee_schedule: TradingFeeSchedule,
    trade_breakdown: Any = None,
) -> dict[str, float]:
    normalized_side = normalize_side(side)
    fee_breakdown = fee_schedule.calculate(
        side=normalized_side,
        price=price,
        volume=volume,
        trade_breakdown=trade_breakdown,
    ).to_dict()
    trade_amount = float(fee_breakdown["notional"])
    transaction_cost = float(fee_breakdown["total_fee"])
    settlement_amount = (
        trade_amount - transaction_cost
        if normalized_side == "SELL"
        else trade_amount + transaction_cost
    )
    net_cash_effect = settlement_amount if normalized_side == "SELL" else -settlement_amount
    return {
        "trade_amount": round(trade_amount, 6),
        "commission": float(fee_breakdown["commission"]),
        "transfer_fee": float(fee_breakdown["transfer_fee"]),
        "stamp_duty": float(fee_breakdown["stamp_duty"]),
        "total_fee": transaction_cost,
        "transaction_cost": transaction_cost,
        "settlement_amount": round(settlement_amount, 6),
        "net_cash_effect": round(net_cash_effect, 6),
    }


def apply_trade_cost_fields(record: Any, *, fee_schedule: TradingFeeSchedule) -> dict[str, float]:
    side = _read_attr(record, "direction", "action")
    price = float(_read_attr(record, "filled_price", "price") or 0.0)
    volume = int(_read_attr(record, "filled_volume", "volume") or 0)
    trade_breakdown = hydrate_trade_breakdown(record)
    details = build_trade_cost_fields(
        side=side,
        price=price,
        volume=volume,
        fee_schedule=fee_schedule,
        trade_breakdown=trade_breakdown,
    )
    for field_name, value in details.items():
        try:
            setattr(record, field_name, value)
        except Exception:
            continue
    return details


def normalize_filled_trades(
    records: Iterable[Any],
    fee_schedule: TradingFeeSchedule,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for sequence, record in enumerate(records):
        stock_code = _read_attr(record, "stock_code", "symbol") or ""
        direction = normalize_side(_read_attr(record, "direction", "action"))
        filled_volume = int(_read_attr(record, "filled_volume", "volume") or 0)
        filled_price = float(_read_attr(record, "filled_price", "price") or 0.0)
        filled_time = _read_attr(record, "filled_time", "timestamp", "signal_time")

        if filled_volume <= 0 or filled_price <= 0:
            continue

        persisted_costs = _read_persisted_trade_cost_fields(record)
        trade_breakdown = load_trade_breakdown(record)
        computed_costs = build_trade_cost_fields(
            side=direction,
            price=filled_price,
            volume=filled_volume,
            fee_schedule=fee_schedule,
            trade_breakdown=trade_breakdown,
        )
        trade_costs = {**computed_costs, **persisted_costs}

        normalized.append(
            {
                "sequence": sequence,
                "order_id": _read_attr(record, "order_id"),
                "stock_code": str(stock_code),
                "direction": direction,
                "filled_volume": filled_volume,
                "filled_price": filled_price,
                "filled_time": filled_time,
                "notional": float(trade_costs["trade_amount"]),
                "trade_amount": float(trade_costs["trade_amount"]),
                "commission": float(trade_costs["commission"]),
                "transfer_fee": float(trade_costs["transfer_fee"]),
                "stamp_duty": float(trade_costs["stamp_duty"]),
                "total_fee": float(trade_costs["total_fee"]),
                "transaction_cost": float(trade_costs["transaction_cost"]),
                "settlement_amount": float(trade_costs["settlement_amount"]),
                "net_cash_effect": float(trade_costs["net_cash_effect"]),
            }
        )

    normalized.sort(
        key=lambda item: (
            str(item.get("filled_time") or ""),
            int(item.get("sequence", 0)),
        )
    )
    return normalized


def _read_persisted_trade_cost_fields(record: Any) -> dict[str, float]:
    persisted: dict[str, float] = {}
    for field_name in (
        "trade_amount",
        "commission",
        "transfer_fee",
        "stamp_duty",
        "total_fee",
        "transaction_cost",
        "settlement_amount",
        "net_cash_effect",
    ):
        value = _read_attr(record, field_name)
        if value is None:
            continue
        try:
            persisted[field_name] = float(value)
        except (TypeError, ValueError):
            continue

    if "total_fee" in persisted and "transaction_cost" not in persisted:
        persisted["transaction_cost"] = persisted["total_fee"]
    if "transaction_cost" in persisted and "total_fee" not in persisted:
        persisted["total_fee"] = persisted["transaction_cost"]
    return persisted


def load_trade_breakdown(record: Any) -> list[dict[str, Any]]:
    for field_name in ("trade_breakdown", "trade_breakdown_json"):
        breakdown = normalize_trade_breakdown_payload(_read_attr(record, field_name))
        if breakdown:
            return breakdown

    error_message = str(_read_attr(record, "error_message") or "").strip()
    if not error_message:
        return []

    extracted = _extract_trade_breakdown_json(error_message)
    return normalize_trade_breakdown_payload(extracted)


def hydrate_trade_breakdown(record: Any) -> list[dict[str, Any]]:
    breakdown = load_trade_breakdown(record)
    if breakdown:
        set_trade_breakdown(record, breakdown)
    return breakdown


def set_trade_breakdown(record: Any, trade_breakdown: Any) -> list[dict[str, Any]]:
    normalized = normalize_trade_breakdown_payload(trade_breakdown)
    if not normalized:
        return []

    serialized = json.dumps(normalized, ensure_ascii=True, separators=(",", ":"))
    for field_name in ("trade_breakdown", "trade_breakdown_json"):
        if hasattr(record, field_name):
            try:
                setattr(record, field_name, serialized)
            except Exception:
                continue
            break
    return normalized


def append_trade_breakdown_leg(
    record: Any,
    *,
    volume: int,
    price: float,
    filled_time: Any = None,
    trade_id: Any = None,
    source: Optional[str] = None,
) -> list[dict[str, Any]]:
    breakdown = load_trade_breakdown(record)
    candidate_payload = [
        {
            "trade_id": trade_id,
            "filled_time": _normalize_breakdown_timestamp(filled_time),
            "volume": int(volume or 0),
            "price": float(price or 0.0),
            "source": source,
        }
    ]
    normalized_candidates = normalize_trade_breakdown_payload(candidate_payload)
    if not normalized_candidates:
        return breakdown

    candidate = normalized_candidates[0]
    candidate_key = _trade_breakdown_leg_key(candidate)
    if any(_trade_breakdown_leg_key(item) == candidate_key for item in breakdown):
        return breakdown

    breakdown.append(candidate)
    breakdown.sort(
        key=lambda item: (
            str(item.get("filled_time") or ""),
            str(item.get("trade_id") or ""),
            int(item.get("volume") or 0),
        )
    )
    set_trade_breakdown(record, breakdown)
    return breakdown


def summarize_trade_breakdown(trade_breakdown: Any) -> dict[str, Any]:
    normalized = normalize_trade_breakdown_payload(trade_breakdown)
    if not normalized:
        return {}

    total_volume = sum(int(item["volume"]) for item in normalized)
    total_amount = sum(float(item["amount"]) for item in normalized)
    latest_time = max(
        (str(item.get("filled_time") or "") for item in normalized),
        default="",
    )
    return {
        "filled_volume": int(total_volume),
        "filled_price": round(total_amount / total_volume, 6) if total_volume > 0 else 0.0,
        "filled_time": latest_time or None,
        "trade_amount": round(total_amount, 6),
        "legs": normalized,
    }


def normalize_trade_breakdown_payload(trade_breakdown: Any) -> list[dict[str, Any]]:
    payload = trade_breakdown
    if payload in (None, "", []):
        return []

    if isinstance(payload, str):
        payload = payload.strip()
        if not payload:
            return []
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return []

    if isinstance(payload, dict):
        payload = payload.get("legs") or payload.get("trades") or payload.get("items") or []

    if not isinstance(payload, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        volume = int(
            item.get("filled_volume")
            or item.get("traded_volume")
            or item.get("volume")
            or item.get("qty")
            or 0
        )
        price = float(
            item.get("filled_price")
            or item.get("traded_price")
            or item.get("price")
            or item.get("avg_price")
            or 0.0
        )
        if volume <= 0 or price <= 0:
            continue

        filled_time = _normalize_breakdown_timestamp(
            item.get("filled_time")
            or item.get("traded_time")
            or item.get("trade_time")
            or item.get("timestamp")
        )
        trade_id = item.get("trade_id") or item.get("traded_id") or item.get("fill_id")
        if trade_id in ("", None):
            trade_id = item.get("deal_id") or item.get("business_id")

        normalized.append(
            {
                "trade_id": str(trade_id).strip() if trade_id not in (None, "") else None,
                "filled_time": filled_time,
                "volume": volume,
                "price": round(price, 6),
                "amount": round(price * volume, 6),
                "source": str(item.get("source") or "").strip() or None,
            }
        )

    return normalized


def infer_trade_breakdown_from_logs(
    *,
    stock_code: str,
    filled_price: float,
    filled_volume: int,
    target_time: Any,
    window_seconds: int = 180,
) -> list[dict[str, Any]]:
    parsed_target_time = _coerce_breakdown_datetime(target_time)
    if not parsed_target_time or not stock_code or filled_price <= 0 or filled_volume <= 0:
        return []

    candidates: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, int, float]] = set()
    for log_path in _iter_trade_callback_log_paths():
        try:
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue

        for line in lines:
            parsed_line = _parse_trade_callback_log_line(line)
            if parsed_line is None:
                continue
            if parsed_line["stock_code"].upper() != stock_code.upper():
                continue
            if abs(parsed_line["price"] - float(filled_price)) > 1e-6:
                continue

            delta = abs((parsed_line["timestamp"] - parsed_target_time).total_seconds())
            if delta > window_seconds:
                continue

            leg_key = (
                parsed_line["timestamp"].isoformat(),
                int(parsed_line["volume"]),
                round(float(parsed_line["price"]), 6),
            )
            if leg_key in seen_keys:
                continue
            seen_keys.add(leg_key)
            candidates.append(
                {
                    "trade_id": f"log:{log_path.name}:{parsed_line['timestamp'].isoformat()}",
                    "filled_time": parsed_line["timestamp"].isoformat(),
                    "volume": int(parsed_line["volume"]),
                    "price": round(float(parsed_line["price"]), 6),
                    "source": "log_inference",
                }
            )

    if not candidates:
        return []

    total_logged_volume = sum(int(item["volume"]) for item in candidates)
    if total_logged_volume <= 0 or total_logged_volume > int(filled_volume):
        return []

    if total_logged_volume < int(filled_volume):
        candidates.append(
            {
                "trade_id": "log_inference_remainder",
                "filled_time": parsed_target_time.isoformat(),
                "volume": int(filled_volume) - total_logged_volume,
                "price": round(float(filled_price), 6),
                "source": "log_inference_remainder",
            }
        )

    return normalize_trade_breakdown_payload(candidates)


def analyze_filled_trades(
    records: Iterable[Any],
    fee_schedule: TradingFeeSchedule,
) -> Dict[str, Any]:
    trades = normalize_filled_trades(records, fee_schedule)
    roundtrips = build_roundtrips_from_trades(trades)
    per_stock: dict[str, dict[str, Any]] = {}

    for trade in trades:
        bucket = per_stock.setdefault(
            trade["stock_code"],
            {
                "stock_code": trade["stock_code"],
                "buy_amount": 0.0,
                "sell_amount": 0.0,
                "buy_volume": 0,
                "sell_volume": 0,
                "buy_fees": 0.0,
                "sell_fees": 0.0,
                "total_fees": 0.0,
                "gross_realized_pnl": 0.0,
                "net_realized_pnl": 0.0,
                "matched_volume": 0,
                "roundtrip_count": 0,
            },
        )

        amount = float(trade["notional"])
        fee = float(trade["total_fee"])
        volume = int(trade["filled_volume"])
        if trade["direction"] == "BUY":
            bucket["buy_amount"] += amount
            bucket["buy_volume"] += volume
            bucket["buy_fees"] += fee
        else:
            bucket["sell_amount"] += amount
            bucket["sell_volume"] += volume
            bucket["sell_fees"] += fee
        bucket["total_fees"] += fee

    for roundtrip in roundtrips:
        bucket = per_stock.setdefault(
            roundtrip["stock_code"],
            {
                "stock_code": roundtrip["stock_code"],
                "buy_amount": 0.0,
                "sell_amount": 0.0,
                "buy_volume": 0,
                "sell_volume": 0,
                "buy_fees": 0.0,
                "sell_fees": 0.0,
                "total_fees": 0.0,
                "gross_realized_pnl": 0.0,
                "net_realized_pnl": 0.0,
                "matched_volume": 0,
                "roundtrip_count": 0,
            },
        )
        bucket["gross_realized_pnl"] += float(roundtrip["gross_pnl"])
        bucket["net_realized_pnl"] += float(roundtrip["net_pnl"])
        bucket["matched_volume"] += int(roundtrip["volume"])
        bucket["roundtrip_count"] += 1

    for bucket in per_stock.values():
        bucket["buy_amount"] = round(bucket["buy_amount"], 6)
        bucket["sell_amount"] = round(bucket["sell_amount"], 6)
        bucket["buy_fees"] = round(bucket["buy_fees"], 6)
        bucket["sell_fees"] = round(bucket["sell_fees"], 6)
        bucket["total_fees"] = round(bucket["total_fees"], 6)
        bucket["gross_realized_pnl"] = round(bucket["gross_realized_pnl"], 6)
        bucket["net_realized_pnl"] = round(bucket["net_realized_pnl"], 6)
        bucket["net_volume"] = int(bucket["buy_volume"]) - int(bucket["sell_volume"])

    return {
        "trades": trades,
        "roundtrips": roundtrips,
        "per_stock": per_stock,
    }


def build_roundtrips_from_trades(trades: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    state_by_stock: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []

    for trade in trades:
        stock_code = str(trade.get("stock_code") or "")
        stock_state = state_by_stock.setdefault(
            stock_code,
            {
                "open_buys": deque(),
                "open_sells": deque(),
            },
        )
        current_leg = {
            "order_id": trade.get("order_id"),
            "stock_code": stock_code,
            "direction": trade["direction"],
            "price": float(trade["filled_price"]),
            "timestamp": trade.get("filled_time"),
            "remaining_volume": int(trade["filled_volume"]),
            "remaining_fee": float(trade["total_fee"]),
        }

        if current_leg["direction"] == "BUY":
            _close_open_legs(
                opening_legs=stock_state["open_sells"],
                closing_leg=current_leg,
                branch="positive_t",
                records=records,
            )
            if current_leg["remaining_volume"] > 0:
                stock_state["open_buys"].append(current_leg)
        else:
            _close_open_legs(
                opening_legs=stock_state["open_buys"],
                closing_leg=current_leg,
                branch="reverse_t",
                records=records,
            )
            if current_leg["remaining_volume"] > 0:
                stock_state["open_sells"].append(current_leg)

    return records


def _close_open_legs(
    *,
    opening_legs: deque,
    closing_leg: dict[str, Any],
    branch: str,
    records: list[dict[str, Any]],
) -> None:
    while closing_leg["remaining_volume"] > 0 and opening_legs:
        opening_leg = opening_legs[0]
        matched_volume = min(
            int(opening_leg["remaining_volume"]), int(closing_leg["remaining_volume"])
        )
        opening_fee = _consume_fee(opening_leg, matched_volume)
        closing_fee = _consume_fee(closing_leg, matched_volume)

        if branch == "positive_t":
            sell_leg = opening_leg
            buy_leg = closing_leg
        else:
            sell_leg = closing_leg
            buy_leg = opening_leg

        gross_pnl = (
            float(sell_leg["price"]) * matched_volume - float(buy_leg["price"]) * matched_volume
        )
        net_pnl = (
            float(sell_leg["price"]) * matched_volume - opening_fee
            if branch == "positive_t"
            else float(sell_leg["price"]) * matched_volume - closing_fee
        ) - (
            float(buy_leg["price"]) * matched_volume
            + (closing_fee if branch == "positive_t" else opening_fee)
        )
        total_fee = opening_fee + closing_fee

        records.append(
            {
                "stock_code": opening_leg["stock_code"],
                "branch": branch,
                "entry_direction": opening_leg["direction"],
                "exit_direction": closing_leg["direction"],
                "entry_order_id": opening_leg.get("order_id"),
                "exit_order_id": closing_leg.get("order_id"),
                "entry_timestamp": opening_leg.get("timestamp"),
                "exit_timestamp": closing_leg.get("timestamp"),
                "entry_price": round(float(opening_leg["price"]), 6),
                "exit_price": round(float(closing_leg["price"]), 6),
                "volume": matched_volume,
                "gross_pnl": round(gross_pnl, 6),
                "net_pnl": round(net_pnl, 6),
                "total_fee": round(total_fee, 6),
            }
        )

        if opening_leg["remaining_volume"] <= 0:
            opening_legs.popleft()


def _consume_fee(leg: dict[str, Any], matched_volume: int) -> float:
    remaining_volume = max(int(leg["remaining_volume"]), 0)
    if remaining_volume <= 0 or matched_volume <= 0:
        return 0.0

    remaining_fee = float(leg["remaining_fee"])
    consumed_fee = remaining_fee * matched_volume / remaining_volume
    leg["remaining_volume"] = remaining_volume - matched_volume
    leg["remaining_fee"] = remaining_fee - consumed_fee
    return consumed_fee


def _read_attr(record: Any, *names: str) -> Any:
    if isinstance(record, dict):
        for name in names:
            if name in record:
                return record[name]
        return None

    for name in names:
        if hasattr(record, name):
            return getattr(record, name)
    return None


def _round_money(value: float, *, rounding) -> float:
    decimal_value = Decimal(str(value or 0.0))
    return float(decimal_value.quantize(BROKER_CENT, rounding=rounding))


def _sum_broker_leg_fees(trade_breakdown: list[dict[str, Any]], *, rate: float) -> float:
    total = Decimal("0.00")
    decimal_rate = Decimal(str(rate or 0.0))
    for item in trade_breakdown:
        amount = Decimal(str(item.get("amount") or 0.0))
        total += (amount * decimal_rate).quantize(BROKER_CENT, rounding=ROUND_DOWN)
    return float(total)


def _extract_trade_breakdown_json(error_message: str) -> Optional[str]:
    marker = "trade_breakdown="
    marker_index = error_message.find(marker)
    if marker_index < 0:
        return None

    start_index = error_message.find("[", marker_index + len(marker))
    if start_index < 0:
        return None

    depth = 0
    for index in range(start_index, len(error_message)):
        char = error_message[index]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return error_message[start_index : index + 1]
    return None


def _trade_breakdown_leg_key(item: dict[str, Any]) -> tuple[str, str, int, float]:
    return (
        str(item.get("trade_id") or ""),
        str(item.get("filled_time") or ""),
        int(item.get("volume") or 0),
        round(float(item.get("price") or 0.0), 6),
    )


def _normalize_breakdown_timestamp(value: Any) -> Optional[str]:
    parsed = _coerce_breakdown_datetime(value)
    if parsed is not None:
        return parsed.isoformat()

    text_value = str(value or "").strip()
    return text_value or None


def _coerce_breakdown_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if value in (None, ""):
        return None

    text_value = str(value).strip()
    if not text_value:
        return None

    if text_value.isdigit() and len(text_value) == 14:
        try:
            return datetime.strptime(text_value, "%Y%m%d%H%M%S")
        except ValueError:
            return None

    if text_value.isdigit() and len(text_value) in {10, 13}:
        try:
            timestamp = int(text_value)
            if len(text_value) == 13:
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp)
        except (TypeError, ValueError, OSError, OverflowError):
            return None

    try:
        return datetime.fromisoformat(text_value)
    except ValueError:
        return None


def _iter_trade_callback_log_paths() -> Iterable[Path]:
    log_dir = Path("logs") / "current"
    for file_name in ("trading_engine.log", "app.log"):
        log_path = log_dir / file_name
        if log_path.exists():
            yield log_path


def _parse_trade_callback_log_line(line: str) -> Optional[dict[str, Any]]:
    patterns = (
        re.compile(
            r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+).+Trade callback: .*stock=(?P<stock_code>\d{6}\.(?:SH|SZ|BJ)).*volume=(?P<volume>\d+), price=(?P<price>\d+(?:\.\d+)?)",
        ),
        re.compile(
            r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+).+成交推送: .*股票(?P<stock_code>\d{6}\.(?:SH|SZ|BJ)).*数量(?P<volume>\d+), 价格(?P<price>\d+(?:\.\d+)?)",
        ),
    )
    for pattern in patterns:
        match = pattern.search(line)
        if not match:
            continue
        try:
            return {
                "timestamp": datetime.strptime(
                    match.group("timestamp"),
                    "%Y-%m-%d %H:%M:%S.%f",
                ),
                "stock_code": match.group("stock_code"),
                "volume": int(match.group("volume")),
                "price": float(match.group("price")),
            }
        except (TypeError, ValueError):
            return None
    return None
