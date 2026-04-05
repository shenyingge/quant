from src.infrastructure.notifications import FeishuNotifier
from src.strategy.core.models import MarketSnapshot, PositionSnapshot, SignalCard, StrategyDecision


def test_notify_t0_signal_accepts_typed_signal_card():
    notifier = FeishuNotifier()
    captured = {}

    def fake_send_message(message: str, title: str = "交易通知"):
        captured["message"] = message
        captured["title"] = title
        return True

    notifier.send_message = fake_send_message

    signal_card = SignalCard(
        trade_date="2026-03-26",
        as_of_time="2026-03-26 10:24:01",
        regime="transition",
        position=PositionSnapshot(
            total=3500,
            available=3500,
            cost_price=72.68,
            base=2600,
            tactical=900,
            max=3500,
            t0_sell_available=900,
            t0_buy_capacity=0,
        ),
        market=MarketSnapshot(
            time="2026-03-26 10:24:01",
            price=50.95,
            vwap=50.57,
            high=51.5,
            low=49.85,
        ),
        signal=StrategyDecision(
            action="reverse_t_buy",
            reason="急跌止跌: 反弹2.5%",
            price=51.09,
            volume=900,
            branch="reverse_t",
        ),
        scores={"fake_breakout": 0.3, "absorption": 0.6},
    )

    assert notifier.notify_t0_signal(signal_card, "601138.SH") is True
    assert "reverse_t_buy" in captured["message"]
    assert captured["title"] == "📮 策略引擎交易信号"
