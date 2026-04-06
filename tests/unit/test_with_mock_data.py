"""使用模拟数据测试T+0策略逻辑"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.test_mock_data_generator import MockDataGenerator

from src.infrastructure.logger_config import logger


def test_with_mock_data():
    """使用模拟数据测试策略"""
    logger.info("=" * 60)
    logger.info("使用模拟数据测试T+0策略逻辑")
    logger.info("=" * 60)

    generator = MockDataGenerator()

    # 测试1: Regime识别
    logger.info("\n测试1: Regime识别")
    test_regime_identification(generator)

    # 测试2: 特征计算
    logger.info("\n测试2: 特征计算")
    test_feature_calculation(generator)

    # 测试3: 信号生成 - 假突破场景
    logger.info("\n测试3: 信号生成 - 假突破场景")
    test_signal_generation(generator, "fake_breakout")

    # 测试4: 信号生成 - 承接场景
    logger.info("\n测试4: 信号生成 - 承接场景")
    test_signal_generation(generator, "absorption")

    logger.info("\n" + "=" * 60)
    logger.info("所有测试完成！")


def test_regime_identification(generator):
    """测试regime识别"""
    try:
        from src.strategy.strategies.t0.regime_identifier import RegimeIdentifier

        # 生成日线数据
        daily_data = generator.generate_daily_data(days=100, base_price=12.0)
        logger.info(f"生成日线数据: {len(daily_data)}天")

        # 识别regime
        identifier = RegimeIdentifier()
        regime = identifier.identify_regime(daily_data, date.today())

        logger.info(f"✓ Regime识别成功: {regime}")
        logger.info(f"  最新收盘价: {daily_data.iloc[-1]['close']:.2f}")

        return True
    except Exception as e:
        logger.error(f"✗ Regime识别失败: {e}")
        return False


def test_feature_calculation(generator):
    """测试特征计算"""
    try:
        from src.strategy.strategies.t0.feature_calculator import FeatureCalculator

        # 生成分钟数据
        minute_data = generator.generate_minute_data("normal", base_price=12.0)
        logger.info(f"生成分钟数据: {len(minute_data)}条")

        # 计算特征
        calculator = FeatureCalculator()
        features = calculator.calculate_features(minute_data)

        if features:
            logger.info(f"✓ 特征计算成功:")
            logger.info(f"  当前价格: {features['current_close']:.2f}")
            logger.info(f"  VWAP: {features['vwap']:.2f}")
            logger.info(f"  日内高点: {features['high_so_far']:.2f}")
            logger.info(f"  日内低点: {features['low_so_far']:.2f}")
            logger.info(f"  假突破评分: {features['fake_breakout_score']:.2f}")
            logger.info(f"  承接评分: {features['absorption_score']:.2f}")
            return True
        else:
            logger.error("✗ 特征计算返回None")
            return False
    except Exception as e:
        logger.error(f"✗ 特征计算失败: {e}")
        return False


def test_signal_generation(generator, scenario):
    """测试信号生成"""
    try:
        from src.strategy.strategies.t0.feature_calculator import FeatureCalculator
        from src.strategy.strategies.t0.signal_generator import SignalGenerator

        # 生成对应场景的分钟数据
        minute_data = generator.generate_minute_data(scenario, base_price=12.0)
        logger.info(f"生成{scenario}场景分钟数据: {len(minute_data)}条")

        # 计算特征
        calculator = FeatureCalculator()
        features = calculator.calculate_features(minute_data)

        if not features:
            logger.error("✗ 特征计算失败")
            return False

        # 生成信号
        signal_gen = SignalGenerator()
        position = {"total_position": 3100, "available_volume": 900}

        # 根据场景设置regime
        regime = "downtrend" if scenario == "fake_breakout" else "uptrend"

        signal = signal_gen.generate_signal(regime, features, position, date.today())

        logger.info(f"✓ 信号生成成功:")
        logger.info(f"  Regime: {regime}")
        logger.info(f"  信号动作: {signal['action']}")
        logger.info(f"  信号原因: {signal['reason']}")
        if signal["action"] != "observe":
            logger.info(f"  建议价格: {signal['price']:.2f}")
            logger.info(f"  建议数量: {signal['volume']}")

        return True
    except Exception as e:
        logger.error(f"✗ 信号生成失败: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_with_mock_data()
