from src.infrastructure.notifications import FeishuNotifier


class CaptureNotifier(FeishuNotifier):
    def __init__(self):
        super().__init__()
        self.sent_messages = []

    def send_message(self, message: str, title: str = "交易通知") -> bool:
        self.sent_messages.append({"title": title, "message": message})
        return True


def test_runtime_notification_uses_readable_chinese():
    notifier = CaptureNotifier()

    notifier.notify_runtime_event("交易引擎", "启动", "开始监听 Redis 下单信号", "info")

    payload = notifier.sent_messages[-1]
    assert payload["title"] == "🔔 交易引擎"
    assert "组件: 交易引擎" in payload["message"]
    assert "事件: 启动" in payload["message"]
    assert "详情: 开始监听 Redis 下单信号" in payload["message"]


def test_signal_received_notification_uses_readable_chinese():
    notifier = CaptureNotifier()
    signal_data = {
        "signal_id": "SIG-001",
        "stock_code": "601138.SH",
        "direction": "SELL",
        "volume": 1000,
        "price": 12.34,
    }

    notifier.notify_signal_received(signal_data)

    payload = notifier.sent_messages[-1]
    assert payload["title"] == "🔔 交易信号"
    assert "收到交易信号:" in payload["message"]
    assert "股票信息:" in payload["message"]
    assert "操作类型: SELL" in payload["message"]
    assert "数量: 1000" in payload["message"]
    assert "价格: 12.34" in payload["message"]
    assert "信号ID: SIG-001" in payload["message"]


def test_service_status_notification_uses_readable_chinese():
    notifier = CaptureNotifier()

    notifier.notify_service_status("已启动", "QMT 连接就绪")

    payload = notifier.sent_messages[-1]
    assert payload["title"] == "✅ 交易引擎"
    assert "组件: 交易引擎" in payload["message"]
    assert "事件: 已启动" in payload["message"]
    assert "详情: QMT 连接就绪" in payload["message"]
