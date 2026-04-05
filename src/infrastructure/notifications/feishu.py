"""Feishu (飞书) webhook notifications (migrated from src/notifications.py)."""

import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

import requests

from src.config import settings
from src.logger_config import configured_logger as logger
from src.trading.qmt_constants import get_account_status_name, get_status_name
from src.data_manager.stock_info import get_stock_display_name
from src.strategy.core.models import SignalCard

STRATEGY_ENGINE_NAME = "策略引擎"
TRADING_ENGINE_NAME = "交易引擎"


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

    def notify_t0_signal(self, signal_card: Any, stock_code: Optional[str] = None) -> bool:
        """Send T+0 strategy signal notifications."""
        if isinstance(signal_card, SignalCard):
            return self._notify_t0_signal_from_card(signal_card, stock_code)

        signal = signal_card.get("signal", {})
        action = signal.get("action", "observe")
        is_error = bool(signal_card.get("error"))

        if action == "observe" and not is_error and not settings.t0_notify_observe_signals:
            logger.info(
                "策略引擎 observe 信号通知已跳过，可通过 T0_NOTIFY_OBSERVE_SIGNALS=true 开启"
            )
            return True

        stock_code = stock_code or settings.t0_stock_code
        stock_display = get_stock_display_name(stock_code) if stock_code else settings.t0_stock_code
        market = signal_card.get("market", {})
        position = signal_card.get("position", {})
        scores = signal_card.get("scores", {})

        message = f"股票: {stock_display}\n"
        message += (
            f"时间: {signal_card.get('as_of_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}\n"
        )
        message += f"市场状态: {signal_card.get('regime', 'unknown')}\n"
        message += f"信号: {action}\n"
        message += f"原因: {signal.get('reason', 'N/A')}\n"
        message += f"建议价格: {self._format_number(signal.get('price'))}\n"
        message += f"建议数量: {self._format_number(signal.get('volume'), digits=0)}\n"

        if market:
            message += (
                f"最新价 / VWAP: {self._format_number(market.get('price'))}"
                f" / {self._format_number(market.get('vwap'))}\n"
            )

        if position:
            message += (
                f"仓位(总 / 可用): {self._format_number(position.get('total'), digits=0)}"
                f" / {self._format_number(position.get('available'), digits=0)}\n"
            )

        if scores:
            message += (
                f"评分(fake_breakout / absorption): "
                f"{self._format_number(scores.get('fake_breakout'))}"
                f" / {self._format_number(scores.get('absorption'))}"
            )

        if is_error:
            if not self._should_send_failure_notification(
                "t0_signal_error", stock_code, signal.get("reason"), signal.get("action")
            ):
                return True
            title = f"❌ {STRATEGY_ENGINE_NAME}异常"
        elif action == "observe":
            title = f"👀 {STRATEGY_ENGINE_NAME}观察信号"
        else:
            title = f"📮 {STRATEGY_ENGINE_NAME}交易信号"

        return self.send_message(message, title)

    def _notify_t0_signal_from_card(
        self, signal_card: SignalCard, stock_code: Optional[str] = None
    ) -> bool:
        action = signal_card.signal.action

        if action == "observe" and not settings.t0_notify_observe_signals:
            logger.info(
                "策略引擎 observe 信号通知已跳过，可通过 T0_NOTIFY_OBSERVE_SIGNALS=true 开启"
            )
            return True

        stock_code = stock_code or settings.t0_stock_code
        stock_display = get_stock_display_name(stock_code) if stock_code else settings.t0_stock_code

        message = f"股票: {stock_display}\n"
        message += f"时间: {signal_card.as_of_time}\n"
        message += f"市场状态: {signal_card.regime}\n"
        message += f"信号: {signal_card.signal.action}\n"
        message += f"原因: {signal_card.signal.reason}\n"
        message += f"建议价格: {self._format_number(signal_card.signal.price)}\n"
        message += f"建议数量: {self._format_number(signal_card.signal.volume, digits=0)}\n"
        message += (
            f"最新价 / VWAP: {self._format_number(signal_card.market.price)}"
            f" / {self._format_number(signal_card.market.vwap)}\n"
        )
        message += (
            f"仓位(总 / 可用): {self._format_number(signal_card.position.total, digits=0)}"
            f" / {self._format_number(signal_card.position.available, digits=0)}\n"
        )
        message += (
            f"评分(fake_breakout / absorption): "
            f"{self._format_number(signal_card.scores.get('fake_breakout'))}"
            f" / {self._format_number(signal_card.scores.get('absorption'))}"
        )

        title = (
            f"👀 {STRATEGY_ENGINE_NAME}观察信号"
            if action == "observe"
            else f"📮 {STRATEGY_ENGINE_NAME}交易信号"
        )
        return self.send_message(message, title)

    def notify_t0_position_sync(self, stock_code: str, success: bool, detail: str = "") -> bool:
        """Send T+0 position-sync notifications."""
        stock_display = get_stock_display_name(stock_code) if stock_code else settings.t0_stock_code
        message = f"股票: {stock_display}\n结果: {'成功' if success else '失败'}"
        if detail:
            message += f"\n详情: {detail}"

        if not success and not self._should_send_failure_notification(
            "t0_position_sync_failure", stock_code, detail
        ):
            return True

        title = (
            f"✅ {STRATEGY_ENGINE_NAME}仓位同步"
            if success
            else f"❌ {STRATEGY_ENGINE_NAME}仓位同步"
        )
        return self.send_message(message, title)

    def notify_signal_received(self, signal_data: Dict[str, Any]) -> bool:
        """通知收到交易信号"""
        stock_code = signal_data.get("stock_code", "N/A")
        stock_display = get_stock_display_name(stock_code) if stock_code != "N/A" else "N/A"

        message = f"收到交易信号:\n"
        message += f"• 股票信息: {stock_display}\n"
        message += f"• 操作类型: {signal_data.get('direction', 'N/A')}\n"
        message += f"• 数量: {signal_data.get('volume', 'N/A')}\n"
        message += f"• 价格: {signal_data.get('price', 'N/A')}\n"
        message += f"• 信号ID: {signal_data.get('signal_id', 'N/A')}"

        return self.send_message(message, "🔔 交易信号")
