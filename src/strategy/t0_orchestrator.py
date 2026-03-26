"""T+0策略编排器 - 协调所有模块执行策略"""

import json
from datetime import date, datetime
from pathlib import Path

from src.config import settings
from src.logger_config import logger
from src.notifications import FeishuNotifier
from src.strategy.core.models import MarketSnapshot, PositionSnapshot, SignalCard, StrategyDecision
from src.strategy.data_fetcher import DataFetcher
from src.strategy.feature_calculator import FeatureCalculator
from src.strategy.position_syncer import PositionSyncer
from src.strategy.regime_identifier import RegimeIdentifier
from src.strategy.signal_generator import SignalGenerator
from src.strategy.signal_state_repository import StrategySignalRepository


class T0Orchestrator:
    """T+0策略编排器"""

    def __init__(self):
        self.stock_code = settings.t0_stock_code
        self.output_dir = Path(settings.t0_output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.data_fetcher = DataFetcher()
        self.regime_identifier = RegimeIdentifier()
        self.feature_calculator = FeatureCalculator()
        self.signal_generator = SignalGenerator()
        self.position_syncer = PositionSyncer()
        self.signal_repository = StrategySignalRepository()
        self.notifier = FeishuNotifier()

    def run_once(self) -> dict:
        """运行一次策略

        Returns:
            信号卡片字典
        """
        try:
            trade_date = date.today()
            logger.info(f"开始执行T+0策略: {self.stock_code}, {trade_date}")

            # 1. 获取数据
            minute_data = self.data_fetcher.fetch_minute_data(self.stock_code, trade_date)
            if minute_data is None:
                return self._finalize_signal_card(self._error_signal_card("分钟数据获取失败"))

            daily_data = self.data_fetcher.fetch_daily_data(self.stock_code, days=100)
            if daily_data is None:
                return self._finalize_signal_card(self._error_signal_card("日线数据获取失败"))

            # 2. 识别regime
            regime = self.regime_identifier.identify_regime(daily_data, trade_date)

            # 3. 计算特征
            features = self.feature_calculator.calculate_snapshot(minute_data)
            if features is None:
                return self._finalize_signal_card(self._error_signal_card("特征计算失败"))

            # 4. 加载仓位
            position = self.position_syncer.load_portfolio_state()

            # 4.1 加载当日已产出的策略信号历史
            signal_history = self.signal_repository.load_today_history(trade_date)

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

            logger.info(f"策略执行完成: {signal.action}")
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
        self._save_signal_card(signal_card)
        self.notifier.notify_t0_signal(signal_card, self.stock_code)
        return signal_card.to_dict() if hasattr(signal_card, "to_dict") else signal_card

    def _error_signal_card(self, error_msg: str) -> dict:
        """生成错误信号卡片"""
        return {
            "trade_date": date.today().strftime("%Y-%m-%d"),
            "as_of_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "regime": "unknown",
            "signal": {"action": "observe", "reason": error_msg, "price": 0, "volume": 0},
            "error": True,
        }
