"""Strategy engine for coordinating T+0 runtime evaluation."""

import json
import time
from datetime import date, datetime
from pathlib import Path

import redis

from src.infrastructure.config import settings
from src.infrastructure.logger_config import logger
from src.market_data.ingestion.qmt_snapshot_provider import QMTSnapshotProvider
from src.infrastructure.notifications import FeishuNotifier
from src.strategy.core.models import MarketSnapshot, PositionSnapshot, SignalCard, StrategyDecision
from src.strategy.data_fetcher import DataFetcher
from src.strategy.feature_calculator import FeatureCalculator
from src.strategy.position_syncer import PositionSyncer
from src.strategy.regime_identifier import RegimeIdentifier
from src.strategy.signal_generator import SignalGenerator
from src.strategy.signal_state_repository import StrategySignalRepository

try:
    from xtquant import xtdata
except ImportError:
    xtdata = None


def build_market_data_provider():
    if not settings.t0_market_data_provider_enabled:
        return None
    if xtdata is None:
        logger.warning("xtdata unavailable, market snapshot provider disabled")
        return None
    return QMTSnapshotProvider(xtdata_client=xtdata)


class StrategyEngine:
    """Runtime strategy engine."""

    def __init__(self):
        self.stock_code = settings.t0_stock_code
        self.output_dir = Path(settings.t0_output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.market_data_provider = build_market_data_provider()
        self.data_fetcher = DataFetcher(market_data_provider=self.market_data_provider)
        if self.market_data_provider is not None:
            interval_seconds = min(
                3,
                max(1, int(settings.t0_market_data_snapshot_interval_seconds)),
            )
            self.market_data_provider.subscribe_snapshot(
                stock_codes=[self.stock_code],
                interval_seconds=interval_seconds,
                callback=self._on_market_snapshot,
            )
        self.regime_identifier = RegimeIdentifier()
        self.feature_calculator = FeatureCalculator()
        self.signal_generator = SignalGenerator()
        self.position_syncer = PositionSyncer()
        self.signal_repository = StrategySignalRepository()
        self.notifier = FeishuNotifier()
        self._last_notified_action = None

        try:
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password,
                db=0,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            self.redis_client.ping()
            self.redis_enabled = True
            logger.info("Redis 信号发布已连接")
        except Exception as e:
            logger.warning(f"Redis 信号发布连接失败: {e}")
            self.redis_client = None
            self.redis_enabled = False

    def _on_market_snapshot(self, snapshot) -> None:
        return None

    def run_once(self) -> dict:
        """运行一次策略

        Returns:
            信号卡片字典
        """
        start_time = time.time()
        try:
            trade_date = date.today()
            self.position_syncer.publish_pending_events(limit=20)
            logger.debug(f"开始执行策略引擎: {self.stock_code}, {trade_date}")

            # 1. 获取数据 (realtime模式跳过download_history_data)
            minute_data = self.data_fetcher.fetch_minute_data(
                self.stock_code, trade_date, realtime=True
            )
            if minute_data is None:
                return self._finalize_signal_card(self._error_signal_card("分钟数据获取失败"))

            daily_data = self.data_fetcher.fetch_daily_data(self.stock_code, days=100)
            if daily_data is None:
                return self._finalize_signal_card(self._error_signal_card("日线数据获取失败"))

            # 2. 识别regime
            regime = self.regime_identifier.identify_regime(daily_data, trade_date)
            logger.debug(f"市场状态: regime={regime}")

            # 3. 计算特征
            features = self.feature_calculator.calculate_snapshot(minute_data)
            if features is None:
                return self._finalize_signal_card(self._error_signal_card("特征计算失败"))

            # 记录关键特征
            feature_dict = features.to_dict() if hasattr(features, "to_dict") else dict(features)
            logger.debug(
                f"特征计算: price={feature_dict.get('current_close', 0):.2f}, "
                f"vwap={feature_dict.get('vwap', 0):.2f}, "
                f"high={feature_dict.get('high_so_far', 0):.2f}, "
                f"low={feature_dict.get('low_so_far', 0):.2f}, "
                f"bounce={feature_dict.get('bounce_from_low', 0):.2f}%, "
                f"fake_breakout={feature_dict.get('fake_breakout_score', 0):.2f}, "
                f"absorption={feature_dict.get('absorption_score', 0):.2f}"
            )

            # 4. 加载仓位
            position_state = self.position_syncer.load_position()
            position = self.position_syncer.to_portfolio_state(position_state)
            position_dict = position.to_dict() if hasattr(position, "to_dict") else dict(position)
            logger.debug(
                f"仓位状态: total={position_dict.get('total_position', 0)}, "
                f"available={position_dict.get('available_volume', 0)}, "
                f"t0_sell_avail={position_dict.get('t0_sell_available', 0)}, "
                f"t0_buy_capacity={position_dict.get('t0_buy_capacity', 0)}, "
                f"cost={position_dict.get('cost_price', 0):.2f}, "
                f"version={position_dict.get('position_version', 0)}"
            )

            # 4.1 加载当日已产出的策略信号历史
            signal_history = self.signal_repository.load_today_history(trade_date)
            if signal_history:
                logger.debug(
                    f"今日信号历史: {len(signal_history)}条, "
                    f"actions={[s.action for s in signal_history]}"
                )
            else:
                logger.debug("今日信号历史: 无")

            # 4.2 获取实时快照，补齐最新市场信息
            snapshot = self.data_fetcher.fetch_realtime_snapshot(self.stock_code)

            # 5. 生成信号
            signal = self.signal_generator.generate_signal(
                regime, features, position, trade_date, signal_history=signal_history
            )

            # 6. 构造信号卡片
            signal_card = self._build_signal_card(
                trade_date, regime, features, position, signal, snapshot
            )

            # 7. 保存信号历史
            if signal.action != "observe":
                self.signal_repository.save_signal(
                    trade_date=trade_date,
                    regime=regime,
                    stock_code=self.stock_code,
                    signal=signal,
                )

            elapsed = time.time() - start_time

            # 只在有实际信号时输出详细日志
            if signal.action != "observe":
                logger.info(
                    f"🔔 策略信号: action={signal.action}, reason={signal.reason}, "
                    f"price={signal.price:.2f}, volume={signal.volume}, "
                    f"branch={signal.branch}, 耗时={elapsed:.2f}秒"
                )
            else:
                logger.debug(
                    f"策略执行: action={signal.action}, reason={signal.reason}, 耗时={elapsed:.2f}秒"
                )

            return self._finalize_signal_card(signal_card)

        except Exception as e:
            logger.error(f"策略执行异常: {e}", exc_info=True)
            return self._finalize_signal_card(self._error_signal_card(f"系统异常: {str(e)}"))

    def _build_signal_card(
        self,
        trade_date: date,
        regime: str,
        features,
        position,
        signal,
        snapshot: dict = None,
    ) -> dict:
        """构造信号卡片"""
        feature_dict = features.to_dict() if hasattr(features, "to_dict") else dict(features)
        position_dict = position.to_dict() if hasattr(position, "to_dict") else dict(position)

        market = MarketSnapshot(
            time=feature_dict["latest_bar_time"],
            price=feature_dict["current_close"],
            vwap=feature_dict["vwap"],
            high=feature_dict["high_so_far"],
            low=feature_dict["low_so_far"],
        )

        if snapshot:
            market = MarketSnapshot(
                time=snapshot.get("time") or market.time,
                price=snapshot.get("price") if snapshot.get("price") is not None else market.price,
                vwap=market.vwap,
                high=snapshot.get("high") if snapshot.get("high") is not None else market.high,
                low=snapshot.get("low") if snapshot.get("low") is not None else market.low,
            )

        signal_dict = signal.to_dict() if hasattr(signal, "to_dict") else dict(signal)

        card = SignalCard(
            trade_date=trade_date.strftime("%Y-%m-%d"),
            as_of_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            regime=regime,
            position=PositionSnapshot(
                total=position_dict.get("total_position", 0),
                available=position_dict.get("available_volume", 0),
                cost_price=position_dict.get("cost_price", 0),
                base=position_dict.get("base_position", settings.t0_base_position),
                tactical=position_dict.get("tactical_position", settings.t0_tactical_position),
                max=position_dict.get(
                    "max_position",
                    settings.t0_base_position + settings.t0_tactical_position,
                ),
                t0_sell_available=position_dict.get("t0_sell_available", 0),
                t0_buy_capacity=position_dict.get("t0_buy_capacity", 0),
                position_version=position_dict.get("position_version", 0),
            ),
            market=market,
            signal=StrategyDecision(
                action=signal_dict["action"],
                reason=signal_dict["reason"],
                price=signal_dict["price"],
                volume=signal_dict["volume"],
                branch=signal_dict.get("branch"),
            ),
            scores={
                "fake_breakout": feature_dict["fake_breakout_score"],
                "absorption": feature_dict["absorption_score"],
            },
        )
        return card

    def _save_signal_card(self, signal_card: dict):
        """保存信号卡片到JSON文件"""
        try:
            output_file = self.output_dir / "live_signal_card.json"
            payload = signal_card.to_dict() if hasattr(signal_card, "to_dict") else signal_card
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.info(f"信号卡片已保存: {output_file}")
        except Exception as e:
            logger.error(f"保存信号卡片失败: {e}")

    def _finalize_signal_card(self, signal_card: dict) -> dict:
        """Persist and notify after a signal card is generated."""
        signal_dict = signal_card.to_dict() if hasattr(signal_card, "to_dict") else signal_card

        # 写入 Redis
        if self.redis_enabled:
            try:
                self.redis_client.setex(
                    settings.redis_t0_signal_key,
                    settings.redis_t0_signal_ttl,
                    json.dumps(signal_dict, ensure_ascii=False),
                )
                logger.debug(f"信号卡片已写入 Redis: {settings.redis_t0_signal_key}")
            except Exception as e:
                logger.warning(f"信号卡片写入 Redis 失败: {e}")

        # 可选：写入本地文件（调试用）
        if settings.t0_save_signal_card:
            self._save_signal_card(signal_card)

        # 飞书通知
        current_action = signal_dict.get("signal", {}).get("action")
        if current_action != "observe" or current_action != self._last_notified_action:
            self.notifier.notify_t0_signal(signal_card, self.stock_code)
            self._last_notified_action = current_action

        return signal_dict

    def _error_signal_card(self, error_msg: str) -> dict:
        """生成错误信号卡片"""
        return {
            "trade_date": date.today().strftime("%Y-%m-%d"),
            "as_of_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "regime": "unknown",
            "signal": {"action": "observe", "reason": error_msg, "price": 0, "volume": 0},
            "error": True,
        }
