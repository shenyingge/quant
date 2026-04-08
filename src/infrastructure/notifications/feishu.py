"""Feishu (飞书) webhook notifications (migrated from src/notifications.py)."""

import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

import requests

from src.infrastructure.config import settings
from src.infrastructure.logger_config import configured_logger as logger
from src.trading.qmt_constants import get_account_status_name, get_status_name

TRADING_ENGINE_NAME = "交易引擎"


def _safe_stock_display_name(stock_code: Optional[str]) -> str:
    """Resolve stock display name without triggering package import cycles."""
    if not stock_code:
        return "UNKNOWN"

    try:
        from src.data_manager.stock_info import get_stock_display_name

        return get_stock_display_name(stock_code)
    except Exception:
        return stock_code


class FeishuNotifier:
    _failure_notification_cache = {}
    _failure_notification_lock = threading.Lock()

    def __init__(self):
        self.webhook_url = settings.feishu_webhook_url
        self._notification_cache = {}  # 通知去重缓存

    def send_message(self, message: str, title: str = "交易通知") -> bool:
        """发送飞书消息"""
        if not self.webhook_url:
            logger.warning("飞书Webhook URL未配置，跳过通知")
            return False

        try:
            payload = {
                "msg_type": "interactive",
                "card": {
                    "elements": [
                        {"tag": "div", "text": {"content": message, "tag": "lark_md"}},
                        {"tag": "hr"},
                        {
                            "tag": "div",
                            "text": {
                                "content": f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                                "tag": "lark_md",
                            },
                        },
                    ],
                    "header": {
                        "title": {"content": title, "tag": "plain_text"},
                        "template": "blue",
                    },
                },
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )

            if response.status_code == 200:
                logger.info("飞书通知发送成功")
                return True
            else:
                logger.error(
                    f"飞书通知发送失败，状态码: {response.status_code}, 响应: {response.text}"
                )
                return False

        except Exception as e:
            logger.error(f"发送飞书通知时发生错误: {e}")
            return False

    @staticmethod
    def _format_number(value: Any, digits: int = 2) -> str:
        """Format numeric values for notification messages."""
        if value is None:
            return "N/A"

        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)

        if number.is_integer():
            return f"{int(number):,}"

        return f"{number:,.{digits}f}"

    @staticmethod
    def _normalize_failure_key(*parts: Any) -> str:
        """Builds a stable throttle key for repeated failure notifications."""
        normalized_parts = []
        for part in parts:
            text = " ".join(str(part or "").split())
            normalized_parts.append(text[:200])
        return "|".join(normalized_parts)

    def _should_send_failure_notification(self, category: str, *parts: Any) -> bool:
        """Rate-limits repeated failure notifications across notifier instances."""
        cooldown_seconds = max(
            int(getattr(settings, "feishu_failure_notify_cooldown_seconds", 300) or 0),
            0,
        )
        if cooldown_seconds <= 0:
            return True

        now = time.time()
        cache_key = f"{category}:{self._normalize_failure_key(*parts)}"

        with FeishuNotifier._failure_notification_lock:
            expired_keys = [
                key
                for key, sent_at in FeishuNotifier._failure_notification_cache.items()
                if now - sent_at >= cooldown_seconds
            ]
            for key in expired_keys:
                del FeishuNotifier._failure_notification_cache[key]

            last_sent_at = FeishuNotifier._failure_notification_cache.get(cache_key)
            if last_sent_at is not None and now - last_sent_at < cooldown_seconds:
                logger.debug(f"失败通知限频跳过: {cache_key}")
                return False

            FeishuNotifier._failure_notification_cache[cache_key] = now

            if len(FeishuNotifier._failure_notification_cache) > 512:
                oldest_key = min(
                    FeishuNotifier._failure_notification_cache,
                    key=FeishuNotifier._failure_notification_cache.get,
                )
                del FeishuNotifier._failure_notification_cache[oldest_key]

        return True

    def notify_runtime_event(
        self,
        component: str,
        event: str,
        detail: str = "",
        level: str = "info",
    ) -> bool:
        """统一的运行时事件通知（服务启停、连接状态、健康检查等）"""
        title_map = {
            "info": f"🔔 {component}",
            "success": f"✅ {component}",
            "warning": f"⚠️ {component}",
            "error": f"❌ {component}",
        }

        message = f"组件: {component}\n事件: {event}"
        if detail:
            message += f"\n详情: {detail}"

        if level in {"warning", "error"} and not self._should_send_failure_notification(
            "runtime_event", component, event, detail, level
        ):
            return True

        return self.send_message(message, title_map.get(level, title_map["info"]))

    def notify_service_status(self, status: str, message: str = "") -> bool:
        """Send trading-engine lifecycle notifications expected by runtime services."""
        level = "success" if "启动" in status else "info"
        return self.notify_runtime_event(TRADING_ENGINE_NAME, status, message, level)

    def notify_error(self, error_message: str, context: str = "") -> bool:
        """Send runtime error notifications using the unified event format."""
        detail = f"{context}: {error_message}" if context else str(error_message)
        return self.notify_runtime_event(TRADING_ENGINE_NAME, "运行异常", detail, "error")

    def notify_order_placed(self, signal_data: Dict[str, Any], order_id: Any) -> bool:
        """Send order submission notifications for trading-engine order placement."""
        stock_code = signal_data.get("stock_code")
        stock_display = _safe_stock_display_name(stock_code)
        message = f"订单ID: {order_id}\n"
        message += f"股票: {stock_display}\n"
        message += f"方向: {signal_data.get('direction', 'N/A')}\n"
        message += f"数量: {self._format_number(signal_data.get('volume'), digits=0)}\n"
        message += f"价格: {self._format_number(signal_data.get('price'))}"

        signal_id = signal_data.get("signal_id")
        if signal_id:
            message += f"\n信号ID: {signal_id}"

        return self.send_message(message, "📬 订单已提交")

    def notify_order_filled(self, order_info: Dict[str, Any]) -> bool:
        """Send order fill notifications after execution callbacks confirm a trade."""
        stock_code = order_info.get("stock_code")
        stock_display = _safe_stock_display_name(stock_code)
        filled_qty = order_info.get("filled_qty", order_info.get("filled_volume"))
        avg_price = order_info.get("avg_price", order_info.get("filled_price"))

        trade_amount_text = "N/A"
        try:
            if filled_qty is not None and avg_price is not None:
                trade_amount_text = self._format_number(float(filled_qty) * float(avg_price))
        except (TypeError, ValueError):
            trade_amount_text = "N/A"

        message = f"订单ID: {order_info.get('order_id', 'N/A')}\n"
        message += f"股票: {stock_display}\n"
        message += f"成交数量: {self._format_number(filled_qty, digits=0)}\n"
        message += f"成交均价: {self._format_number(avg_price)}\n"
        message += f"成交金额: {trade_amount_text}"
        return self.send_message(message, "✅ 订单已成交")

    def notify_daily_pnl_summary(self, pnl_data: Dict[str, Any]) -> bool:
        """Send the end-of-day PnL summary used by the trading engine scheduler."""
        summary = pnl_data.get("summary", {})
        performance = pnl_data.get("performance", {})
        stock_breakdown = pnl_data.get("stock_breakdown", [])

        message = f"日期: {pnl_data.get('date_display', 'N/A')}\n"
        message += f"总订单数: {self._format_number(summary.get('total_orders'), digits=0)}\n"
        message += f"买入订单: {self._format_number(summary.get('buy_orders'), digits=0)}\n"
        message += f"卖出订单: {self._format_number(summary.get('sell_orders'), digits=0)}\n"
        message += f"成交总额: {self._format_number(summary.get('total_amount'))}\n"
        message += (
            f"估算已实现盈亏: "
            f"{self._format_number(performance.get('estimated_realized_pnl'))}\n"
        )
        message += (
            f"交易成本估算: {self._format_number(performance.get('trading_cost_estimate'))}"
        )

        note = performance.get("note")
        if note:
            message += f"\n说明: {note}"

        if stock_breakdown:
            top_stock = stock_breakdown[0]
            message += (
                f"\n主要标的: {top_stock.get('stock_display', 'N/A')}"
                f" | 成交额 {self._format_number(top_stock.get('total_amount'))}"
            )

        return self.send_message(message, "📊 当日盈亏汇总")

    def notify_signal_received(self, signal_data: Dict[str, Any]) -> bool:
        """通知收到交易信号"""
        stock_code = signal_data.get("stock_code", "N/A")
        stock_display = _safe_stock_display_name(stock_code) if stock_code != "N/A" else "N/A"

        message = f"收到交易信号:\n"
        message += f"• 股票信息: {stock_display}\n"
        message += f"• 操作类型: {signal_data.get('direction', 'N/A')}\n"
        message += f"• 数量: {signal_data.get('volume', 'N/A')}\n"
        message += f"• 价格: {signal_data.get('price', 'N/A')}\n"
        message += f"• 信号ID: {signal_data.get('signal_id', 'N/A')}"

        return self.send_message(message, "🔔 交易信号")
