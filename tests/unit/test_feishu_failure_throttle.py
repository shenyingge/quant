from src.infrastructure.config import settings
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
        notifier_a.notify_runtime_event("交易引擎", "运行异常", "Redis 连接失败", "error") is True
    )
    assert (
        notifier_b.notify_runtime_event("交易引擎", "运行异常", "Redis 连接失败", "error") is True
    )
    assert len(sent_messages) == 1


def test_notify_error_notifications_are_throttled(monkeypatch):
    sent_messages = []
    FeishuNotifier._failure_notification_cache.clear()
    monkeypatch.setattr(settings, "feishu_failure_notify_cooldown_seconds", 300)
    monkeypatch.setattr(
        FeishuNotifier,
        "send_message",
        lambda self, message, title="交易通知": sent_messages.append((title, message)) or True,
    )

    notifier = FeishuNotifier()

    assert notifier.notify_error("QMT 下单失败", "订单提交通道") is True
    assert notifier.notify_error("QMT 下单失败", "订单提交通道") is True
    assert len(sent_messages) == 1
