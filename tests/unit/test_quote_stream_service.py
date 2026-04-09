import json
from datetime import datetime

import src.market_data.streaming.quote_stream_service as quote_stream_service


class FakePubSub:
    def subscribe(self, *_args, **_kwargs):
        return None

    def get_message(self, *_args, **_kwargs):
        return None

    def close(self):
        return None


class FakeRedis:
    def __init__(self):
        self.sets = {}
        self.values = {}
        self.published = []
        self.set_calls = []
        self.setex_calls = []

    def ping(self):
        return True

    def smembers(self, key):
        return self.sets.get(key, set())

    def publish(self, channel, payload):
        self.published.append((channel, json.loads(payload)))

    def setex(self, key, _ttl, value):
        self.setex_calls.append((key, _ttl, value))
        self.values[key] = value

    def set(self, key, value):
        self.set_calls.append((key, value))
        self.values[key] = value

    def pubsub(self, **_kwargs):
        return FakePubSub()


def test_quote_stream_service_reconciles_subscriptions_and_publishes_quotes(monkeypatch):
    subscribed = {}
    unsubscribed = []

    class FakeXtData:
        @staticmethod
        def subscribe_quote(stock_code, period="tick", start_time="", end_time="", count=0, callback=None):
            seq = len(subscribed) + 1
            subscribed[stock_code] = {"seq": seq, "period": period, "callback": callback}
            return seq

        @staticmethod
        def unsubscribe_quote(seq):
            unsubscribed.append(seq)

    fake_redis = FakeRedis()
    fake_redis.sets["quote_subscriptions"] = {"000001.SZ"}

    monkeypatch.setattr(quote_stream_service, "xtdata", FakeXtData())
    monkeypatch.setattr(quote_stream_service.redis, "Redis", lambda **_kwargs: fake_redis)
    monkeypatch.setattr(quote_stream_service.settings, "redis_quote_latest_ttl_seconds", 0)

    service = quote_stream_service.QuoteStreamService()
    service._reconcile_subscriptions()

    assert "000001.SZ" in service._subscription_seq_by_stock
    assert subscribed["000001.SZ"]["period"] == "tick"

    callback = subscribed["000001.SZ"]["callback"]
    callback(
        {
            "000001.SZ": [
                {
                    "time": 20260402123000,
                    "lastPrice": 12.34,
                    "volume": 500,
                }
            ]
        }
    )

    assert fake_redis.published[0][0] == quote_stream_service.settings.redis_quote_stream_channel
    assert fake_redis.published[0][1]["stock_code"] == "000001.SZ"
    assert fake_redis.published[0][1]["last_price"] == 12.34
    assert fake_redis.published[0][1]["quote_time"] == "2026-04-02T12:30:00+08:00"
    assert fake_redis.published[0][1]["published_at"].endswith("+08:00")
    assert fake_redis.published[0][1]["quote"]["time"] == "2026-04-02T12:30:00+08:00"
    assert (
        json.loads(fake_redis.values["quote_latest:000001.SZ"])["volume"] == 500
    )
    assert fake_redis.set_calls and not fake_redis.setex_calls

    fake_redis.sets["quote_subscriptions"] = set()
    service._reconcile_subscriptions()

    assert unsubscribed == [1]
    assert service._subscription_seq_by_stock == {}


def test_normalize_quote_timestamp_value_warns_on_naive_input(monkeypatch):
    warnings = []

    monkeypatch.setattr(
        quote_stream_service.logger,
        "warning",
        lambda message, *args: warnings.append(message.format(*args)),
    )

    normalized = quote_stream_service._normalize_quote_timestamp_value(
        datetime(2026, 4, 2, 13, 30, 1),
        stock_code="000001.SZ",
    )

    assert normalized == "2026-04-02T13:30:01+08:00"
    assert any("assuming Asia/Shanghai" in item for item in warnings)
