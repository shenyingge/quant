from src.infrastructure.notifications import FeishuNotifier


class CaptureNotifier(FeishuNotifier):
    def __init__(self):
        super().__init__()
        self.sent_messages = []

    def send_message(self, message: str, title: str = "交易通知") -> bool:
        self.sent_messages.append({"title": title, "message": message})
        return True


def test_feishu_notifier_supports_trading_engine_runtime_notifications():
    notifier = CaptureNotifier()

    assert notifier.notify_service_status("已启动", "交易引擎成功启动") is True
    assert notifier.notify_error("QMT连接失败", "服务启动") is True
    assert (
        notifier.notify_order_placed(
            {
                "stock_code": "601138.SH",
                "direction": "BUY",
                "volume": 100,
                "price": 52.34,
                "signal_id": "SIG-1",
            },
            "ORDER-1",
        )
        is True
    )
    assert (
        notifier.notify_order_filled(
            {
                "order_id": "ORDER-1",
                "stock_code": "601138.SH",
                "filled_qty": 100,
                "avg_price": 52.34,
            }
        )
        is True
    )
    assert (
        notifier.notify_daily_pnl_summary(
            {
                "date_display": "2026年04月07日",
                "summary": {
                    "total_orders": 2,
                    "buy_orders": 1,
                    "sell_orders": 1,
                    "total_amount": 10468.0,
                },
                "performance": {
                    "estimated_realized_pnl": 128.5,
                    "trading_cost_estimate": 4.2,
                    "note": "测试汇总",
                },
                "stock_breakdown": [
                    {"stock_display": "601138.SH", "total_amount": 10468.0, "net_volume": 0}
                ],
            }
        )
        is True
    )

    assert [payload["title"] for payload in notifier.sent_messages] == [
        "✅ 交易引擎",
        "❌ 交易引擎",
        "📬 订单已提交",
        "✅ 订单已成交",
        "📊 当日盈亏汇总",
    ]
    assert "事件: 已启动" in notifier.sent_messages[0]["message"]
    assert "详情: 交易引擎成功启动" in notifier.sent_messages[0]["message"]
    assert "详情: 服务启动: QMT连接失败" in notifier.sent_messages[1]["message"]
    assert "订单ID: ORDER-1" in notifier.sent_messages[2]["message"]
    assert "信号ID: SIG-1" in notifier.sent_messages[2]["message"]
    assert "成交数量: 100" in notifier.sent_messages[3]["message"]
    assert "估算已实现盈亏: 128.50" in notifier.sent_messages[4]["message"]
