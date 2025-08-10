#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
手动触发发送当日盈亏汇总通知
用于测试通知功能
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.daily_pnl_calculator import calculate_daily_summary
from src.logger_config import configured_logger as logger
from src.notifications import FeishuNotifier


def main():
    """手动发送当日盈亏汇总通知"""
    print("手动发送当日盈亏汇总通知")
    print("=" * 50)

    try:
        # 计算当日交易汇总
        logger.info("开始计算当日盈亏汇总...")
        pnl_data = calculate_daily_summary()

        if not pnl_data:
            print("❌ 无法生成盈亏汇总数据")
            return False

        print(f"✅ 成功生成 {pnl_data['date_display']} 的交易汇总")
        print(f"• 总成交订单：{pnl_data['summary']['total_orders']}笔")
        print(f"• 总成交金额：¥{pnl_data['summary']['total_amount']:,.2f}")

        # 创建通知器并发送
        notifier = FeishuNotifier()

        print("\n正在发送飞书通知...")
        success = notifier.notify_daily_pnl_summary(pnl_data)

        if success:
            print("✅ 盈亏汇总通知发送成功！")
            logger.info("手动触发的盈亏汇总通知发送成功")
            return True
        else:
            print("❌ 盈亏汇总通知发送失败")
            logger.error("手动触发的盈亏汇总通知发送失败")
            return False

    except Exception as e:
        print(f"❌ 发送通知时发生错误: {e}")
        logger.error(f"手动发送盈亏汇总通知失败: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
