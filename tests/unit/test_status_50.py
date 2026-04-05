#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
调试状态 50 的分类问题
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from xtquant import xtconstant

from src.trading.qmt_constants import (
    OrderStatus,
    get_status_name,
    is_filled_status,
    is_finished_status,
    is_pending_status,
)


def debug_status_50():
    """调试状态 50"""
    print("=== 调试状态 50 ===")

    status_50 = 50

    print(f"状态码: {status_50}")
    print(f"状态名称: {get_status_name(status_50)}")
    print(f"xtconstant.ORDER_REPORTED: {xtconstant.ORDER_REPORTED}")

    print(f"\n状态分类检查:")
    print(f"是成交状态: {is_filled_status(status_50)}")
    print(f"是完成状态: {is_finished_status(status_50)}")
    print(f"是待处理状态: {is_pending_status(status_50)}")

    print(f"\n各类状态代码:")
    print(f"成交状态代码: {OrderStatus.get_filled_status_codes()}")
    print(f"完成状态代码: {OrderStatus.get_finished_status_codes()}")
    print(f"待处理状态代码: {OrderStatus.get_pending_status_codes()}")

    print(f"\n验证 50 是否在各列表中:")
    print(f"50 in 成交状态: {50 in OrderStatus.get_filled_status_codes()}")
    print(f"50 in 完成状态: {50 in OrderStatus.get_finished_status_codes()}")
    print(f"50 in 待处理状态: {50 in OrderStatus.get_pending_status_codes()}")


if __name__ == "__main__":
    debug_status_50()
