"""交易日检查工具"""
from datetime import datetime, date
from src.logger_config import configured_logger as logger
from src.config import settings


def is_trading_day() -> bool:
    """
    检查今天是否为交易日
    
    Returns:
        bool: True if today is a trading day, False otherwise
    """
    # 如果启用了测试模式，直接返回True
    if settings.test_mode_enabled:
        logger.info("测试模式已启用，跳过交易日检查")
        return True
    
    # 如果禁用了交易日检查，直接返回True
    if not settings.trading_day_check_enabled:
        logger.info("交易日检查已禁用，跳过检查")
        return True
    
    today = datetime.now()
    today_str = today.strftime('%Y%m%d')
    today_date = today.date()
    
    # 使用数据库缓存的交易日历
    try:
        from src.trading_calendar_manager import trading_calendar_manager
        
        logger.info(f"正在检查 {today_str} 是否为交易日...")
        
        # 使用缓存的交易日历检查（会自动初始化）
        is_trading = trading_calendar_manager.is_trading_day(today_date)
        
        if is_trading:
            logger.info(f"✓ {today_str} 是交易日")
        else:
            logger.info(f"✗ {today_str} 不是交易日")
            
            # 显示日期和星期供参考
            weekday_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            logger.info(f"今天是 {weekday_names[today.weekday()]}")
            
            # 显示下一个交易日
            next_trading_day = trading_calendar_manager.get_next_trading_day(today_date)
            if next_trading_day:
                logger.info(f"下一个交易日: {next_trading_day.strftime('%Y-%m-%d')}")
        
        return is_trading
        
    except Exception as e:
        logger.error(f"检查交易日失败: {e}")
        # 出错时默认返回False（更保守的做法）
        return False