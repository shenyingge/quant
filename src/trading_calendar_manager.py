"""交易日历管理模块 - 使用akshare获取并缓存交易日历"""

from datetime import date, datetime, timedelta
from typing import List, Optional, Set

import akshare as ak
import pandas as pd
from sqlalchemy.orm import Session

from src.database import SessionLocal, TradingCalendar, create_tables
from src.logger_config import configured_logger as logger


class TradingCalendarManager:
    """交易日历管理器"""

    def __init__(self):
        self.db_session: Optional[Session] = None
        self._cached_years: Set[int] = set()
        self._memory_cache: dict = {}  # 内存缓存

    def _get_session(self) -> Session:
        """获取数据库会话"""
        if not self.db_session:
            self.db_session = SessionLocal()
        return self.db_session

    def close(self):
        """关闭数据库会话"""
        if self.db_session:
            self.db_session.close()
            self.db_session = None

    def _fetch_trading_calendar_from_akshare(self, year: int) -> List[date]:
        """
        从akshare获取指定年份的交易日历

        Args:
            year: 年份

        Returns:
            交易日期列表
        """
        try:
            logger.info(f"正在从akshare获取{year}年交易日历...")

            # 获取交易日历数据
            # akshare的tool_trade_date_hist_sina获取的是历史交易日
            calendar_df = ak.tool_trade_date_hist_sina()

            if calendar_df is None or calendar_df.empty:
                logger.error(f"无法从akshare获取交易日历数据")
                return []

            # 筛选指定年份的交易日
            calendar_df["trade_date"] = pd.to_datetime(calendar_df["trade_date"])
            year_data = calendar_df[calendar_df["trade_date"].dt.year == year]

            # 转换为日期列表
            trading_dates = [d.date() for d in year_data["trade_date"].tolist()]

            logger.info(f"成功获取{year}年交易日历，共{len(trading_dates)}个交易日")
            return trading_dates

        except Exception as e:
            logger.error(f"从akshare获取交易日历失败: {e}")
            return []

    def update_calendar_for_year(self, year: int, force: bool = False) -> bool:
        """
        更新指定年份的交易日历到数据库

        Args:
            year: 年份
            force: 是否强制更新（覆盖已有数据）

        Returns:
            是否成功
        """
        session = self._get_session()

        try:
            # 检查是否已有该年数据
            existing_count = (
                session.query(TradingCalendar).filter(TradingCalendar.year == year).count()
            )

            if existing_count > 0 and not force:
                logger.info(f"{year}年交易日历已存在，共{existing_count}条记录")
                # 加载到内存缓存
                trading_dates = (
                    session.query(TradingCalendar.date)
                    .filter(TradingCalendar.year == year, TradingCalendar.is_trading == True)
                    .all()
                )
                self._memory_cache[year] = set([d[0] for d in trading_dates])
                self._cached_years.add(year)
                return True

            if existing_count > 0 and force:
                # 删除旧数据
                session.query(TradingCalendar).filter(TradingCalendar.year == year).delete()
                session.commit()
                logger.info(f"已删除{year}年的{existing_count}条旧记录")

            # 获取交易日历
            trading_dates = self._fetch_trading_calendar_from_akshare(year)

            if not trading_dates:
                logger.error(f"无法获取{year}年交易日历")
                return False

            # 生成全年日期并标记交易日
            trading_dates_set = set(trading_dates)
            start_date = date(year, 1, 1)
            end_date = date(year, 12, 31)
            current_date = start_date

            records = []
            while current_date <= end_date:
                record = TradingCalendar(
                    date=current_date,
                    is_trading=current_date in trading_dates_set,
                    year=year,
                    market="SSE",
                )
                records.append(record)
                current_date += timedelta(days=1)

            # 批量插入
            session.bulk_save_objects(records)
            session.commit()

            trading_days_count = len(trading_dates)
            total_days = len(records)
            logger.info(
                f"成功更新{year}年交易日历：总共{total_days}天，其中{trading_days_count}个交易日"
            )

            # 更新内存缓存
            self._cached_years.add(year)
            self._memory_cache[year] = trading_dates_set

            return True

        except Exception as e:
            logger.error(f"更新{year}年交易日历失败: {e}")
            session.rollback()
            return False

    def is_trading_day(self, check_date: Optional[date] = None) -> bool:
        """
        检查指定日期是否为交易日

        Args:
            check_date: 要检查的日期，默认为今天

        Returns:
            是否为交易日
        """
        if check_date is None:
            check_date = date.today()

        year = check_date.year

        # 检查内存缓存
        if year in self._memory_cache:
            return check_date in self._memory_cache[year]

        session = self._get_session()

        try:
            # 查询数据库
            calendar_entry = (
                session.query(TradingCalendar).filter(TradingCalendar.date == check_date).first()
            )

            if calendar_entry:
                return calendar_entry.is_trading

            # 如果没有数据，尝试更新该年的日历
            logger.info(f"数据库中没有{year}年的交易日历，正在获取...")
            if self.update_calendar_for_year(year):
                # 重新查询
                calendar_entry = (
                    session.query(TradingCalendar)
                    .filter(TradingCalendar.date == check_date)
                    .first()
                )

                if calendar_entry:
                    return calendar_entry.is_trading

            # 如果还是没有，返回False（更保守的做法）
            logger.error(f"无法获取{check_date}的交易日信息")
            return False

        except Exception as e:
            logger.error(f"检查交易日失败: {e}")
            return False

    def auto_update_next_year(self):
        """
        自动更新下一年的交易日历（在每年12月调用）
        """
        current_year = date.today().year
        next_year = current_year + 1

        logger.info(f"自动更新{next_year}年交易日历...")

        # 更新下一年的日历
        if self.update_calendar_for_year(next_year):
            logger.info(f"成功自动更新{next_year}年交易日历")
        else:
            logger.error(f"自动更新{next_year}年交易日历失败")

    def get_next_trading_day(self, from_date: Optional[date] = None) -> Optional[date]:
        """
        获取下一个交易日

        Args:
            from_date: 起始日期，默认为今天

        Returns:
            下一个交易日，如果没有则返回None
        """
        if from_date is None:
            from_date = date.today()

        session = self._get_session()

        try:
            # 查询下一个交易日
            next_trading = (
                session.query(TradingCalendar)
                .filter(TradingCalendar.date > from_date, TradingCalendar.is_trading == True)
                .order_by(TradingCalendar.date)
                .first()
            )

            if next_trading:
                return next_trading.date

            # 如果没有找到，可能需要更新下一年的数据
            next_year = from_date.year + 1
            if next_year not in self._cached_years:
                logger.info(f"尝试获取{next_year}年交易日历...")
                if self.update_calendar_for_year(next_year):
                    # 重新查询
                    next_trading = (
                        session.query(TradingCalendar)
                        .filter(
                            TradingCalendar.date > from_date, TradingCalendar.is_trading == True
                        )
                        .order_by(TradingCalendar.date)
                        .first()
                    )

                    if next_trading:
                        return next_trading.date

            return None

        except Exception as e:
            logger.error(f"获取下一个交易日失败: {e}")
            return None

    def get_previous_trading_day(self, from_date: Optional[date] = None) -> Optional[date]:
        """
        获取上一个交易日

        Args:
            from_date: 起始日期，默认为今天

        Returns:
            上一个交易日，如果没有则返回None
        """
        if from_date is None:
            from_date = date.today()

        session = self._get_session()

        try:
            # 查询上一个交易日
            prev_trading = (
                session.query(TradingCalendar)
                .filter(TradingCalendar.date < from_date, TradingCalendar.is_trading == True)
                .order_by(TradingCalendar.date.desc())
                .first()
            )

            if prev_trading:
                return prev_trading.date

            return None

        except Exception as e:
            logger.error(f"获取上一个交易日失败: {e}")
            return None


# 全局实例
trading_calendar_manager = TradingCalendarManager()


def initialize_trading_calendar():
    """初始化交易日历（确保当前年份的数据存在）"""
    try:
        current_year = date.today().year
        current_month = date.today().month

        # 确保数据库表存在
        create_tables()

        # 检查是否已初始化，避免重复初始化
        if current_year in trading_calendar_manager._cached_years:
            logger.debug(f"{current_year}年交易日历已初始化")
            return

        # 更新当前年份
        logger.info(f"初始化{current_year}年交易日历...")
        trading_calendar_manager.update_calendar_for_year(current_year)

        # 如果是12月，也更新下一年
        if current_month == 12:
            next_year = current_year + 1
            logger.info(f"当前是12月，同时初始化{next_year}年交易日历...")
            trading_calendar_manager.update_calendar_for_year(next_year)
    except Exception as e:
        logger.error(f"初始化交易日历失败: {e}")
