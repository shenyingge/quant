#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易日检查测试脚本
测试xtquant的交易日查询功能
"""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

try:
    from xtquant import xtdata
    print("SUCCESS: xtquant.xtdata module loaded successfully")
    XTDATA_AVAILABLE = True
except ImportError as e:
    print(f"WARNING: Cannot import xtdata module: {e}")
    print("This is expected if xtquant is not installed.")
    print("The trading day check will default to 'True' in production.")
    XTDATA_AVAILABLE = False

def test_trading_day_check():
    """Test trading day check functionality"""
    print("\n" + "="*50)
    print("Trading Day Check Test")
    print("="*50)
    
    if not XTDATA_AVAILABLE:
        print("SKIPPING: xtdata module not available")
        print("In production, this will default to returning True (always trading day)")
        return
    
    try:
        # 下载交易日历数据
        print("\n1. Download trading calendar data...")
        try:
            xtdata.download_holiday_data()
            print("SUCCESS: Trading calendar data downloaded")
        except Exception as e:
            print(f"WARNING: Download trading calendar failed: {str(e)[:100]}")
            print("Continue with existing data...")
        
        # 测试当天
        today = datetime.now()
        today_str = today.strftime('%Y%m%d')
        
        print(f"\n2. 检查今天 ({today_str}) 是否为交易日...")
        
        # 获取当年交易日历
        year = today.year
        start_date = f"{year}0101"
        end_date = f"{year}1231"
        
        print(f"获取 {year} 年交易日历...")
        trading_calendar = xtdata.get_trading_calendar('SH', start_date, end_date)
        
        if trading_calendar is None:
            print("✗ 无法获取交易日历")
            return
        
        print(f"✓ 成功获取交易日历，共 {len(trading_calendar)} 个交易日")
        
        # 检查今天
        is_today_trading = today_str in trading_calendar
        print(f"今天 {today_str} {'是' if is_today_trading else '不是'}交易日")
        
        # 检查最近几天
        print(f"\n3. 检查最近7天的交易日情况:")
        print("-" * 40)
        print("日期\t\t星期\t交易日")
        print("-" * 40)
        
        for i in range(-3, 4):  # 前3天到后3天
            check_date = today + timedelta(days=i)
            check_str = check_date.strftime('%Y%m%d')
            weekday = check_date.strftime('%A')
            is_trading = check_str in trading_calendar
            
            marker = "🟢" if is_trading else "🔴"
            status = "是" if is_trading else "否"
            print(f"{check_str}\t{weekday[:3]}\t{marker} {status}")
        
        # 显示本月交易日统计
        print(f"\n4. {year}年{today.month}月交易日统计:")
        month_start = f"{year}{today.month:02d}01"
        if today.month == 12:
            month_end = f"{year}{today.month:02d}31"
        else:
            month_end = f"{year}{today.month+1:02d}01"
        
        month_trading_days = [d for d in trading_calendar if month_start <= d < month_end]
        print(f"✓ 本月共有 {len(month_trading_days)} 个交易日")
        
        # 显示最近的几个交易日
        print(f"\n5. 最近的5个交易日:")
        recent_days = [d for d in trading_calendar if d <= today_str][-5:]
        for day in recent_days:
            marker = "👆" if day == today_str else "  "
            print(f"  {marker} {day}")
        
        print(f"\n6. 接下来的5个交易日:")
        future_days = [d for d in trading_calendar if d > today_str][:5]
        for day in future_days:
            print(f"   {day}")
            
    except Exception as e:
        print(f"✗ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

def test_trading_day_function(check_date=None):
    """Simulate the trading day check function from Windows service"""
    print(f"\nTesting Trading Day Check Function (Simulating Windows Service):")
    print("-" * 50)
    
    if not XTDATA_AVAILABLE:
        print("xtdata module not available, returning default: True")
        return True
    
    try:
        if check_date is None:
            check_date = datetime.now().strftime('%Y%m%d')
        else:
            check_date = check_date.strftime('%Y%m%d')

        print(f"正在检查 {check_date} 是否为交易日...")

        # 下载交易日历数据（如果需要）
        try:
            xtdata.download_holiday_data()
            print("交易日历数据已更新")
        except Exception as e:
            print(f"下载交易日历数据失败: {e}，使用已有数据")

        # 获取当年的交易日历
        year = check_date[:4]
        start_date = f"{year}0101"
        end_date = f"{year}1231"
        
        # 获取上海市场的交易日历（作为A股市场标准）
        trading_calendar = xtdata.get_trading_calendar('SH', start_date, end_date)
        
        if trading_calendar is None:
            print("无法获取交易日历，默认为交易日")
            return True

        # 检查当前日期是否在交易日列表中
        is_trading_day = check_date in trading_calendar
        
        status_msg = f"{check_date} {'是' if is_trading_day else '不是'}交易日"
        print(status_msg)
        
        return is_trading_day

    except Exception as e:
        print(f"检查交易日时发生异常: {e}，默认为交易日")
        return True

if __name__ == "__main__":
    print("交易日检查测试脚本")
    print("测试xtquant交易日历功能")
    
    # 基础功能测试
    test_trading_day_check()
    
    # 函数测试
    result = test_trading_day_function()
    print(f"\n最终结果: {'今天是交易日' if result else '今天不是交易日'}")
    
    print(f"\n{'='*50}")
    print("测试完成")