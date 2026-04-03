"""T+0策略诊断工具 - 显示详细的策略判断过程"""

from datetime import date, datetime
from pathlib import Path

from src.config import settings
from src.logger_config import logger
from src.strategy.core.params import T0StrategyParams
from src.strategy.data_fetcher import DataFetcher
from src.strategy.feature_calculator import FeatureCalculator
from src.strategy.position_syncer import PositionSyncer
from src.strategy.regime_identifier import RegimeIdentifier


class StrategyDiagnostics:
    """策略诊断工具"""

    def __init__(self):
        self.stock_code = settings.t0_stock_code
        self.params = T0StrategyParams.from_settings(settings)
        self.data_fetcher = DataFetcher()
        self.regime_identifier = RegimeIdentifier()
        self.feature_calculator = FeatureCalculator()
        self.position_syncer = PositionSyncer()

    def diagnose(self) -> dict:
        """运行完整诊断并返回详细信息"""
        trade_date = date.today()
        current_time = datetime.now().time()

        print(f"\n{'='*80}")
        print(f"T+0 策略诊断报告 - {self.stock_code}")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")

        # 1. 数据获取
        print("【1. 数据获取】")
        minute_data = self.data_fetcher.fetch_minute_data(
            self.stock_code, trade_date, realtime=True
        )
        if minute_data is None:
            print("  ❌ 分钟数据获取失败")
            return {"error": "分钟数据获取失败"}
        print(f"  ✓ 分钟数据: {len(minute_data)} 条")

        # 显示前几条数据
        print(f"\n  前5条数据:")
        for idx, row in minute_data.head(5).iterrows():
            print(f"    {idx}: open={row.get('open', 0):.2f}, high={row.get('high', 0):.2f}, "
                  f"low={row.get('low', 0):.2f}, close={row.get('close', 0):.2f}")

        # 显示最后几条数据
        print(f"\n  最后5条数据:")
        for idx, row in minute_data.tail(5).iterrows():
            print(f"    {idx}: open={row.get('open', 0):.2f}, high={row.get('high', 0):.2f}, "
                  f"low={row.get('low', 0):.2f}, close={row.get('close', 0):.2f}")

        daily_data = self.data_fetcher.fetch_daily_data(self.stock_code, days=100)
        if daily_data is None:
            print("  ❌ 日线数据获取失败")
            return {"error": "日线数据获取失败"}
        print(f"  ✓ 日线数据: {len(daily_data)} 条\n")

        # 检查数据中是否有零值
        zero_check_fields = ["open", "high", "low"]
        for field in zero_check_fields:
            if field in minute_data.columns:
                zero_count = (minute_data[field] == 0).sum()
                if zero_count > 0:
                    total = len(minute_data)
                    print(f"  ⚠️  {field} 有 {zero_count}/{total} 条为零值")

        # 2. 市场状态
        print("【2. 市场状态】")
        regime = self.regime_identifier.identify_regime(daily_data, trade_date)
        print(f"  Regime: {regime}")
        branch_priority = self._get_branch_priority(regime)
        print(f"  分支优先级: {' > '.join(branch_priority)}\n")

        # 3. 特征计算
        print("【3. 特征计算】")
        features = self.feature_calculator.calculate_snapshot(minute_data)
        if features is None:
            print("  ❌ 特征计算失败")
            return {"error": "特征计算失败"}

        feature_dict = features.to_dict() if hasattr(features, "to_dict") else dict(features)
        day_open = feature_dict.get("day_open", 0)
        current_close = feature_dict.get("current_close", 0)
        high_so_far = feature_dict.get("high_so_far", 0)
        low_so_far = feature_dict.get("low_so_far", 0)
        vwap = feature_dict.get("vwap", 0)
        bounce = feature_dict.get("bounce_from_low", 0)
        close_vs_vwap = feature_dict.get("close_vs_vwap", 0)
        fake_breakout = feature_dict.get("fake_breakout_score", 0)
        absorption = feature_dict.get("absorption_score", 0)

        rise = ((high_so_far - day_open) / day_open * 100) if day_open > 0 else 0
        pullback = ((high_so_far - current_close) / high_so_far * 100) if high_so_far > 0 else 0

        print(f"  开盘价: {day_open:.2f}")
        print(f"  当前价: {current_close:.2f}")
        print(f"  最高价: {high_so_far:.2f}  (涨幅: {rise:.2f}%)")
        print(f"  最低价: {low_so_far:.2f}")
        print(f"  VWAP: {vwap:.2f}  (当前价 vs VWAP: {close_vs_vwap:.2f}%)")
        print(f"  回撤幅度: {pullback:.2f}%")
        print(f"  反弹幅度: {bounce:.2f}%")
        print(f"  假突破分数: {fake_breakout:.2f}")
        print(f"  吸收分数: {absorption:.2f}\n")

        # 4. 仓位状态
        print("【4. 仓位状态】")
        position = self.position_syncer.load_portfolio_state()
        position_dict = position.to_dict() if hasattr(position, "to_dict") else dict(position)

        total_position = position_dict.get("total_position", 0)
        available_volume = position_dict.get("available_volume", 0)
        cost_price = position_dict.get("cost_price", 0)
        base_position = position_dict.get("base_position", self.params.t0_base_position)
        tactical_position = position_dict.get("tactical_position", self.params.t0_tactical_position)
        max_position = position_dict.get("max_position", base_position + tactical_position)
        t0_sell_available = position_dict.get("t0_sell_available", 0)
        t0_buy_capacity = position_dict.get("t0_buy_capacity", 0)

        print(f"  总持仓: {total_position}")
        print(f"  可用数量: {available_volume}")
        print(f"  成本价: {cost_price:.2f}")
        print(f"  基础仓: {base_position}")
        print(f"  机动仓: {tactical_position}")
        print(f"  最大仓位: {max_position}")
        print(f"  T+0可卖: {t0_sell_available}")
        print(f"  T+0可买: {t0_buy_capacity}\n")

        # 5. 时间窗口检查
        print("【5. 时间窗口检查】")
        print(f"  当前时间: {current_time.strftime('%H:%M:%S')}")

        positive_sell_window = self._within_window(
            current_time,
            self.params.t0_positive_sell_start_time,
            self.params.t0_positive_sell_end_time,
        )
        positive_buyback_window = self._within_window(
            current_time,
            self.params.t0_positive_buyback_start_time,
            self.params.t0_positive_buyback_end_time,
        )
        reverse_buy_window = self._within_window(
            current_time,
            self.params.t0_reverse_buy_start_time,
            self.params.t0_reverse_buy_end_time,
        )
        reverse_sell_window = self._within_window(
            current_time,
            self.params.t0_reverse_sell_start_time,
            self.params.t0_reverse_sell_end_time,
        )

        print(
            f"  正T卖出窗口 ({self.params.t0_positive_sell_start_time}-"
            f"{self.params.t0_positive_sell_end_time}): "
            f"{'✓ 在窗口内' if positive_sell_window else '✗ 不在窗口内'}"
        )
        print(
            f"  正T回补窗口 ({self.params.t0_positive_buyback_start_time}-"
            f"{self.params.t0_positive_buyback_end_time}): "
            f"{'✓ 在窗口内' if positive_buyback_window else '✗ 不在窗口内'}"
        )
        print(
            f"  反T买入窗口 ({self.params.t0_reverse_buy_start_time}-"
            f"{self.params.t0_reverse_buy_end_time}): "
            f"{'✓ 在窗口内' if reverse_buy_window else '✗ 不在窗口内'}"
        )
        print(
            f"  反T卖出窗口 ({self.params.t0_reverse_sell_start_time}-"
            f"{self.params.t0_reverse_sell_end_time}): "
            f"{'✓ 在窗口内' if reverse_sell_window else '✗ 不在窗口内'}"
        )
        print()

        # 6. 策略条件检查
        print("【6. 策略条件检查】")

        # 正T卖出条件
        print("  正T卖出条件:")
        print(f"    - 时间窗口: {'✓' if positive_sell_window else '✗'}")
        print(
            f"    - 涨幅 >= {self.params.t0_positive_sell_min_rise}%: "
            f"{'✓' if rise >= self.params.t0_positive_sell_min_rise else '✗'} "
            f"(实际: {rise:.2f}%)"
        )
        print(
            f"    - 回撤 >= {self.params.t0_positive_sell_min_pullback}%: "
            f"{'✓' if pullback >= self.params.t0_positive_sell_min_pullback else '✗'} "
            f"(实际: {pullback:.2f}%)"
        )
        print(
            f"    - 价格 < VWAP: "
            f"{'✓' if current_close < vwap else '✗'} "
            f"(当前: {current_close:.2f}, VWAP: {vwap:.2f})"
        )
        print(f"    - T+0可卖 > 0: {'✓' if t0_sell_available > 0 else '✗'} (实际: {t0_sell_available})")

        # 正T回补条件
        print("\n  正T回补条件:")
        print(f"    - 时间窗口: {'✓' if positive_buyback_window else '✗'}")
        print(
            f"    - 价格 <= VWAP * {1 + self.params.t0_positive_buyback_vwap_discount}: "
            f"{'✓' if current_close <= vwap * (1 + self.params.t0_positive_buyback_vwap_discount) else '✗'} "
            f"(当前: {current_close:.2f}, 阈值: {vwap * (1 + self.params.t0_positive_buyback_vwap_discount):.2f})"
        )
        print(
            f"    - 假突破分数 >= {self.params.t0_positive_buyback_min_fake_breakout}: "
            f"{'✓' if fake_breakout >= self.params.t0_positive_buyback_min_fake_breakout else '✗'} "
            f"(实际: {fake_breakout:.2f})"
        )
        print(f"    - T+0可买 > 0: {'✓' if t0_buy_capacity > 0 else '✗'} (实际: {t0_buy_capacity})")

        # 反T买入条件
        print("\n  反T买入条件:")
        print(f"    - 时间窗口: {'✓' if reverse_buy_window else '✗'}")
        print(
            f"    - 反弹 >= {self.params.t0_reverse_buy_min_bounce}%: "
            f"{'✓' if bounce >= self.params.t0_reverse_buy_min_bounce else '✗'} "
            f"(实际: {bounce:.2f}%)"
        )
        print(
            f"    - 价格 vs VWAP >= -0.5%: "
            f"{'✓' if close_vs_vwap >= -0.5 else '✗'} "
            f"(实际: {close_vs_vwap:.2f}%)"
        )
        print(
            f"    - 吸收分数 >= 0.6: "
            f"{'✓' if absorption >= 0.6 else '✗'} "
            f"(实际: {absorption:.2f})"
        )
        print(f"    - T+0可买 > 0: {'✓' if t0_buy_capacity > 0 else '✗'} (实际: {t0_buy_capacity})")

        # 反T卖出条件
        print("\n  反T卖出条件:")
        print(f"    - 时间窗口: {'✓' if reverse_sell_window else '✗'}")
        profit_pct = ((current_close - cost_price) / cost_price * 100) if cost_price > 0 else 0
        print(
            f"    - 盈利 >= {self.params.t0_reverse_sell_min_profit}%: "
            f"{'✓' if profit_pct >= self.params.t0_reverse_sell_min_profit else '✗'} "
            f"(实际: {profit_pct:.2f}%)"
        )
        print(
            f"    - 价格 >= VWAP: "
            f"{'✓' if current_close >= vwap else '✗'} "
            f"(当前: {current_close:.2f}, VWAP: {vwap:.2f})"
        )
        print(f"    - T+0可卖 > 0: {'✓' if t0_sell_available > 0 else '✗'} (实际: {t0_sell_available})")

        print(f"\n{'='*80}\n")

        return {
            "regime": regime,
            "features": feature_dict,
            "position": position_dict,
            "time_windows": {
                "positive_sell": positive_sell_window,
                "positive_buyback": positive_buyback_window,
                "reverse_buy": reverse_buy_window,
                "reverse_sell": reverse_sell_window,
            },
        }

    def _within_window(self, current_time, start: str, end: str) -> bool:
        return self.params.parse_time(start) <= current_time <= self.params.parse_time(end)

    def _get_branch_priority(self, regime: str) -> list:
        if regime == "downtrend":
            return ["positive_t", "reverse_t"]
        if regime == "uptrend":
            return ["reverse_t"]
        return ["reverse_t", "positive_t"]


if __name__ == "__main__":
    diagnostics = StrategyDiagnostics()
    diagnostics.diagnose()

