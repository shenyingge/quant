import concurrent.futures
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from xtquant import xtconstant
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount

from src.infrastructure.config import settings
from src.trading.account.account_position_sync import sync_account_positions_from_qmt
from src.trading.analytics.attribution import AttributionService
from src.infrastructure.db import OrderRecord, SessionLocal, TradingSignal, get_db
from src.infrastructure.logger_config import configured_logger as logger
from src.trading.qmt_constants import (
    AccountStatus,
    OrderStatus,
    get_account_status_name,
    get_status_name,
    is_filled_status,
    is_finished_status,
)
from src.infrastructure.redis.client import redis_trade_client
from src.data_manager.stock_info import get_stock_display_name
from src.trading.costs.trading_costs import (
    TradingFeeSchedule,
    append_trade_breakdown_leg,
    apply_trade_cost_fields,
    load_trade_breakdown,
    summarize_trade_breakdown,
)


class QMTCallback(XtQuantTraderCallback):
    """QMT交易回调处理类"""

    def __init__(self, trader_instance):
        super().__init__()
        self.trader = trader_instance
        self.fee_schedule = TradingFeeSchedule.from_settings(settings)

    def on_disconnected(self):
        """
        连接断开回调
        :return:
        """
        logger.error("QMT连接已断开")
        if hasattr(self.trader, "notifier") and self.trader.notifier:
            self.trader.notifier.notify_error("QMT连接已断开", "连接状态")

        # 标记连接状态
        self.trader.is_connected = False

        # 触发重连（如果启用）
        if hasattr(self.trader, "trigger_reconnect"):
            self.trader.trigger_reconnect()

    def on_stock_order(self, order):
        """
        委托回报推送
        :param order: XtOrder对象
        :return:
        """
        try:
            order_id = getattr(order, "order_id", "")
            stock_code = getattr(order, "stock_code", "")
            order_status = getattr(order, "order_status", "")
            order_sysid = getattr(order, "order_sysid", "")

            # 创建回调数据的唯一标识
            callback_key = f"stock_order_{order_id}_{order_status}_{order_sysid}"

            # 检查是否是重复回调
            if callback_key in self.trader._last_callback_data:
                logger.debug(f"跳过重复的委托回报: {callback_key}")
                return

            # 记录这次回调，防止重复
            self.trader._last_callback_data[callback_key] = True

            # 清理过期的回调记录（保留最近100个）
            if len(self.trader._last_callback_data) > 100:
                # 删除一半较旧的记录
                keys_to_remove = list(self.trader._last_callback_data.keys())[:50]
                for key in keys_to_remove:
                    del self.trader._last_callback_data[key]

            stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
            # 日志记录使用状态码进行内部判断，但显示时使用描述
            logger.info(
                f"委托回报: 股票{stock_display}, 状态{order_status}({get_status_name(order_status) if isinstance(order_status, int) else order_status}), 委托号{order_id}, 系统号{order_sysid}"
            )

            # 更新统计信息
            with self.trader.stats_lock:
                # 检查是否为已报状态
                is_reported = (
                    isinstance(order_status, int) and order_status == OrderStatus.REPORTED
                ) or (isinstance(order_status, str) and order_status in ["已报", "已确认"])

                # 检查是否为取消状态
                is_cancelled = (
                    isinstance(order_status, int)
                    and order_status in [OrderStatus.CANCELED, OrderStatus.REJECTED]
                ) or (isinstance(order_status, str) and order_status in ["已撤销", "废单"])

                if is_reported:
                    self.trader.stats["confirmed_orders"] = (
                        self.trader.stats.get("confirmed_orders", 0) + 1
                    )
                elif is_filled_status(order_status):
                    self.trader.stats["filled_orders"] = (
                        self.trader.stats.get("filled_orders", 0) + 1
                    )
                elif is_cancelled:
                    self.trader.stats["cancelled_orders"] = (
                        self.trader.stats.get("cancelled_orders", 0) + 1
                    )

        except Exception as e:
            logger.error(f"委托回报处理异常: {e}")

    def on_stock_trade(self, trade):
        return self._on_stock_trade_impl(trade)
        """
        成交变动推送
        :param trade: XtTrade对象
        :return:
        """
        try:
            account_id = getattr(trade, "account_id", "")
            stock_code = getattr(trade, "stock_code", "")
            order_id = getattr(trade, "order_id", "")
            traded_volume = getattr(trade, "traded_volume", getattr(trade, "filled_qty", 0))
            traded_price = getattr(trade, "traded_price", getattr(trade, "filled_price", 0))
            trade_id = getattr(trade, "trade_id", f"trade_{int(__import__('time').time())}")
            trade_amount = traded_volume * traded_price

            # 创建回调数据的唯一标识
            callback_key = f"stock_trade_{order_id}_{trade_id}_{traded_volume}_{traded_price}"

            # 检查是否是重复回调
            if callback_key in self.trader._last_callback_data:
                logger.debug(f"跳过重复的成交推送: {callback_key}")
                return

            # 记录这次回调，防止重复
            self.trader._last_callback_data[callback_key] = True

            stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
            logger.info(
                f"成交推送: 账户{account_id}, 股票{stock_display}, 委托{order_id}, 数量{traded_volume}, 价格{traded_price}, 金额{trade_amount:.2f}"
            )

            # 更新数据库记录并发送成交通知
            try:
                from datetime import datetime

                from src.infrastructure.db import OrderRecord, SessionLocal

                db = SessionLocal()
                try:
                    # 查找对应的订单记录
                    order_record = (
                        db.query(OrderRecord).filter(OrderRecord.order_id == order_id).first()
                    )

                    if order_record:
                        # 更新成交信息
                        order_record.filled_volume = traded_volume
                        order_record.filled_price = traded_price
                        order_record.filled_time = datetime.utcnow()

                        # 检查是否已经发送过成交通知
                        if not getattr(order_record, "fill_notified", False):
                            # 发送成交通知
                            if hasattr(self.trader, "notifier") and self.trader.notifier:
                                stock_display = (
                                    get_stock_display_name(stock_code) if stock_code else stock_code
                                )
                                logger.info(
                                    f"QMT回调：订单 {order_id} ({stock_display}) 成交，发送通知"
                                )
                                self.trader.notifier.notify_order_filled(
                                    {
                                        "order_id": order_id,
                                        "stock_code": stock_code,
                                        "filled_qty": traded_volume,
                                        "avg_price": traded_price,
                                        "trade_amount": trade_amount,
                                    }
                                )
                                order_record.fill_notified = True
                        else:
                            stock_display = (
                                get_stock_display_name(stock_code) if stock_code else stock_code
                            )
                        logger.debug(f"订单 {order_id} ({stock_display}) 已经发送过成交通知，跳过")

                        db.commit()
                    else:
                        stock_display = (
                            get_stock_display_name(stock_code) if stock_code else stock_code
                        )
                        logger.warning(f"未找到订单记录: {order_id} ({stock_display})")
                        # 如果找不到订单记录，仍然发送通知（可能是手动下单等情况）
                        if hasattr(self.trader, "notifier") and self.trader.notifier:
                            self.trader.notifier.notify_order_filled(
                                {
                                    "order_id": order_id,
                                    "stock_code": stock_code,
                                    "filled_qty": traded_volume,
                                    "avg_price": traded_price,
                                    "trade_amount": trade_amount,
                                }
                            )
                finally:
                    db.close()

            except Exception as e:
                logger.error(f"更新订单记录时出错: {e}")
                # 即使更新失败，也发送通知
                if hasattr(self.trader, "notifier") and self.trader.notifier:
                    self.trader.notifier.notify_order_filled(
                        {
                            "order_id": order_id,
                            "stock_code": stock_code,
                            "filled_qty": traded_volume,
                            "avg_price": traded_price,
                            "trade_amount": trade_amount,
                        }
                    )

            try:
                sync_account_positions_from_qmt(self.trader, source="trade_callback")
            except Exception as sync_error:
                logger.error(f"成交后同步 Meta DB 仓位失败: {sync_error}")

            # 更新统计信息
            with self.trader.stats_lock:
                self.trader.stats["total_trade_amount"] = (
                    self.trader.stats.get("total_trade_amount", 0) + trade_amount
                )
                self.trader.stats["total_trade_volume"] = (
                    self.trader.stats.get("total_trade_volume", 0) + traded_volume
                )

        except Exception as e:
            logger.error(f"成交推送处理异常: {e}")

    def _on_stock_trade_impl(self, trade):
        try:
            account_id = getattr(trade, "account_id", "")
            stock_code = getattr(trade, "stock_code", "")
            order_id = getattr(trade, "order_id", "")
            traded_volume = getattr(trade, "traded_volume", getattr(trade, "filled_qty", 0))
            traded_price = getattr(trade, "traded_price", getattr(trade, "filled_price", 0))
            trade_id = self._extract_trade_identifier(trade) or f"trade_{int(time.time())}"
            filled_time = self._extract_trade_timestamp(trade)
            direction = self._infer_trade_direction(trade, stock_code=stock_code)
            trade_amount = traded_volume * traded_price

            callback_key = self._build_trade_callback_key(
                trade=trade,
                raw_order_id=order_id,
                stock_code=stock_code,
                traded_volume=traded_volume,
                traded_price=traded_price,
            )
            if callback_key in self.trader._last_callback_data:
                logger.debug(f"Skipping duplicate trade callback: {callback_key}")
                return

            self.trader._last_callback_data[callback_key] = True

            stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
            logger.info(
                f"Trade callback: account={account_id}, stock={stock_display}, order={order_id}, volume={traded_volume}, price={traded_price}, amount={trade_amount:.2f}"
            )

            notification_payload = {
                "order_id": order_id,
                "stock_code": stock_code,
                "filled_qty": traded_volume,
                "avg_price": traded_price,
                "trade_amount": trade_amount,
            }

            try:
                sync_account_positions_from_qmt(self.trader, source="trade_callback")
            except Exception as sync_error:
                logger.error(f"Trade callback position sync failed: {sync_error}")

            position_syncer = None
            if stock_code == settings.t0_stock_code:
                try:
                    from src.strategy.strategies.t0.position_syncer import PositionSyncer

                    position_syncer = PositionSyncer()
                except Exception as position_sync_error:
                    logger.error(
                        f"Failed to initialize T0 strategy position syncer during trade callback: {position_sync_error}"
                    )

            try:
                db = SessionLocal()
                try:
                    order_record = self._load_order_record_for_trade(
                        db, order_id, stock_code, traded_volume
                    )

                    if order_record is not None:
                        self._apply_trade_fill_to_order_record(
                            order_record,
                            traded_volume=traded_volume,
                            traded_price=traded_price,
                            filled_time=filled_time,
                            trade_identifier=trade_id,
                        )
                    else:
                        order_record = self._create_order_record_from_trade(
                            trade=trade,
                            stock_code=stock_code,
                            raw_order_id=order_id,
                            trade_id=trade_id,
                            traded_volume=traded_volume,
                            traded_price=traded_price,
                        )
                        db.add(order_record)
                        logger.warning(
                            f"Created standalone order record from trade callback: order_id={order_record.order_id}, stock_code={stock_code}, trade_id={trade_id}"
                        )

                    if position_syncer is not None:
                        position_syncer.apply_fill_transactional(
                            db,
                            direction,
                            traded_volume,
                            traded_price,
                            stock_code=stock_code,
                            filled_time=filled_time,
                            source="trade_callback",
                        )

                    should_notify = not getattr(order_record, "fill_notified", False)
                    notification_payload["order_id"] = order_record.order_id

                    # Attribution: record this fill in trade_executions
                    try:
                        attribution_service = AttributionService(session=db)
                        attribution_service.record_execution(
                            broker_trade_id=str(getattr(trade, "trade_id", "") or "") or None,
                            broker_order_id=str(getattr(trade, "order_id", "") or "") or None,
                            submit_request_id=None,
                            stock_code=str(getattr(trade, "stock_code", "") or ""),
                            direction=str(getattr(order_record, "direction", "") or ""),
                            filled_volume=int(traded_volume),
                            filled_price=float(traded_price),
                            filled_amount=float(traded_volume) * float(traded_price),
                            filled_time=filled_time,
                            commission=getattr(order_record, "commission", None),
                            transfer_fee=getattr(order_record, "transfer_fee", None),
                            stamp_duty=getattr(order_record, "stamp_duty", None),
                            total_fee=getattr(order_record, "total_fee", None),
                            execution_source="qmt_trade_callback",
                        )
                    except Exception as exc:
                        logger.warning("AttributionService.record_execution failed: {}", exc)

                    db.commit()

                    if position_syncer is not None:
                        position_syncer.publish_pending_events(limit=20)

                    if should_notify and hasattr(self.trader, "notifier") and self.trader.notifier:
                        self.trader.notifier.notify_order_filled(notification_payload)
                        order_record.fill_notified = True
                        db.commit()
                    elif not should_notify:
                        logger.debug(
                            f"Skipping duplicate fill notification for order {order_record.order_id}"
                        )
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()

            except Exception as exc:
                logger.error(f"Failed to persist trade callback into Meta DB: {exc}")
                if hasattr(self.trader, "notifier") and self.trader.notifier:
                    self.trader.notifier.notify_order_filled(notification_payload)

            with self.trader.stats_lock:
                self.trader.stats["total_trade_amount"] = (
                    self.trader.stats.get("total_trade_amount", 0) + trade_amount
                )
                self.trader.stats["total_trade_volume"] = (
                    self.trader.stats.get("total_trade_volume", 0) + traded_volume
                )
        except Exception as exc:
            logger.error(f"Trade callback processing failed: {exc}")

    def _load_order_record_for_trade(
        self, db: Session, raw_order_id: Any, stock_code: str, traded_volume: int
    ) -> Optional[OrderRecord]:
        normalized_order_id = self._normalize_order_id(raw_order_id)
        if normalized_order_id:
            order_record = (
                db.query(OrderRecord).filter(OrderRecord.order_id == normalized_order_id).first()
            )
            if order_record is not None:
                return order_record

        if not stock_code:
            return None

        candidate_query = db.query(OrderRecord).filter(
            OrderRecord.stock_code == stock_code,
            OrderRecord.filled_time.is_(None),
            OrderRecord.created_at >= datetime.utcnow() - timedelta(minutes=30),
        )
        if traded_volume:
            candidate_query = candidate_query.filter(OrderRecord.volume >= int(traded_volume))

        candidates = candidate_query.order_by(OrderRecord.created_at.desc()).limit(2).all()
        if len(candidates) == 1:
            logger.info(
                f"Matched trade callback to recent order record {candidates[0].order_id} for {stock_code}"
            )
            return candidates[0]
        if len(candidates) > 1:
            logger.warning(
                f"Trade callback fallback matched multiple recent order records for {stock_code}; raw_order_id={raw_order_id}"
            )
        return None

    def _apply_trade_fill_to_order_record(
        self,
        order_record: OrderRecord,
        *,
        traded_volume: int,
        traded_price: float,
        filled_time: datetime,
        trade_identifier: Optional[str] = None,
    ) -> None:
        if order_record.price in (None, 0):
            order_record.price = float(traded_price or 0.0)
        if order_record.volume in (None, 0):
            order_record.volume = int(traded_volume or 0)
        self._append_trade_leg_to_order_record(
            order_record,
            traded_volume=traded_volume,
            traded_price=traded_price,
            filled_time=filled_time,
            trade_identifier=trade_identifier,
            source="trade_callback",
        )
        if int(order_record.filled_volume or 0) >= int(order_record.volume or 0):
            order_record.order_status = "FILLED"
        elif not order_record.order_status or order_record.order_status == "PENDING":
            order_record.order_status = "部分成交"
        self._apply_trade_costs_to_order_record(order_record)

    def _create_order_record_from_trade(
        self,
        *,
        trade: Any,
        stock_code: str,
        raw_order_id: Any,
        trade_id: Any,
        traded_volume: int,
        traded_price: float,
    ) -> OrderRecord:
        filled_time = self._extract_trade_timestamp(trade)
        signal_id = self._infer_signal_id_from_active_orders(raw_order_id, stock_code)
        direction = self._infer_trade_direction(trade, stock_code=stock_code)
        order_id = self._build_trade_order_id(raw_order_id, trade_id)
        order_record = OrderRecord(
            signal_id=signal_id,
            order_id=order_id,
            stock_code=stock_code,
            direction=direction,
            volume=int(traded_volume or 0),
            price=float(traded_price or 0.0),
            order_status="FILLED",
            order_time=filled_time,
            filled_price=0.0,
            filled_volume=0,
            filled_time=None,
            fill_notified=False,
            error_message="Created from QMT trade callback without a matching order record",
        )
        self._append_trade_leg_to_order_record(
            order_record,
            traded_volume=traded_volume,
            traded_price=traded_price,
            filled_time=filled_time,
            trade_identifier=trade_id,
            source="trade_callback",
        )
        self._apply_trade_costs_to_order_record(order_record)
        return order_record

    def _append_trade_leg_to_order_record(
        self,
        order_record: OrderRecord,
        *,
        traded_volume: int,
        traded_price: float,
        filled_time: datetime,
        trade_identifier: Optional[str],
        source: str,
    ) -> None:
        existing_breakdown = load_trade_breakdown(order_record)
        if (
            not existing_breakdown
            and int(getattr(order_record, "filled_volume", 0) or 0) > 0
            and float(getattr(order_record, "filled_price", 0.0) or 0.0) > 0
        ):
            append_trade_breakdown_leg(
                order_record,
                volume=int(order_record.filled_volume or 0),
                price=float(order_record.filled_price or 0.0),
                filled_time=getattr(order_record, "filled_time", None),
                trade_id="seed_existing_fill",
                source="seed_existing_fill",
            )

        breakdown = append_trade_breakdown_leg(
            order_record,
            volume=traded_volume,
            price=traded_price,
            filled_time=filled_time,
            trade_id=trade_identifier,
            source=source,
        )
        summary = summarize_trade_breakdown(breakdown)
        if not summary:
            order_record.filled_volume = int(traded_volume or 0)
            order_record.filled_price = float(traded_price or 0.0)
            order_record.filled_time = filled_time
            return

        order_record.filled_volume = int(summary.get("filled_volume") or 0)
        order_record.filled_price = float(summary.get("filled_price") or 0.0)
        parsed_time = self._parse_trade_timestamp(summary.get("filled_time"))
        order_record.filled_time = parsed_time or filled_time

    def _apply_trade_costs_to_order_record(self, order_record: OrderRecord) -> None:
        try:
            apply_trade_cost_fields(order_record, fee_schedule=self.fee_schedule)
        except Exception as exc:
            logger.warning(
                "Unable to apply persisted trade cost fields for order_id={} stock_code={}: {}",
                getattr(order_record, "order_id", None),
                getattr(order_record, "stock_code", None),
                exc,
            )

    def _build_trade_order_id(self, raw_order_id: Any, trade_id: Any) -> str:
        normalized_order_id = self._normalize_order_id(raw_order_id)
        if normalized_order_id:
            return normalized_order_id[:50]

        trade_part = str(trade_id or f"trade_{int(time.time())}").strip()
        if not trade_part:
            trade_part = f"trade_{int(time.time())}"
        return f"MANUAL_{trade_part}"[:50]

    def _extract_trade_identifier(self, trade: Any) -> Optional[str]:
        for attr in ("trade_id", "traded_id", "trade_no", "deal_id", "business_id", "fill_id"):
            value = str(getattr(trade, attr, "") or "").strip()
            if value and value != "0":
                return value
        return None

    def _build_trade_callback_key(
        self,
        *,
        trade: Any,
        raw_order_id: Any,
        stock_code: str,
        traded_volume: int,
        traded_price: float,
    ) -> str:
        trade_identifier = self._extract_trade_identifier(trade)
        normalized_order_id = self._normalize_order_id(raw_order_id)
        order_sysid = str(getattr(trade, "order_sysid", "") or "").strip()

        if trade_identifier:
            owner = normalized_order_id or order_sysid or stock_code or "unknown"
            return f"stock_trade_{owner}_{trade_identifier}"

        traded_time = str(
            getattr(trade, "traded_time", "")
            or getattr(trade, "trade_time", "")
            or getattr(trade, "filled_time", "")
            or ""
        ).strip()
        order_part = normalized_order_id or str(raw_order_id or "").strip() or "0"
        return "|".join(
            [
                "stock_trade_fallback",
                stock_code or "",
                order_part,
                order_sysid,
                traded_time,
                str(int(traded_volume or 0)),
                f"{float(traded_price or 0.0):.8f}",
            ]
        )

    def _normalize_order_id(self, raw_order_id: Any) -> Optional[str]:
        order_id = str(raw_order_id or "").strip()
        if not order_id or order_id == "0":
            return None
        return order_id

    def _extract_trade_timestamp(self, trade: Any) -> datetime:
        for attr in ("traded_time", "trade_time", "filled_time", "order_time"):
            parsed_time = self._parse_trade_timestamp(getattr(trade, attr, None))
            if parsed_time is not None:
                return parsed_time
        return datetime.utcnow()

    def _parse_trade_timestamp(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if value in (None, ""):
            return None

        if isinstance(value, (int, float)):
            return self._parse_trade_timestamp(str(int(value)))

        text_value = str(value).strip()
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

    def _infer_signal_id_from_active_orders(
        self, raw_order_id: Any, stock_code: str
    ) -> Optional[str]:
        active_orders = getattr(self.trader, "active_orders", None)
        order_lock = getattr(self.trader, "order_lock", None)
        if not active_orders or order_lock is None:
            return None

        normalized_order_id = self._normalize_order_id(raw_order_id)
        with order_lock:
            if normalized_order_id and normalized_order_id in active_orders:
                signal_data = active_orders[normalized_order_id].get("signal_data", {})
                return signal_data.get("signal_id")

            stock_matches = []
            for order_info in active_orders.values():
                signal_data = order_info.get("signal_data", {})
                if signal_data.get("stock_code") == stock_code:
                    stock_matches.append(signal_data)

        if len(stock_matches) == 1:
            return stock_matches[0].get("signal_id")
        return None

    def _infer_trade_direction(self, trade: Any, *, stock_code: str) -> str:
        for attr in (
            "order_type",
            "direction",
            "side",
            "operation",
            "trade_direction",
            "buy_sell",
            "bs_flag",
            "entrust_bs",
        ):
            mapped_direction = self._map_trade_direction(getattr(trade, attr, None))
            if mapped_direction:
                return mapped_direction

        active_orders = getattr(self.trader, "active_orders", None)
        order_lock = getattr(self.trader, "order_lock", None)
        if active_orders and order_lock is not None:
            with order_lock:
                stock_matches = []
                for order_info in active_orders.values():
                    signal_data = order_info.get("signal_data", {})
                    if signal_data.get("stock_code") == stock_code:
                        stock_matches.append(signal_data.get("direction"))
            if len(stock_matches) == 1:
                mapped_direction = self._map_trade_direction(stock_matches[0])
                if mapped_direction:
                    return mapped_direction

        return "UNKNOWN"

    def _map_trade_direction(self, value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        if isinstance(value, int):
            if value == xtconstant.STOCK_BUY:
                return "BUY"
            if value == xtconstant.STOCK_SELL:
                return "SELL"

        text_value = str(value).strip().upper()
        if text_value in {"BUY", "B", str(xtconstant.STOCK_BUY)}:
            return "BUY"
        if text_value in {"SELL", "S", str(xtconstant.STOCK_SELL)}:
            return "SELL"
        return None

    def on_order_error(self, order_error):
        """
        委托失败推送
        :param order_error:XtOrderError 对象
        :return:
        """
        try:
            order_id = getattr(order_error, "order_id", "")
            error_id = getattr(order_error, "error_id", 0)
            error_msg = getattr(order_error, "error_msg", "")
            stock_code = getattr(order_error, "stock_code", "")

            stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
            logger.error(
                f"委托失败: 委托{order_id}, 股票{stock_display}, 错误码{error_id}, 错误信息: {error_msg}"
            )

            # 发送错误通知
            if hasattr(self.trader, "notifier") and self.trader.notifier:
                self.trader.notifier.notify_error(
                    f"委托失败: {error_msg}", f"委托{order_id}, 股票{stock_display}"
                )

            # 更新统计信息
            with self.trader.stats_lock:
                self.trader.stats["failed_orders"] = self.trader.stats.get("failed_orders", 0) + 1

            # 从活跃委托列表中移除失败的委托
            with self.trader.order_lock:
                if order_id in self.trader.active_orders:
                    order_info = self.trader.active_orders.pop(order_id)
                    logger.info(f"已移除失败委托 {order_id} 从活跃列表")

                    # 保存失败记录
                    signal_data = order_info.get("signal_data", {})
                    self.trader._save_order_to_redis(order_id, signal_data, "failed", error_msg)

                    # 调用外部回调，通知失败
                    callback = order_info.get("callback")
                    if callback:
                        callback(None, f"委托失败: {error_msg}")

                # 也检查是否是序列号格式的失败
                else:
                    # 遍历所有active_orders，查找匹配的seq_id
                    for temp_id, order_info in list(self.trader.active_orders.items()):
                        if (
                            temp_id.startswith("seq_") and order_info.get("seq_id") == int(order_id)
                            if str(order_id).isdigit()
                            else False
                        ):
                            # 找到对应的序列号记录
                            self.trader.active_orders.pop(temp_id)
                            logger.info(f"已移除失败委托序列 {temp_id} 从活跃列表")

                            signal_data = order_info.get("signal_data", {})
                            self.trader._save_order_to_redis(
                                temp_id, signal_data, "failed", error_msg
                            )

                            # 调用外部回调，通知失败
                            callback = order_info.get("callback")
                            if callback:
                                callback(None, f"委托失败: {error_msg}")
                            break

        except Exception as e:
            logger.error(f"委托错误处理异常: {e}")

    def on_cancel_error(self, cancel_error):
        """
        撤单失败推送
        :param cancel_error: XtCancelError 对象
        :return:
        """
        try:
            order_id = getattr(cancel_error, "order_id", "")
            error_id = getattr(cancel_error, "error_id", 0)
            error_msg = getattr(cancel_error, "error_msg", "")
            stock_code = getattr(cancel_error, "stock_code", "")

            stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
            logger.error(
                f"撤单失败: 委托{order_id}, 股票{stock_display}, 错误码{error_id}, 错误信息: {error_msg}"
            )

            # 发送错误通知
            if hasattr(self.trader, "notifier") and self.trader.notifier:
                self.trader.notifier.notify_error(
                    f"撤单失败: {error_msg}", f"委托{order_id}, 股票{stock_display}"
                )

            # 更新统计信息
            with self.trader.stats_lock:
                self.trader.stats["cancel_failed"] = self.trader.stats.get("cancel_failed", 0) + 1

        except Exception as e:
            logger.error(f"撤单错误处理异常: {e}")

    def on_account_status(self, status):
        """
        账户状态变化回调
        :param status: XtAccountStatus 对象
        :return:
        """
        try:
            account_id = getattr(status, "account_id", "")
            account_type = getattr(status, "account_type", "")
            account_status = getattr(status, "status", "")

            # 获取账户状态描述，支持数字和字符串状态
            if isinstance(account_status, int):
                status_desc = get_account_status_name(account_status)
                logger.info(
                    f"账户状态变化: 账户{account_id}, 类型{account_type}, 状态{account_status}({status_desc})"
                )
            else:
                # 兼容旧版本字符串状态
                logger.info(
                    f"账户状态变化: 账户{account_id}, 类型{account_type}, 状态{account_status}"
                )
                status_desc = account_status

            # 检查是否为异常状态
            is_error_status = False
            if isinstance(account_status, int):
                is_error_status = account_status in AccountStatus.get_error_statuses()
            else:
                # 兼容旧版本字符串判断
                is_error_status = account_status not in [
                    "正常",
                    "连接",
                    "CONNECTED",
                    "1",
                    "连接中",
                    "登录中",
                    "初始化中",
                    "数据刷新校正中",
                ]

            # 如果账户状态异常，发送通知
            if is_error_status:
                if hasattr(self.trader, "notifier") and self.trader.notifier:
                    # 使用专门的账户状态通知方法
                    if hasattr(self.trader.notifier, "notify_account_status"):
                        self.trader.notifier.notify_account_status(
                            account_id, account_status, "状态异常"
                        )
                    else:
                        # 兼容旧版本通知器
                        self.trader.notifier.notify_error(
                            f"账户状态异常: {status_desc}", f"账户{account_id}"
                        )

            # 更新连接状态
            if isinstance(account_status, int):
                self.trader.is_connected = account_status in AccountStatus.get_normal_statuses()
            else:
                # 兼容旧版本字符串状态
                self.trader.is_connected = account_status in [
                    "正常",
                    "连接",
                    "CONNECTED",
                    "1",
                    "连接中",
                    "登录中",
                ]

        except Exception as e:
            logger.error(f"账户状态处理异常: {e}")

    def on_order_stock_async_response(self, response):
        """异步下单回调"""
        try:
            logger.info(f"异步下单回调: {response.__dict__}")
            # 处理异步下单结果
            order_id = getattr(response, "order_id", None)
            seq_id = getattr(response, "seq", None)
            error_id = getattr(response, "error_id", 0)
            error_msg = getattr(response, "error_msg", "")

            if error_id == 0 and order_id:
                logger.info(f"异步下单成功，委托编号: {order_id}，序列号: {seq_id}")

                # 更新active_orders，用真实order_id替换序列号
                if seq_id:
                    temp_id = f"seq_{seq_id}"
                    with self.trader.order_lock:
                        if temp_id in self.trader.active_orders:
                            order_info = self.trader.active_orders.pop(temp_id)
                            # 使用真实order_id作为key
                            self.trader.active_orders[str(order_id)] = order_info
                            logger.info(f"委托序列 {seq_id} 已更新为真实委托编号 {order_id}")

                            # 保存成功的委托记录到Redis
                            signal_data = order_info.get("signal_data", {})
                            self.trader._save_order_to_redis(
                                str(order_id), signal_data, "submitted"
                            )

                            # 调用外部回调，通知TradingEngine真实的order_id
                            callback = order_info.get("callback")
                            if callback:
                                callback(str(order_id), None)
            else:
                logger.error(f"异步下单失败: {error_msg} (错误代码: {error_id})")

                # 如果失败，移除临时序列号记录并保存失败记录
                if seq_id:
                    temp_id = f"seq_{seq_id}"
                    with self.trader.order_lock:
                        if temp_id in self.trader.active_orders:
                            order_info = self.trader.active_orders.pop(temp_id)
                            logger.info(f"移除失败的委托序列 {seq_id}")

                            # 保存失败的委托记录到Redis
                            signal_data = order_info.get("signal_data", {})
                            self.trader._save_order_to_redis(None, signal_data, "failed", error_msg)

                            # 调用外部回调，通知失败
                            callback = order_info.get("callback")
                            if callback:
                                callback(None, f"异步下单失败: {error_msg}")

        except Exception as e:
            logger.error(f"异步下单回调异常: {e}")

    def on_cancel_order_stock_async_response(self, response):
        """异步撤单回调"""
        try:
            logger.info(f"异步撤单回调: {response.__dict__}")
            error_id = getattr(response, "error_id", 0)
            error_msg = getattr(response, "error_msg", "")

            if error_id == 0:
                logger.info("异步撤单成功")
            else:
                logger.error(f"异步撤单失败: {error_msg} (错误代码: {error_id})")

        except Exception as e:
            logger.error(f"异步撤单回调异常: {e}")

    def on_order_status(self, order_status):
        """委托状态变化回调"""
        try:
            order_id = str(order_status.order_id)
            status = order_status.order_status
            # 日志记录状态码和描述，方便调试
            logger.info(
                f"委托状态变化: {order_id} -> {status}({get_status_name(status) if isinstance(status, int) else status})"
            )

            # 更新委托状态记录
            with self.trader.order_lock:
                if order_id in self.trader.active_orders:
                    order_info = self.trader.active_orders[order_id]
                    order_info["last_status"] = status
                    order_info["last_update"] = datetime.now()

                    # 如果委托完成，移除并保存最终记录
                    if is_finished_status(status):
                        order_info = self.trader.active_orders.pop(order_id)
                        logger.info(
                            f"委托 {order_id} 最终状态: {status}({get_status_name(status) if isinstance(status, int) else status})，移出活跃列表"
                        )

                        # 保存最终状态记录
                        signal_data = order_info.get("signal_data", {})
                        # 判断最终状态（支持数字和字符串状态）
                        if (isinstance(status, int) and status == OrderStatus.SUCCEEDED) or (
                            isinstance(status, str) and status == "已成交"
                        ):
                            final_status = "filled"
                        elif (isinstance(status, int) and status == OrderStatus.CANCELED) or (
                            isinstance(status, str) and status == "已撤销"
                        ):
                            final_status = "cancelled"
                        else:
                            final_status = "rejected"

                        # 构建状态更新记录
                        status_record = {
                            "order_id": order_id,
                            "final_status": final_status,
                            "order_status": status,
                            "update_time": datetime.now().isoformat(),
                        }

                        # 如果是成交，添加成交信息
                        if (isinstance(status, int) and status == OrderStatus.SUCCEEDED) or (
                            isinstance(status, str) and status == "已成交"
                        ):
                            filled_qty = getattr(
                                order_status, "filled_qty", getattr(order_status, "order_volume", 0)
                            )
                            avg_price = getattr(
                                order_status, "avg_price", getattr(order_status, "price", 0)
                            )

                            status_record.update(
                                {
                                    "filled_volume": filled_qty,
                                    "avg_price": avg_price,
                                    "stock_code": getattr(
                                        order_status,
                                        "stock_code",
                                        signal_data.get("stock_code", ""),
                                    ),
                                }
                            )

                            # 保存成交记录到Redis
                            self.trader._save_trade_execution_to_redis(order_id, status_record)

                        # 更新委托记录状态到Redis
                        self.trader._save_order_to_redis(order_id, signal_data, final_status)

        except Exception as e:
            logger.error(f"委托状态回调异常: {e}")


class QMTTrader:
    def __init__(self, notifier=None, session_id=None):
        self.session_id = settings.qmt_session_id if session_id is None else int(session_id)
        self.is_connected = False
        self.xt_trader = None
        self.account = None
        self.callback = None  # QMT回调对象
        self.notifier = notifier  # 通知器，用于回调中发送通知

        # 添加回调去重机制
        self._last_callback_data = {}  # 缓存最近的回调数据，用于去重

        # 订单跟踪（简化版，主要用于回调处理）
        self.active_orders = (
            {}
        )  # {order_id: {'signal_data': dict, 'timestamp': datetime, 'trades': list}}
        self.order_lock = threading.Lock()

        # 主线程运行xtquant
        self._shutdown = False

        # 异步交易线程池（只处理业务逻辑，xtquant在主线程运行）
        self.trade_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="TradeLogic")

        # 统计信息
        self.stats = {
            "total_orders": 0,  # 总委托数
            "successful_orders": 0,  # 成功委托数
            "failed_orders": 0,  # 失败委托数
            "timeout_orders": 0,  # 超时委托数
            "pending_count": 0,  # 排队中委托数
        }
        self.stats_lock = threading.Lock()

        # 重连相关
        self.reconnect_lock = threading.Lock()
        self.reconnect_thread = None
        self.reconnect_attempts = 0
        self.last_connect_time = None

        # 订单超时监控
        self.timeout_monitor_thread = None
        self.timeout_monitor_running = False

    def connect(self) -> bool:
        """连接QMT"""
        try:
            # 创建回调对象（必须在创建trader之前，确保强引用）
            self.callback = QMTCallback(self)

            # 创建交易对象
            logger.info(f"正在连接QMT，Session ID: {self.session_id}, Path: {settings.qmt_path}")
            # XtQuantTrader需要两个参数：path和session_id（可能作为log_dir）
            self.xt_trader = XtQuantTrader(settings.qmt_path, self.session_id)

            # 尝试注册回调（某些版本可能不支持或返回None）
            try:
                self.xt_trader.register_callback(self.callback)
                logger.info("QMT回调注册成功")
            except AttributeError:
                logger.warning("当前QMT版本不支持register_callback，跳过回调注册")
                logger.info("可能是模拟环境或旧版本QMT，委托可能不会有回调响应")
            except Exception as e:
                logger.warning(f"注册QMT回调异常: {e}，继续连接")

            # 添加回调测试信息
            logger.info(f"回调对象引用: {self.callback is not None}")

            # 启动交易引擎
            try:
                self.xt_trader.start()
                logger.info("QMT交易引擎启动成功")
            except Exception as e:
                logger.warning(f"启动QMT服务异常: {e}，尝试继续连接")

            # 创建账户对象
            self.account = StockAccount(
                account_id=settings.qmt_account_id,
                # account_type=settings.qmt_account_type
            )

            # 连接QMT
            result = self.xt_trader.connect()
            if result == 0:
                logger.info("QMT连接成功")
                self.is_connected = True
                self.reconnect_attempts = 0  # 重置重连计数
                self.last_connect_time = time.time()
                logger.info(f"QMT账户: {settings.qmt_account_id}")

                # 某些版本的QMT可能需要订阅账户
                try:
                    if hasattr(self.xt_trader, "subscribe"):
                        subscribe_result = self.xt_trader.subscribe(self.account)
                        if subscribe_result == 0:
                            logger.info("QMT账户订阅成功")
                        else:
                            logger.warning(f"QMT账户订阅失败，错误代码: {subscribe_result}")
                    else:
                        logger.info("当前QMT版本无需显式订阅账户")
                except Exception as e:
                    logger.warning(f"账户订阅异常: {e}")
                    # 不影响主流程，继续执行

                # 连接Redis（用于交易记录存储）
                if settings.redis_trade_records_enabled:
                    redis_connected = redis_trade_client.connect()
                    if redis_connected:
                        logger.info("Redis交易记录存储已启用")
                    else:
                        logger.warning("Redis连接失败，交易记录将仅存储到数据库")

                # xtquant将在主线程中运行，等待run_forever调用
                logger.info("xtquant将在主线程中运行，等待run_forever调用")

                # 启动订单超时监控
                if settings.auto_cancel_enabled:
                    self._start_timeout_monitor()

                return True
            else:
                logger.error(f"QMT连接失败，错误代码: {result}")
                return False
        except Exception as e:
            logger.error(f"连接QMT时发生错误: {e}")
            return False

    def disconnect(self):
        """断开QMT连接"""
        try:
            self._shutdown = True

            # 停止订单超时监控
            self._stop_timeout_monitor()

            # 停止异步交易线程池
            if hasattr(self, "trade_executor") and self.trade_executor:
                self.trade_executor.shutdown(wait=True)

            # 停止xtquant
            self._shutdown = True

            # 断开Redis连接
            if settings.redis_trade_records_enabled:
                redis_trade_client.disconnect()

            if self.xt_trader:
                self.xt_trader.stop()
                self.is_connected = False
                logger.info("QMT连接已断开")
        except Exception as e:
            logger.error(f"断开QMT连接时发生错误: {e}")

    def trigger_reconnect(self):
        """触发QMT重连"""
        if not settings.auto_reconnect_enabled:
            logger.info("QMT自动重连已禁用")
            return

        with self.reconnect_lock:
            # 如果重连线程已在运行，不重复启动
            if self.reconnect_thread and self.reconnect_thread.is_alive():
                logger.debug("QMT重连线程已在运行")
                return

            self.reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
            self.reconnect_thread.start()
            logger.info("QMT重连线程已启动")

    def _reconnect_loop(self):
        """QMT重连循环"""
        while self.reconnect_attempts < settings.reconnect_max_attempts and not self._shutdown:
            try:
                self.reconnect_attempts += 1

                # 计算重连延迟（指数退避）
                delay = min(
                    settings.reconnect_initial_delay
                    * (settings.reconnect_backoff_factor ** (self.reconnect_attempts - 1)),
                    settings.reconnect_max_delay,
                )

                logger.info(
                    f"QMT第 {self.reconnect_attempts}/{settings.reconnect_max_attempts} 次重连，"
                    f"将在 {delay:.1f} 秒后尝试"
                )

                # 等待重连延迟
                for _ in range(int(delay)):
                    if self._shutdown:
                        logger.info("QMT服务停止，取消重连")
                        return
                    time.sleep(1)

                if self._shutdown:
                    logger.info("QMT服务停止，取消重连")
                    return

                # 尝试重连
                if self.connect():
                    logger.info("QMT重连成功")
                    # 通知已由 connection_manager 统一发送，避免重复
                    return
                else:
                    logger.warning(f"QMT第 {self.reconnect_attempts} 次重连失败")

            except Exception as e:
                logger.error(f"QMT重连异常: {e}")

        # 重连失败
        logger.error(f"QMT重连失败，已达到最大尝试次数 {settings.reconnect_max_attempts}")

        # 发送重连失败通知
        if self.notifier and hasattr(self.notifier, "notify_reconnect_failed"):
            self.notifier.notify_reconnect_failed("QMT", self.reconnect_attempts)

    def is_healthy(self) -> bool:
        """检查QMT连接健康状态"""
        if not self.is_connected or not self.xt_trader:
            return False

        try:
            # 尝试获取账户信息来测试连接
            if hasattr(self.xt_trader, "query_stock_asset") and self.account:
                result = self.xt_trader.query_stock_asset(self.account)
                return result is not None
            else:
                # 如果没有查询方法，只检查连接状态
                return self.is_connected
        except Exception as e:
            logger.debug(f"QMT健康检查异常: {e}")
            return False

    def query_position(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """查询单只股票持仓，返回策略同步所需的标准字段。"""
        if not self.is_connected or not self.xt_trader or not self.account:
            logger.error("QMT未连接或未初始化，无法查询持仓")
            return None

        try:
            positions = self.xt_trader.query_stock_positions(self.account)
            if positions is None:
                logger.warning("QMT持仓查询返回空结果")
                return None

            target_code = stock_code.split(".")[0].upper()
            for position in positions:
                position_code = getattr(position, "stock_code", "")
                if position_code.split(".")[0].upper() != target_code:
                    continue

                return {
                    "stock_code": position_code,
                    "volume": getattr(position, "volume", 0),
                    "can_use_volume": getattr(position, "can_use_volume", 0),
                    "open_price": getattr(
                        position,
                        "open_price",
                        getattr(position, "avg_price", 0),
                    ),
                    "market_value": getattr(position, "market_value", 0),
                    "last_price": getattr(position, "last_price", 0),
                }

            logger.info(f"未查询到股票持仓: {stock_code}")
            return {
                "stock_code": stock_code,
                "volume": 0,
                "can_use_volume": 0,
                "open_price": 0,
                "market_value": 0,
                "last_price": 0,
            }
        except Exception as e:
            logger.error(f"查询持仓失败: {e}")
            return None

    def place_order(self, signal_data: Dict[str, Any]) -> Optional[str]:
        """下单（同步版本，使用异步线程但等待结果）"""
        if not self.is_connected or not self.xt_trader or not self.account:
            logger.error("QMT未连接或未初始化，无法委托下单")
            return None

        try:
            stock_code = signal_data.get("stock_code", signal_data.get("symbol", "")).strip()
            direction = signal_data.get("direction", signal_data.get("action", "")).upper()
            volume = int(signal_data.get("volume", signal_data.get("quantity", 0)))
            price = signal_data.get("price")

            if not stock_code or not direction or volume <= 0:
                logger.error(f"无效的委托参数: {signal_data}")
                return None

            stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
            logger.info(
                f"准备委托下单: 证券={stock_display}, 方向={direction}, 数量={volume}, 价格={price}"
            )

            # 使用异步线程池提交任务，但等待结果
            future = self.trade_executor.submit(self._execute_order, signal_data)

            try:
                order_id = future.result(timeout=settings.order_submit_timeout)
                return order_id
            except concurrent.futures.TimeoutError:
                logger.error(f"委托操作超时（{settings.order_submit_timeout}秒）")
                future.cancel()
                return None

        except Exception as e:
            logger.error(f"委托下单时发生错误: {e}")
            return None

    def place_order_async(self, signal_data: Dict[str, Any], callback=None) -> None:
        """异步委托下单"""
        if not self.is_connected or not self.xt_trader or not self.account:
            logger.error("QMT未连接或未初始化，无法委托下单")
            if callback:
                callback(None, "QMT未连接")
            return

        # 更新统计
        with self.stats_lock:
            self.stats["total_orders"] += 1
            self.stats["pending_count"] += 1

        stock_code = signal_data.get("stock_code", signal_data.get("symbol", "Unknown"))
        direction = signal_data.get("direction", signal_data.get("action", "Unknown"))
        stock_display = (
            get_stock_display_name(stock_code) if stock_code != "Unknown" else stock_code
        )
        logger.info(
            f"提交异步委托任务: {stock_display} {direction} [队列中: {self.stats['pending_count']}]"
        )

        def _async_order_callback(future):
            try:
                order_id = future.result()
                with self.stats_lock:
                    self.stats["pending_count"] -= 1
                    if order_id:
                        self.stats["successful_orders"] += 1
                    else:
                        self.stats["failed_orders"] += 1

                if callback:
                    callback(order_id, None if order_id else "下单失败")
            except concurrent.futures.TimeoutError:
                with self.stats_lock:
                    self.stats["pending_count"] -= 1
                    self.stats["timeout_orders"] += 1
                error_msg = f"异步委托超时"
                logger.error(error_msg)
                if callback:
                    callback(None, error_msg)
            except Exception as e:
                with self.stats_lock:
                    self.stats["pending_count"] -= 1
                    self.stats["failed_orders"] += 1
                error_msg = f"异步委托异常: {e}"
                logger.error(error_msg)
                if callback:
                    callback(None, error_msg)

        future = self.trade_executor.submit(self._execute_order, signal_data, callback)
        future.add_done_callback(_async_order_callback)

    def _execute_order(self, signal_data: Dict[str, Any], callback=None) -> Optional[str]:
        """实际执行委托操作（使用passorder），支持重试机制"""
        retry_count = 0
        last_error = None

        while retry_count <= settings.order_retry_attempts:
            try:
                if retry_count > 0:
                    logger.info(
                        f"开始第 {retry_count} 次重试下单，股票: {signal_data.get('stock_code')}"
                    )
                    time.sleep(settings.order_retry_delay)

                result = self._execute_single_order(signal_data, callback)
                if result:
                    if retry_count > 0:
                        logger.info(f"重试下单成功，第 {retry_count} 次尝试")
                    return result

            except Exception as e:
                last_error = e
                logger.error(f"第 {retry_count + 1} 次下单尝试失败: {e}")

            retry_count += 1

        # 所有重试都失败了
        error_msg = f"下单失败，已重试 {settings.order_retry_attempts} 次，最后错误: {last_error}"
        logger.error(error_msg)

        # 保存失败记录
        self._save_order_to_redis(None, signal_data, "failed", error_msg)

        return None

    def _execute_single_order(self, signal_data: Dict[str, Any], callback=None) -> Optional[str]:
        """执行单次下单操作"""
        try:
            stock_code = signal_data.get("stock_code", "").strip()
            direction = signal_data.get("direction", "").upper()
            volume = int(signal_data.get("volume", 0))
            price = signal_data.get("price")

            # 确定市场类型并格式化股票代码
            if stock_code.startswith("6"):
                market = "SH"  # 上海
                full_stock_code = f"{stock_code}.SH"
            elif stock_code.startswith("8") or (
                stock_code.startswith("4") and len(stock_code) == 6
            ):
                market = "BJ"  # 北京（新三板精选层/北交所）
                full_stock_code = f"{stock_code}.BJ"
            elif stock_code.startswith(("0", "3")):
                market = "SZ"  # 深圳
                full_stock_code = f"{stock_code}.SZ"
            else:
                # 默认判断
                market = "SH"
                full_stock_code = f"{stock_code}.SH"

            # 如果已经包含市场后缀，不重复添加
            if "." in stock_code:
                full_stock_code = stock_code

            # 转换买卖方向 - 使用xtconstant常量
            if direction == "BUY":
                xt_direction = xtconstant.STOCK_BUY
            elif direction == "SELL":
                xt_direction = xtconstant.STOCK_SELL
            else:
                raise ValueError(f"不支持的交易方向: {direction}")

            # 价格类型 - 根据交易所和是否有价格来确定
            if price and price > 0:
                # 有价格指定，使用限价
                price_type = xtconstant.FIX_PRICE
                order_price = price
            else:
                # 没有价格指定，根据交易所使用不同的市价单类型
                if market == "SH" or market == "BJ":
                    # 上交所/北交所：最优五档即时成交剩余撤销
                    price_type = xtconstant.MARKET_SH_CONVERT_5_CANCEL  # 42
                elif market == "SZ":
                    # 深交所：即时成交剩余撤销
                    price_type = xtconstant.MARKET_SZ_INSTBUSI_RESTCANCEL  # 46
                    logger.debug(
                        f"深交所市价单类型: MARKET_SZ_INSTBUSI_RESTCANCEL = {xtconstant.MARKET_SZ_INSTBUSI_RESTCANCEL}"
                    )
                else:
                    # 默认使用最优五档
                    price_type = xtconstant.MARKET_SH_CONVERT_5_CANCEL
                    logger.warning(f"未知市场 {market}，使用默认市价单类型")

                order_price = 0  # 市价单价格设为0

            stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
            logger.info(
                f"执行委托(order_stock_async): 证券={stock_display}({full_stock_code}), 市场={market}, 方向={direction}({xt_direction}), 数量={volume}, 价格类型={price_type}({price_type}), 价格={order_price}"
            )

            # 添加调试信息，显示xtconstant的实际值
            logger.debug(
                f"xtconstant values - STOCK_BUY={xtconstant.STOCK_BUY}, STOCK_SELL={xtconstant.STOCK_SELL}, FIX_PRICE={xtconstant.FIX_PRICE}"
            )

            # 使用order_stock_async执行异步委托，避免阻塞
            try:
                # 按照QMT API: order_stock_async(account, stock_code, order_type, order_volume, price_type, price, strategy_name, order_remark)
                seq = self.xt_trader.order_stock_async(
                    self.account,  # 账户对象
                    full_stock_code,  # 证券代码（带市场后缀）
                    xt_direction,  # 买卖方向: STOCK_BUY, STOCK_SELL
                    volume,  # 委托数量
                    price_type,  # 价格类型: FIX_PRICE, MARKET_PRICE
                    order_price,  # 委托价格
                    "auto_trader",  # 策略名称
                    f'Signal_{signal_data.get("signal_id", "unknown")}',  # 订单备注
                )

                # 异步方法返回seq序列号，>0表示成功提交
                if seq and seq > 0:
                    logger.info(f"异步委托提交成功，序列号: {seq}")
                    # 暂时返回序列号作为order_id，实际order_id会在回调中获得
                    order_result = seq
                else:
                    raise Exception(f"异步委托提交失败，序列号: {seq}")

                # 异步API无需等待，结果会通过回调返回

            except AttributeError as e:
                logger.error(f"order 出错: {e}")
                # 如果没有async版本，使用同步版本但加超时保护
                logger.warning("使用同步order_stock (可能阻塞)")

                import concurrent.futures
                import threading

                # 直接调用同步下单，不使用线程池
                order_result = self.xt_trader.order_stock(
                    account=self.account,
                    stock_code=full_stock_code,  # 使用带市场后缀的股票代码
                    order_type=xt_direction,
                    order_volume=volume,
                    price_type=price_type,
                    price=order_price,
                    strategy_name="auto_trader",
                    order_remark=f'Signal_{signal_data.get("signal_id", "unknown")}',
                )

            # 异步API返回seq序列号，>0表示提交成功
            if order_result and isinstance(order_result, int) and order_result > 0:
                seq_id = order_result
                logger.info(f"异步委托提交成功，序列号: {seq_id}")

                # 使用序列号作为临时ID，实际order_id会在回调中更新
                temp_id = f"seq_{seq_id}"

                # 将委托加入活跃列表，用于回调处理和超时监控
                with self.order_lock:
                    self.active_orders[temp_id] = {
                        "timestamp": datetime.now(),
                        "signal_data": signal_data,
                        "seq_id": seq_id,  # 保存序列号
                        "trades": [],  # 成交记录列表
                        "total_filled": 0,  # 总成交量
                        "callback": callback,  # 保存外部回调函数
                        "retry_count": getattr(self, "_current_retry_count", 0),  # 记录重试次数
                    }
                logger.info(f"委托序列 {seq_id} 已加入活跃列表")

                # 保存委托记录到Redis（使用临时ID）
                self._save_order_to_redis(temp_id, signal_data, "submitted")

                return temp_id
            else:
                error_msg = f"委托失败，返回值: {order_result}"
                raise Exception(error_msg)

        except Exception as e:
            raise e

    def cancel_order(self, order_id: str) -> bool:
        """撤销委托（异步执行但等待结果）"""
        if not self.xt_trader or not self.account:
            logger.error("QMT未连接或未初始化，无法撤销委托")
            return False

        try:
            # 直接调用撤单方法（在主线程中运行xtquant）
            return self._cancel_order(order_id)

        except Exception as e:
            logger.error(f"撤销委托时发生错误: {e}")
            return False

    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """查询委托状态（异步执行但等待结果）"""
        if not self.xt_trader or not self.account:
            logger.error("QMT未连接或未初始化，无法查询委托状态")
            return None

        try:
            # 直接调用查询方法（在主线程中运行xtquant）
            return self._get_order_status(order_id)

        except Exception as e:
            logger.error(f"查询委托状态时发生错误: {e}")
            return None

    def get_positions(self) -> Optional[List[Dict[str, Any]]]:
        """获取持仓信息（异步执行但等待结果）"""
        if not self.xt_trader or not self.account:
            logger.error("QMT未连接或未初始化，无法获取持仓")
            return None

        try:
            # 直接调用查询方法（在主线程中运行xtquant）
            return self._get_positions()

        except Exception as e:
            logger.error(f"获取持仓信息时发生错误: {e}")
            return None

    def get_active_orders_count(self) -> int:
        """获取活跃订单数量"""
        with self.order_lock:
            return len(self.active_orders)

    def get_today_orders(self, stock_code: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Return today's QMT order snapshots as normalized dictionaries."""
        if not self.xt_trader or not self.account:
            logger.error("QMT未连接或未初始化，无法获取当日委托")
            return None

        try:
            return self._get_today_orders(stock_code)
        except Exception as e:
            logger.error(f"获取当日委托时发生错误: {e}")
            return None

    def get_active_orders_info(self) -> List[Dict[str, Any]]:
        """获取活跃委托信息"""
        with self.order_lock:
            return [
                {
                    "order_id": order_id,
                    "signal_data": info.get("signal_data", {}),
                    "timestamp": info["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                    "elapsed_seconds": (datetime.now() - info["timestamp"]).total_seconds(),
                    "last_status": info.get("last_status", "unknown"),
                    "total_filled": info.get("total_filled", 0),
                    "trades_count": len(info.get("trades", [])),
                }
                for order_id, info in self.active_orders.items()
            ]

    def get_trading_stats(self) -> Dict[str, Any]:
        """获取交易统计信息"""
        with self.stats_lock:
            stats = self.stats.copy()

        # 添加成功率和队列状态
        total = stats["total_orders"]
        if total > 0:
            stats["success_rate"] = (stats["successful_orders"] / total) * 100
        else:
            stats["success_rate"] = 0

        # 添加线程池状态
        stats["thread_pool_active"] = (
            len(self.trade_executor._threads)
            if hasattr(self.trade_executor, "_threads") and self.trade_executor._threads
            else 0
        )
        stats["thread_pool_max"] = self.trade_executor._max_workers
        stats["xtquant_main_thread"] = True  # xtquant运行在主线程

        return stats

    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        return {
            "active_orders_count": self.get_active_orders_count(),
            "thread_queue_pending": self.stats["pending_count"],
            "total_orders_submitted": self.stats["total_orders"],
            "success_rate": f"{self.get_trading_stats()['success_rate']:.1f}%",
            "xtquant_main_thread": True,
        }

    def _save_order_to_redis(
        self, order_id: str, signal_data: Dict[str, Any], status: str, error_msg: str = None
    ):
        """保存委托记录到Redis"""
        if not settings.redis_trade_records_enabled:
            return

        try:
            # 构建交易记录数据
            trade_record = {
                "order_id": order_id,
                "stock_code": signal_data.get("stock_code", signal_data.get("symbol", "")),
                "direction": signal_data.get("direction", signal_data.get("action", "")),
                "volume": signal_data.get("volume", signal_data.get("quantity", 0)),
                "price": signal_data.get("price", 0),
                "status": status,
                "timestamp": datetime.now().isoformat(),
                "signal_data": signal_data,
            }

            # 如果有错误信息，添加到记录中
            if error_msg:
                trade_record["error_message"] = error_msg

            # 使用order_id作为trade_id（后续如果有实际成交记录可以更新）
            trade_id = f"order_{order_id}"

            # 保存到Redis
            success = redis_trade_client.save_trade_record(order_id, trade_id, trade_record)
            if success:
                logger.info(f"委托记录已保存到Redis: {order_id}_{trade_id}")

        except Exception as e:
            logger.error(f"保存委托记录到Redis异常: {e}")

    def _save_trade_execution_to_redis(self, order_id: str, trade_info: Dict[str, Any]):
        """保存成交记录到Redis"""
        if not settings.redis_trade_records_enabled:
            return

        try:
            # 获取实际成交信息
            filled_volume = trade_info.get("filled_volume", trade_info.get("traded_volume", 0))
            avg_price = trade_info.get("avg_price", trade_info.get("traded_price", 0))

            if filled_volume > 0:  # 有成交量才保存
                # 构建成交记录
                execution_record = {
                    "order_id": order_id,
                    "trade_id": f"exec_{order_id}_{int(time.time())}",
                    "stock_code": trade_info.get("stock_code", ""),
                    "filled_volume": filled_volume,
                    "avg_price": avg_price,
                    "trade_amount": filled_volume * avg_price,
                    "execution_time": datetime.now().isoformat(),
                    "order_status": trade_info.get("order_status", ""),
                    "original_trade_info": trade_info,
                }

                trade_id = execution_record["trade_id"]

                # 保存成交记录到Redis
                success = redis_trade_client.save_trade_record(order_id, trade_id, execution_record)
                if success:
                    logger.info(
                        f"成交记录已保存到Redis: {order_id}_{trade_id} (成交量:{filled_volume}, 成交价:{avg_price})"
                    )

        except Exception as e:
            logger.error(f"保存成交记录到Redis异常: {e}")

    def get_redis_trade_records_info(self) -> Dict[str, Any]:
        """获取Redis交易记录信息"""
        if not settings.redis_trade_records_enabled:
            return {"enabled": False, "message": "Redis交易记录存储未启用"}

        try:
            count = redis_trade_client.get_trade_records_count()
            return {
                "enabled": True,
                "records_count": count,
                "cleanup_time": settings.redis_trade_cleanup_time,
                "redis_host": settings.redis_host,
                "redis_port": settings.redis_port,
            }
        except Exception as e:
            return {"enabled": True, "error": str(e)}

    def _cancel_order(self, order_id: str) -> bool:
        """撤销委托"""
        try:
            # 如果是序列号格式，无法直接撤单
            if order_id.startswith("seq_"):
                logger.warning(f"无法撤销序列号委托 {order_id}，等待真实order_id")
                return False

            result = self.xt_trader.cancel_order_stock(self.account, int(order_id))

            if result == 0:
                logger.info(f"撤销委托成功，委托编号: {order_id}")
                # 从活跃列表中移除委托
                with self.order_lock:
                    self.active_orders.pop(order_id, None)
                return True
            else:
                logger.error(f"撤销委托失败，委托编号: {order_id}, 错误代码: {result}")
                return False

        except Exception as e:
            logger.error(f"撤单异常: {e}")
            return False

    def _get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """查询委托状态"""
        try:
            # 如果是序列号格式，暂时跳过查询
            if order_id.startswith("seq_"):
                return None

            order = self.xt_trader.query_stock_order(self.account, int(order_id))

            if order:
                return {
                    "order_id": str(order.order_id),
                    "stock_code": order.stock_code,
                    "order_status": order.order_status,
                    "filled_volume": getattr(
                        order, "filled_qty", getattr(order, "order_volume", 0)
                    ),
                    "avg_price": getattr(order, "avg_price", getattr(order, "price", 0)),
                }
            return None

        except Exception as e:
            logger.error(f"查询委托状态异常: {e}")
            return None

    def _get_positions(self) -> Optional[List[Dict[str, Any]]]:
        """查询持仓"""
        try:
            positions = self.xt_trader.query_stock_positions(self.account)

            if positions is None:
                return None

            if not positions:
                return []

            return [
                {
                    "stock_code": pos.stock_code,
                    "volume": getattr(pos, "volume", 0),
                    "available_volume": getattr(pos, "can_use_volume", 0),
                    "avg_price": getattr(pos, "avg_price", 0),
                    "market_value": getattr(pos, "market_value", 0),
                    "last_price": getattr(pos, "last_price", 0),
                    "account_id": getattr(pos, "account_id", ""),
                }
                for pos in positions
                if pos
            ]

        except Exception as e:
            logger.error(f"查询持仓异常: {e}")
            return None

    def _get_today_orders(self, stock_code: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Query today's orders and normalize them for reconciliation/reporting."""
        try:
            orders = self.xt_trader.query_stock_orders(self.account, cancelable_only=False)

            if orders is None:
                return None

            target = str(stock_code or "").strip().upper()
            results: List[Dict[str, Any]] = []
            for order in orders:
                order_code = str(getattr(order, "stock_code", "") or "").strip()
                if target and order_code.upper() != target:
                    continue

                order_type = getattr(order, "order_type", None)
                if order_type == xtconstant.STOCK_BUY or str(order_type).strip().upper() == "BUY":
                    direction = "BUY"
                elif (
                    order_type == xtconstant.STOCK_SELL or str(order_type).strip().upper() == "SELL"
                ):
                    direction = "SELL"
                else:
                    direction = "UNKNOWN"
                results.append(
                    {
                        "order_id": str(getattr(order, "order_id", "") or ""),
                        "stock_code": order_code,
                        "direction": direction,
                        "order_volume": int(getattr(order, "order_volume", 0) or 0),
                        "traded_volume": int(getattr(order, "traded_volume", 0) or 0),
                        "traded_price": float(getattr(order, "traded_price", 0) or 0.0),
                        "order_status": getattr(order, "order_status", None),
                        "order_time": getattr(order, "order_time", None),
                    }
                )

            return results
        except Exception as e:
            logger.error(f"鏌ヨ褰撴棩濮旀墭寮傚父: {e}")
            return None

    def _start_timeout_monitor(self):
        """启动订单超时监控"""
        if self.timeout_monitor_running:
            return

        self.timeout_monitor_running = True
        self.timeout_monitor_thread = threading.Thread(
            target=self._timeout_monitor_loop, daemon=True, name="OrderTimeoutMonitor"
        )
        self.timeout_monitor_thread.start()
        logger.info(f"订单超时监控已启动，超时时间: {settings.auto_cancel_timeout}秒")

    def _stop_timeout_monitor(self):
        """停止订单超时监控"""
        if self.timeout_monitor_running:
            self.timeout_monitor_running = False
            logger.info("订单超时监控已停止")

    def _timeout_monitor_loop(self):
        """订单超时监控循环"""
        logger.info("订单超时监控线程已启动")

        while self.timeout_monitor_running and not self._shutdown:
            try:
                current_time = datetime.now()
                timeout_orders = []

                # 查找超时订单
                with self.order_lock:
                    for order_id, order_info in list(self.active_orders.items()):
                        order_time = order_info.get("timestamp")
                        if order_time:
                            elapsed_time = (current_time - order_time).total_seconds()
                            if elapsed_time > settings.auto_cancel_timeout:
                                timeout_orders.append((order_id, order_info, elapsed_time))

                # 处理超时订单
                for order_id, order_info, elapsed_time in timeout_orders:
                    try:
                        signal_data = order_info.get("signal_data", {})
                        stock_code = signal_data.get("stock_code", "Unknown")
                        stock_display = (
                            get_stock_display_name(stock_code)
                            if stock_code != "Unknown"
                            else stock_code
                        )

                        logger.warning(
                            f"订单超时 {elapsed_time:.1f}秒: {order_id} ({stock_display}), 开始自动撤单"
                        )

                        # 标记为超时撤单
                        with self.order_lock:
                            if order_id in self.active_orders:
                                self.active_orders[order_id]["timeout_cancelled"] = True

                        # 尝试撤单
                        cancel_success = self._cancel_order(order_id)

                        if cancel_success:
                            logger.info(f"超时订单撤单成功: {order_id}")
                            # 发送撤单通知，使用状态描述
                            if self.notifier:
                                self.notifier.notify_error(
                                    f"订单超时自动撤单: {stock_display}",
                                    f"委托{order_id}超时{elapsed_time:.1f}秒，状态将变为{get_status_name(OrderStatus.CANCELED)}",
                                )
                        else:
                            # 如果撤单失败，从活跃列表中移除（可能订单已经成交或其他状态）
                            with self.order_lock:
                                if order_id in self.active_orders:
                                    self.active_orders.pop(order_id)
                                    logger.warning(f"撤单失败，已从活跃列表移除: {order_id}")

                    except Exception as e:
                        logger.error(f"处理超时订单异常 {order_id}: {e}")
                        # 移除有问题的订单
                        with self.order_lock:
                            if order_id in self.active_orders:
                                self.active_orders.pop(order_id)

                # 每30秒检查一次
                time.sleep(30)

            except Exception as e:
                logger.error(f"订单超时监控异常: {e}")
                time.sleep(30)

        logger.info("订单超时监控线程已停止")
