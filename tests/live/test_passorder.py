"""
测试passorder下单功能
"""

import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.live_qmt

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger

from src.trading.execution.qmt_trader import QMTTrader


def test_passorder_functionality():
    """测试passorder下单功能"""
    print("开始测试passorder下单功能...")

    # 创建交易对象
    trader = QMTTrader()

    # 连接QMT
    if not trader.connect():
        print("× QMT连接失败，无法进行测试")
        return False

    print("√ QMT连接成功")

    # 测试信号数据
    test_signals = [
        {
            "signal_id": f"TEST_PASSORDER_{int(time.time())}",
            "stock_code": "000001",  # 平安银行（深圳）
            "direction": "BUY",
            "volume": 100,
            "price": 10.50,
        },
        {
            "signal_id": f"TEST_PASSORDER_{int(time.time())}_2",
            "stock_code": "600000",  # 浦发银行（上海）
            "direction": "BUY",
            "volume": 100,
            "price": 8.50,
        },
    ]

    success_count = 0

    for i, signal in enumerate(test_signals, 1):
        print(f"\n--- 测试信号 {i} ---")
        print(f"股票代码: {signal['stock_code']}")
        print(f"交易方向: {signal['direction']}")
        print(f"数量: {signal['volume']}")
        print(f"价格: {signal['price']}")

        try:
            # 测试同步下单
            print("尝试同步下单...")
            order_id = trader.place_order(signal)

            if order_id:
                print(f"√ 同步下单成功，委托编号: {order_id}")
                success_count += 1

                # 等待一下，然后查询订单状态
                time.sleep(2)
                order_status = trader.get_order_status(order_id)
                if order_status:
                    print(f"订单状态: {order_status}")

                # 测试撤单功能
                print(f"尝试撤销订单 {order_id}...")
                if trader.cancel_order(order_id):
                    print(f"√ 撤单成功")
                else:
                    print(f"× 撤单失败")

            else:
                print(f"× 同步下单失败")

        except Exception as e:
            print(f"× 测试异常: {e}")

        # 测试间隔
        if i < len(test_signals):
            time.sleep(3)

    # 测试异步下单
    print(f"\n--- 测试异步下单 ---")
    async_test_signal = {
        "signal_id": f"ASYNC_TEST_{int(time.time())}",
        "stock_code": "000002",  # 万科A
        "direction": "BUY",
        "volume": 100,
        "price": 15.20,
    }

    def async_callback(order_id, error):
        if order_id:
            print(f"√ 异步下单成功，委托编号: {order_id}")
            # 异步撤单测试
            time.sleep(1)
            if trader.cancel_order(order_id):
                print(f"√ 异步订单撤单成功")
        else:
            print(f"× 异步下单失败: {error}")

    print("提交异步下单任务...")
    trader.place_order_async(async_test_signal, async_callback)

    # 等待异步任务完成
    time.sleep(5)

    # 获取交易统计信息
    print(f"\n--- 交易统计 ---")
    stats = trader.get_trading_stats()
    print(f"总委托数: {stats['total_orders']}")
    print(f"成功委托数: {stats['successful_orders']}")
    print(f"失败委托数: {stats['failed_orders']}")
    print(f"超时委托数: {stats['timeout_orders']}")
    print(f"成功率: {stats['success_rate']:.1f}%")

    # 获取队列状态
    queue_status = trader.get_queue_status()
    print(f"队列状态: {queue_status}")

    # 获取待处理订单信息
    pending_orders = trader.get_pending_orders_info()
    if pending_orders:
        print(f"待处理订单数: {len(pending_orders)}")
        for order in pending_orders:
            print(
                f"  订单 {order['order_id']}: {order['stock_code']} {order['direction']} {order['volume']}股"
            )
    else:
        print("无待处理订单")

    # 断开连接
    trader.disconnect()
    print(f"\n测试完成，成功测试 {success_count}/{len(test_signals)} 个信号")

    return success_count > 0


def test_market_detection():
    """测试市场检测逻辑"""
    print("\n--- 测试市场检测 ---")

    test_codes = [
        ("600000", "SH"),  # 上海股票
        ("600001", "SH"),  # 上海股票
        ("000001", "SZ"),  # 深圳股票
        ("000002", "SZ"),  # 深圳股票
        ("300001", "SZ"),  # 创业板
        ("002001", "SZ"),  # 中小板
    ]

    for code, expected_market in test_codes:
        # 模拟市场检测逻辑
        if code.startswith("6"):
            detected_market = "SH"
        elif code.startswith(("0", "3")):
            detected_market = "SZ"
        else:
            detected_market = "SH" if len(code) == 6 and code.startswith("6") else "SZ"

        status = "√" if detected_market == expected_market else "×"
        print(f"{status} {code}: 期望={expected_market}, 检测={detected_market}")


def main():
    """主函数"""
    if len(sys.argv) > 1 and sys.argv[1] == "--market-only":
        # 仅测试市场检测
        test_market_detection()
        return

    print("QMT PassOrder 功能测试")
    print("=" * 50)
    print("注意: 此测试会尝试真实下单操作")
    print("请确保:")
    print("1. QMT已启动并登录")
    print("2. 账户有足够资金")
    print("3. 测试股票代码正确")
    print("4. 在交易时间内进行测试")

    confirm = input("\n确认继续测试? (y/N): ").strip().lower()
    if confirm != "y":
        print("测试已取消")
        return

    # 测试市场检测
    test_market_detection()

    # 测试passorder功能
    try:
        success = test_passorder_functionality()
        if success:
            print("\n√ PassOrder功能测试通过")
        else:
            print("\n× PassOrder功能测试失败")
    except Exception as e:
        print(f"\n× 测试过程中发生异常: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
