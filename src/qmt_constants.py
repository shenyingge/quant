#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
QMT 常量定义和映射
基于 xtconstant 的枚举常量，避免硬编码字符串
"""

try:
    from xtquant import xtconstant
except ImportError:
    # 如果没有安装 xtquant，使用默认值
    class xtconstant:
        ORDER_REPORTED = 50
        ORDER_SUCCEEDED = 56
        ORDER_CANCELED = 54
        ORDER_PART_SUCC = 55
        ORDER_PART_CANCEL = 53
        ORDER_JUNK = 57
        ORDER_UNKNOWN = 255
        ORDER_UNREPORTED = 48
        ORDER_WAIT_REPORTING = 49

        STOCK_BUY = 23
        STOCK_SELL = 24

        PRTP_LATEST = 5
        PRTP_MARKET = 12
        PRTP_FIX = 11


# QMT 订单状态映射：中文状态 <-> 数值常量
ORDER_STATUS_MAP = {
    # 中文状态 -> 数值常量
    "未报": xtconstant.ORDER_UNREPORTED,
    "待报": xtconstant.ORDER_WAIT_REPORTING,
    "已报": xtconstant.ORDER_REPORTED,
    "已成交": xtconstant.ORDER_SUCCEEDED,
    "已撤销": xtconstant.ORDER_CANCELED,
    "部分成交": xtconstant.ORDER_PART_SUCC,
    "部分撤销": xtconstant.ORDER_PART_CANCEL,
    "废单": xtconstant.ORDER_JUNK,
    "未知": xtconstant.ORDER_UNKNOWN,
    "已确认": xtconstant.ORDER_REPORTED,  # 已确认通常等同于已报
}

# 反向映射：数值常量 -> 中文状态
STATUS_CODE_MAP = {v: k for k, v in ORDER_STATUS_MAP.items()}


# 定义不同状态类别
class OrderStatus:
    """订单状态常量"""

    # 未报状态
    UNREPORTED = xtconstant.ORDER_UNREPORTED
    WAIT_REPORTING = xtconstant.ORDER_WAIT_REPORTING

    # 已报但未成交
    REPORTED = xtconstant.ORDER_REPORTED

    # 成交状态
    SUCCEEDED = xtconstant.ORDER_SUCCEEDED
    PART_SUCCEEDED = xtconstant.ORDER_PART_SUCC

    # 取消状态
    CANCELED = xtconstant.ORDER_CANCELED
    PART_CANCELED = xtconstant.ORDER_PART_CANCEL
    REJECTED = xtconstant.ORDER_JUNK

    # 未知状态
    UNKNOWN = xtconstant.ORDER_UNKNOWN

    @classmethod
    def get_filled_statuses(cls):
        """获取表示成交的状态列表（中文）"""
        return ["已成交", "部分成交"]

    @classmethod
    def get_filled_status_codes(cls):
        """获取表示成交的状态代码列表"""
        return [cls.SUCCEEDED, cls.PART_SUCCEEDED]

    @classmethod
    def get_finished_statuses(cls):
        """获取表示已完成的状态列表（中文）"""
        return ["已成交", "已撤销", "废单"]

    @classmethod
    def get_finished_status_codes(cls):
        """获取表示已完成的状态代码列表"""
        return [cls.SUCCEEDED, cls.CANCELED, cls.REJECTED]

    @classmethod
    def get_pending_statuses(cls):
        """获取表示待处理的状态列表（中文）"""
        return ["未报", "待报", "已报", "已确认", "部分成交"]

    @classmethod
    def get_pending_status_codes(cls):
        """获取表示待处理的状态代码列表"""
        return [cls.UNREPORTED, cls.WAIT_REPORTING, cls.REPORTED, cls.PART_SUCCEEDED]


class OperationType:
    """操作类型常量"""

    BUY = xtconstant.STOCK_BUY
    SELL = xtconstant.STOCK_SELL


class PriceType:
    """价格类型常量"""

    LATEST = xtconstant.PRTP_LATEST  # 最新价
    MARKET = xtconstant.PRTP_MARKET  # 市价
    LIMIT = xtconstant.PRTP_FIX  # 限价


# 账户状态映射：状态码 -> 中文描述
ACCOUNT_STATUS_MAP = {
    -1: "无效",
    0: "正常",
    1: "连接中",
    2: "登录中",
    3: "失败",
    4: "初始化中",
    5: "数据刷新校正中",
    6: "收盘后",
    7: "穿透副链接断开",
    8: "系统停用",
    9: "用户停用",
}

# 反向映射：中文描述 -> 状态码
ACCOUNT_STATUS_NAME_MAP = {v: k for k, v in ACCOUNT_STATUS_MAP.items()}


class AccountStatus:
    """账户状态常量"""

    INVALID = -1  # 无效
    OK = 0  # 正常
    WAITING_LOGIN = 1  # 连接中
    LOGINING = 2  # 登录中
    FAIL = 3  # 失败
    INITING = 4  # 初始化中
    CORRECTING = 5  # 数据刷新校正中
    CLOSED = 6  # 收盘后
    ASSIS_FAIL = 7  # 穿透副链接断开
    DISABLEBYSYS = 8  # 系统停用
    DISABLEBYUSER = 9  # 用户停用

    @classmethod
    def get_normal_statuses(cls):
        """获取正常运行状态列表"""
        return [cls.OK, cls.WAITING_LOGIN, cls.LOGINING, cls.INITING, cls.CORRECTING]

    @classmethod
    def get_error_statuses(cls):
        """获取错误状态列表"""
        return [cls.INVALID, cls.FAIL, cls.ASSIS_FAIL, cls.DISABLEBYSYS, cls.DISABLEBYUSER]


def get_status_name(status_code: int) -> str:
    """根据状态代码获取中文名称"""
    return STATUS_CODE_MAP.get(status_code, f"未知状态({status_code})")


def get_account_status_name(status_code: int) -> str:
    """根据账户状态代码获取中文名称"""
    return ACCOUNT_STATUS_MAP.get(status_code, f"未知账户状态({status_code})")


def get_status_code(status_name: str) -> int:
    """根据中文名称获取状态代码"""
    return ORDER_STATUS_MAP.get(status_name, xtconstant.ORDER_UNKNOWN)


def is_filled_status(status) -> bool:
    """判断是否为成交状态（支持字符串和整数）"""
    if isinstance(status, int):
        return status in OrderStatus.get_filled_status_codes()
    elif isinstance(status, str):
        return status in OrderStatus.get_filled_statuses()
    else:
        return False


def is_finished_status(status) -> bool:
    """判断是否为已完成状态（支持字符串和整数）"""
    if isinstance(status, int):
        return status in OrderStatus.get_finished_status_codes()
    elif isinstance(status, str):
        return status in OrderStatus.get_finished_statuses()
    else:
        return False


def is_pending_status(status) -> bool:
    """判断是否为待处理状态（支持字符串和整数）"""
    if isinstance(status, int):
        return status in OrderStatus.get_pending_status_codes()
    elif isinstance(status, str):
        return status in OrderStatus.get_pending_statuses()
    else:
        return False
