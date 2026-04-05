from src.config import settings
from src.infrastructure.notifications import FeishuNotifier


def test_runtime_error_notifications_are_throttled_across_instances(monkeypatch):
    sent_messages = []
    FeishuNotifier._failure_notification_cache.clear()
    monkeypatch.setattr(settings, "feishu_failure_notify_cooldown_seconds", 300)
    monkeypatch.setattr(
        FeishuNotifier,
        "send_message",
        lambda self, message, title="交易通知": sent_messages.append((title, message)) or True,
    )

    notifier_a = FeishuNotifier()
    notifier_b = FeishuNotifier()

    assert (
        notifier_a.notify_runtime_event("策略引擎", "轮询异常", "分钟数据获取失败", "error") is True
    )
    assert (
        notifier_b.notify_runtime_event("策略引擎", "轮询异常", "分钟数据获取失败", "error") is True
    )
    assert len(sent_messages) == 1


def test_t0_error_signal_notifications_are_throttled(monkeypatch):
    sent_messages = []
    FeishuNotifier._failure_notification_cache.clear()
    monkeypatch.setattr(settings, "feishu_failure_notify_cooldown_seconds", 300)
    monkeypatch.setattr(
        FeishuNotifier,
        "send_message",
        lambda self, message, title="交易通知": sent_messages.append((title, message)) or True,
    )

    signal_card = {
        "as_of_time": "2026-03-27 11:20:00",
        "regime": "unknown",
        "signal": {
            "action": "observe",
            "reason": "分钟数据获取失败",
            "price": 0,
            "volume": 0,
        },
        "error": True,
    }

    notifier = FeishuNotifier()

    assert notifier.notify_t0_signal(signal_card, "601138.SH") is True
    assert notifier.notify_t0_signal(signal_card, "601138.SH") is True
    assert len(sent_messages) == 1
