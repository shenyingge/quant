#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查 xtconstant 中的枚举常量
"""

try:
    from xtquant import xtconstant
    
    print("=== 订单状态相关常量 ===")
    order_constants = [attr for attr in dir(xtconstant) if 'ORDER' in attr]
    for const in order_constants:
        value = getattr(xtconstant, const)
        print(f"{const}: {value}")
    
    print("\n=== 市场相关常量 ===")
    market_constants = [attr for attr in dir(xtconstant) if 'MARKET' in attr][:10]  # 只显示前10个
    for const in market_constants:
        value = getattr(xtconstant, const)
        print(f"{const}: {value}")
    
    print("\n=== 账户类型常量 ===")  
    account_constants = [attr for attr in dir(xtconstant) if 'ACCOUNT' in attr]
    for const in account_constants:
        value = getattr(xtconstant, const)
        print(f"{const}: {value}")
        
    print("\n=== 操作类型常量 ===")
    opt_constants = [attr for attr in dir(xtconstant) if attr.startswith('OPT_') and ('BUY' in attr or 'SELL' in attr)][:10]
    for const in opt_constants:
        value = getattr(xtconstant, const)
        print(f"{const}: {value}")
        
    print("\n=== 价格类型常量 ===")
    price_constants = [attr for attr in dir(xtconstant) if 'PRTP_' in attr]
    for const in price_constants:
        value = getattr(xtconstant, const)
        print(f"{const}: {value}")

except Exception as e:
    print(f"检查失败: {e}")