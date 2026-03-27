"""T+0策略系统测试脚本"""

import sys
from datetime import date
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.logger_config import logger


def test_data_fetcher():
    """测试数据获取"""
    logger.info("=" * 50)
    logger.info("测试1: 数据获取模块")
    try:
        from src.strategy.data_fetcher import DataFetcher

        fetcher = DataFetcher()

        # 测试日线数据
        daily_data = fetcher.fetch_daily_data("601138.SH", days=100)
        if daily_data is not None:
            logger.info(f"✓ 日线数据获取成功: {len(daily_data)}天")
        else:
            logger.error("✗ 日线数据获取失败")
            return False

        # 测试分钟数据
        minute_data = fetcher.fetch_minute_data("601138.SH", date.today())
        if minute_data is not None:
            logger.info(f"✓ 分钟数据获取成功: {len(minute_data)}条")
        else:
            logger.warning("⚠ 分钟数据获取失败(可能非交易时间)")

        return True
    except Exception as e:
        logger.error(f"✗ 数据获取测试失败: {e}")
        return False


def test_regime_identifier():
    """测试regime识别"""
    logger.info("=" * 50)
    logger.info("测试2: Regime识别模块")
    try:
        from src.strategy.data_fetcher import DataFetcher
        from src.strategy.regime_identifier import RegimeIdentifier

        fetcher = DataFetcher()
        identifier = RegimeIdentifier()

        daily_data = fetcher.fetch_daily_data("601138.SH", days=100)
        if daily_data is None:
            logger.error("✗ 无法获取日线数据")
            return False

        regime = identifier.identify_regime(daily_data, date.today())
        logger.info(f"✓ Regime识别成功: {regime}")
        return True
    except Exception as e:
        logger.error(f"✗ Regime识别测试失败: {e}")
        return False


def test_feature_calculator():
    """测试特征计算"""
    logger.info("=" * 50)
    logger.info("测试3: 特征计算模块")
    try:
        from src.strategy.data_fetcher import DataFetcher
        from src.strategy.feature_calculator import FeatureCalculator

        fetcher = DataFetcher()
        calculator = FeatureCalculator()

        minute_data = fetcher.fetch_minute_data("601138.SH", date.today())
        if minute_data is None:
            logger.warning("⚠ 无法获取分钟数据(可能非交易时间)")
            return True

        features = calculator.calculate_features(minute_data)
        if features:
            logger.info(f"✓ 特征计算成功:")
            logger.info(f"  VWAP: {features['vwap']:.2f}")
            logger.info(f"  假突破评分: {features['fake_breakout_score']:.2f}")
            logger.info(f"  承接评分: {features['absorption_score']:.2f}")
            return True
        else:
            logger.error("✗ 特征计算失败")
            return False
    except Exception as e:
        logger.error(f"✗ 特征计算测试失败: {e}")
        return False


def test_orchestrator():
    """测试完整流程"""
    logger.info("=" * 50)
    logger.info("测试4: 完整策略流程")
    try:
        from src.strategy.strategy_engine import StrategyEngine

        strategy_engine = StrategyEngine()
        signal_card = strategy_engine.run_once()

        if signal_card:
            logger.info(f"✓ 策略执行成功:")
            logger.info(f"  信号: {signal_card['signal']['action']}")
            logger.info(f"  原因: {signal_card['signal']['reason']}")
            logger.info(f"  输出文件: output/live_signal_card.json")
            return True
        else:
            logger.error("✗ 策略执行失败")
            return False
    except Exception as e:
        logger.error(f"✗ 策略执行测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    logger.info("开始T+0策略系统测试")
    logger.info("")

    results = []

    # 测试1: 数据获取
    results.append(("数据获取", test_data_fetcher()))

    # 测试2: Regime识别
    results.append(("Regime识别", test_regime_identifier()))

    # 测试3: 特征计算
    results.append(("特征计算", test_feature_calculator()))

    # 测试4: 完整流程
    results.append(("完整流程", test_orchestrator()))

    # 汇总结果
    logger.info("")
    logger.info("=" * 50)
    logger.info("测试结果汇总:")
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        logger.info(f"  {name}: {status}")

    passed = sum(1 for _, r in results if r)
    total = len(results)
    logger.info(f"\n总计: {passed}/{total} 通过")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
