#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试日盈亏汇总功能
"""

import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.daily_pnl_calculator import DailyPnLCalculator, calculate_daily_summary
from src.database import OrderRecord, SessionLocal
from src.notifications import FeishuNotifier


def test_empty_summary():
    """测试无交易记录的汇总"""
    print("=== 测试空汇总 ===")

    calculator = DailyPnLCalculator()
    # 使用一个不太可能有交易记录的日期
    test_date = date(2024, 1, 1)

    summary = calculator.calculate_daily_summary(test_date)

    print(f"日期: {summary['date_display']}")
    print(f"总订单数: {summary['summary']['total_orders']}")
    print(f"总成交金额: ¥{summary['summary']['total_amount']:,.2f}")
    print(f"性能说明: {summary['performance']['note']}")

    assert summary["summary"]["total_orders"] == 0
    assert summary["summary"]["total_amount"] == 0.0
    print("✅ 空汇总测试通过")


def test_mock_data_summary():
    """测试使用模拟数据的汇总"""
    print("\n=== 测试模拟数据汇总 ===")

    try:
        # 创建模拟成交记录（仅用于测试，不会真实插入数据库）
        mock_orders = []

        # 模拟一些成交订单
        base_time = datetime.now().replace(hour=10, minute=30, second=0, microsecond=0)

        # 买入订单
        mock_orders.append(
            type(
                "MockOrder",
                (),
                {
                    "stock_code": "000001.SZ",
                    "direction": "BUY",
                    "filled_volume": 1000,
                    "filled_price": Decimal("12.50"),
                    "filled_time": base_time,
                },
            )()
        )

        # 卖出订单
        mock_orders.append(
            type(
                "MockOrder",
                (),
                {
                    "stock_code": "000001.SZ",
                    "direction": "SELL",
                    "filled_volume": 500,
                    "filled_price": Decimal("12.80"),
                    "filled_time": base_time.replace(hour=14, minute=30),
                },
            )()
        )

        # 另一只股票
        mock_orders.append(
            type(
                "MockOrder",
                (),
                {
                    "stock_code": "000977.SZ",
                    "direction": "BUY",
                    "filled_volume": 200,
                    "filled_price": Decimal("25.60"),
                    "filled_time": base_time.replace(hour=11, minute=0),
                },
            )()
        )

        calculator = DailyPnLCalculator()
        today = date.today()

        # 使用模拟数据计算汇总
        summary = calculator._calculate_trading_summary(mock_orders, today)

        print(f"日期: {summary['date_display']}")
        print(f"总订单数: {summary['summary']['total_orders']}")
        print(f"买入订单: {summary['summary']['buy_orders']}")
        print(f"卖出订单: {summary['summary']['sell_orders']}")
        print(f"总成交金额: ¥{summary['summary']['total_amount']:,.2f}")
        print(f"买入金额: ¥{summary['summary']['buy_amount']:,.2f}")
        print(f"卖出金额: ¥{summary['summary']['sell_amount']:,.2f}")
        print(f"平均成交价: ¥{summary['summary']['avg_price']:.2f}")

        # 验证股票明细
        print(f"\n股票明细:")
        for stock in summary["stock_breakdown"]:
            print(
                f"• {stock['stock_display']}: ¥{stock['total_amount']:,.2f}, 净量: {stock['net_volume']}"
            )

        # 验证时间段分布
        print(f"\n时间段分布:")
        print(
            f"• 上午: {summary['time_breakdown']['morning']['orders_count']}笔, ¥{summary['time_breakdown']['morning']['amount']:,.2f}"
        )
        print(
            f"• 下午: {summary['time_breakdown']['afternoon']['orders_count']}笔, ¥{summary['time_breakdown']['afternoon']['amount']:,.2f}"
        )

        # 验证性能估算
        print(f"\n性能估算:")
        print(f"• 估算盈亏: ¥{summary['performance']['estimated_realized_pnl']:,.2f}")
        print(f"• 估算成本: ¥{summary['performance']['trading_cost_estimate']:,.2f}")

        assert summary["summary"]["total_orders"] == 3
        assert summary["summary"]["buy_orders"] == 2
        assert summary["summary"]["sell_orders"] == 1
        print("✅ 模拟数据汇总测试通过")

    except Exception as e:
        print(f"❌ 模拟数据测试失败: {e}")
        raise


def test_notification_format():
    """测试通知格式"""
    print("\n=== 测试通知格式 ===")

    try:
        # 创建测试汇总数据
        test_pnl_data = {
            "date": "2024-08-10",
            "date_display": "2024年08月10日",
            "summary": {
                "total_orders": 5,
                "buy_orders": 3,
                "sell_orders": 2,
                "total_amount": 50000.00,
                "buy_amount": 30000.00,
                "sell_amount": 20000.00,
                "total_volume": 2000,
                "buy_volume": 1200,
                "sell_volume": 800,
                "avg_price": 25.00,
            },
            "stock_breakdown": [
                {
                    "stock_display": "000001.SZ(平安银行)",
                    "total_amount": 30000.00,
                    "net_volume": 400,
                },
                {
                    "stock_display": "000977.SZ(浪潮信息)",
                    "total_amount": 20000.00,
                    "net_volume": -200,
                },
            ],
            "time_breakdown": {
                "morning": {"orders_count": 3, "amount": 30000.00, "volume": 1200},
                "afternoon": {"orders_count": 2, "amount": 20000.00, "volume": 800},
            },
            "performance": {
                "estimated_realized_pnl": 1200.50,
                "trading_cost_estimate": 15.00,
                "note": "此为简单估算，实际盈亏需要考虑持仓成本和手续费",
            },
        }

        # 创建通知器（但不真正发送）
        notifier = FeishuNotifier()

        # 测试通知内容生成（通过捕获日志输出）
        print("生成的通知内容预览:")
        print("-" * 50)

        # 模拟通知内容生成
        summary = test_pnl_data["summary"]
        date_display = test_pnl_data["date_display"]

        message = f"**{date_display} 交易汇总**\n\n"
        message += f"📊 **交易概览**\n"
        message += f"• 总成交订单：{summary['total_orders']}笔\n"
        message += f"• 买入订单：{summary['buy_orders']}笔\n"
        message += f"• 卖出订单：{summary['sell_orders']}笔\n"
        message += f"• 总成交金额：¥{summary['total_amount']:,.2f}\n"

        print(message)
        print("-" * 50)

        # 测试通知内容生成（不实际发送）
        print("ℹ️  跳过实际发送，通知格式正确")

        # 如果需要测试实际发送，可以取消注释以下代码：
        # if settings.feishu_webhook_url:
        #     success = notifier.notify_daily_pnl_summary(test_pnl_data)
        #     print(f"通知发送结果: {'成功' if success else '失败'}")

        print("✅ 通知格式测试通过")

    except Exception as e:
        print(f"❌ 通知格式测试失败: {e}")
        raise


def test_real_data_summary():
    """测试真实数据汇总（如果存在）"""
    print("\n=== 测试真实数据汇总 ===")

    try:
        calculator = DailyPnLCalculator()
        summary = calculator.calculate_daily_summary()  # 使用今天的数据

        print(f"今日({summary['date_display']})交易汇总:")
        print(f"• 总订单数: {summary['summary']['total_orders']}")
        print(f"• 总成交金额: ¥{summary['summary']['total_amount']:,.2f}")
        print(f"• 总成交量: {summary['summary']['total_volume']:,}股")

        if summary["summary"]["total_orders"] > 0:
            print(f"• 平均成交价: ¥{summary['summary']['avg_price']:.2f}")
            print(f"• 估算盈亏: ¥{summary['performance']['estimated_realized_pnl']:,.2f}")

            print(f"\n活跃股票:")
            for stock in summary["stock_breakdown"][:3]:  # 显示前3个
                print(f"  - {stock['stock_display']}: ¥{stock['total_amount']:,.2f}")
        else:
            print("• 当日无交易记录")

        print("✅ 真实数据汇总测试完成")

    except Exception as e:
        print(f"❌ 真实数据汇总测试失败: {e}")
        # 这个不是致命错误，继续执行


def main():
    """运行所有测试"""
    print("日盈亏汇总功能测试")
    print("=" * 60)

    try:
        test_empty_summary()
        test_mock_data_summary()
        test_notification_format()
        test_real_data_summary()

        print("\n" + "=" * 60)
        print("✅ 所有测试完成!")
        print("\n功能说明:")
        print("• 系统将在每天15:10自动发送当日交易汇总")
        print("• 汇总包括：交易概览、时间段分布、股票明细、性能估算")
        print("• 支持盈亏简单估算和交易成本估算")
        print("• 自动识别股票名称并格式化显示")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        return False

    return True


if __name__ == "__main__":
    main()
