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

    notifier.notify_runtime_event("策略引擎", "启动", "开始执行一次策略信号生成", "info")

    payload = notifier.sent_messages[-1]
    assert payload["title"] == "🔔 策略引擎"
    assert "组件: 策略引擎" in payload["message"]
    assert "事件: 启动" in payload["message"]
    assert "详情: 开始执行一次策略信号生成" in payload["message"]


def test_t0_signal_notification_uses_readable_chinese():
    notifier = CaptureNotifier()
    signal_card = {
        "as_of_time": "2026-03-26 10:30:00",
        "regime": "uptrend",
        "signal": {
            "action": "sell",
            "reason": "冲高回落",
            "price": 12.34,
            "volume": 1000,
        },
        "market": {"price": 12.30, "vwap": 12.12},
        "position": {"total": 3100, "available": 900},
        "scores": {"fake_breakout": 0.81, "absorption": 0.22},
        "error": False,
    }

    notifier.notify_t0_signal(signal_card, "601138.SH")

    payload = notifier.sent_messages[-1]
    assert payload["title"] == "📮 策略引擎交易信号"
    assert "股票:" in payload["message"]
    assert "时间: 2026-03-26 10:30:00" in payload["message"]
    assert "市场状态: uptrend" in payload["message"]
    assert "信号: sell" in payload["message"]
    assert "原因: 冲高回落" in payload["message"]
    assert "建议价格: 12.34" in payload["message"]
    assert "建议数量: 1,000" in payload["message"]
    assert "最新价 / VWAP: 12.30 / 12.12" in payload["message"]
    assert "仓位(总 / 可用): 3,100 / 900" in payload["message"]
    assert "评分(fake_breakout / absorption): 0.81 / 0.22" in payload["message"]


def test_t0_position_sync_notification_uses_readable_chinese():
    notifier = CaptureNotifier()

    notifier.notify_t0_position_sync("601138.SH", True, "已从QMT成功同步仓位")

    payload = notifier.sent_messages[-1]
    assert payload["title"] == "✅ 策略引擎仓位同步"
    assert "股票:" in payload["message"]
    assert "结果: 成功" in payload["message"]
    assert "详情: 已从QMT成功同步仓位" in payload["message"]
