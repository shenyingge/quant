import requests
import json
from typing import Dict, Any, Optional
from datetime import datetime
from src.logger_config import configured_logger as logger
from src.config import settings
from src.stock_info import get_stock_display_name

class FeishuNotifier:
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
                        {
                            "tag": "div",
                            "text": {
                                "content": message,
                                "tag": "lark_md"
                            }
                        },
                        {
                            "tag": "hr"
                        },
                        {
                            "tag": "div",
                            "text": {
                                "content": f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                                "tag": "lark_md"
                            }
                        }
                    ],
                    "header": {
                        "title": {
                            "content": title,
                            "tag": "plain_text"
                        },
                        "template": "blue"
                    }
                }
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )

            if response.status_code == 200:
                logger.info("飞书通知发送成功")
                return True
            else:
                logger.error(f"飞书通知发送失败，状态码: {response.status_code}, 响应: {response.text}")
                return False

        except Exception as e:
            logger.error(f"发送飞书通知时发生错误: {e}")
            return False

    def notify_signal_received(self, signal_data: Dict[str, Any]) -> bool:
        """通知收到交易信号"""
        stock_code = signal_data.get('stock_code', 'N/A')
        stock_display = get_stock_display_name(stock_code) if stock_code != 'N/A' else 'N/A'
        
        message = f"收到交易信号:\n"
        message += f"• 股票信息: {stock_display}\n"
        message += f"• 操作类型: {signal_data.get('direction', 'N/A')}\n"
        message += f"• 数量: {signal_data.get('volume', 'N/A')}\n"
        message += f"• 价格: {signal_data.get('price', 'N/A')}\n"
        message += f"• 信号ID: {signal_data.get('signal_id', 'N/A')}"

        return self.send_message(message, "🔔 交易信号")

    def notify_order_placed(self, signal_data: Dict[str, Any], order_id: str) -> bool:
        """通知订单已下达"""
        # 创建去重键
        cache_key = f"order_placed_{order_id}"
        
        # 检查是否已发送过
        if cache_key in self._notification_cache:
            logger.debug(f"跳过重复的订单确认通知: {cache_key}")
            return True
        
        # 记录已发送
        self._notification_cache[cache_key] = True
        
        # 清理缓存（保留最近50个）
        if len(self._notification_cache) > 50:
            keys_to_remove = list(self._notification_cache.keys())[:25]
            for key in keys_to_remove:
                del self._notification_cache[key]
        
        stock_code = signal_data.get('stock_code', 'N/A')
        stock_display = get_stock_display_name(stock_code) if stock_code != 'N/A' else 'N/A'
        
        message = f"订单已下达:\n"
        message += f"• 订单ID: {order_id}\n"
        message += f"• 股票信息: {stock_display}\n"
        message += f"• 操作类型: {signal_data.get('direction', 'N/A')}\n"
        message += f"• 数量: {signal_data.get('volume', 'N/A')}\n"
        message += f"• 价格: {signal_data.get('price', 'N/A')}"

        return self.send_message(message, "✅ 订单确认")

    def notify_order_filled(self, order_info: Dict[str, Any]) -> bool:
        """通知订单成交"""
        stock_code = order_info.get('stock_code', 'N/A')
        stock_display = get_stock_display_name(stock_code) if stock_code != 'N/A' else 'N/A'
        
        filled_qty = float(order_info.get('filled_qty', 0))
        avg_price = float(order_info.get('avg_price', 0))
        trade_amount = filled_qty * avg_price
        
        message = f"订单已成交:\n"
        message += f"• 订单ID: {order_info.get('order_id', 'N/A')}\n"
        message += f"• 股票信息: {stock_display}\n"
        message += f"• 成交数量: {order_info.get('filled_qty', 'N/A')}\n"
        message += f"• 成交价格: {order_info.get('avg_price', 'N/A')}\n"
        message += f"• 成交金额: {trade_amount:.2f}元"

        return self.send_message(message, "🎉 订单成交")

    def notify_error(self, error_message: str, context: str = "") -> bool:
        """通知错误信息"""
        message = f"系统错误:\n"
        message += f"• 错误信息: {error_message}\n"
        if context:
            message += f"• 上下文: {context}"

        return self.send_message(message, "❌ 系统错误")

    def notify_service_status(self, status: str, message: str = "") -> bool:
        """通知服务状态"""
        msg = f"服务状态: {status}"
        if message:
            msg += f"\n详情: {message}"

        title = "🔄 服务状态" if status == "运行中" else "⚠️ 服务状态"
        return self.send_message(msg, title)
