
import os
import sys
import locale
import codecs

# 设置编码环境
if sys.platform.startswith('win'):
    # Windows系统编码设置
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # 设置控制台输出编码
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
else:
    # 非Windows系统
    locale.setlocale(locale.LC_ALL, 'zh_CN.UTF-8')

from src.trading_service import TradingService
from src.redis_listener import RedisSignalListener
from src.config import settings
from src.logger_config import configured_logger as logger
from src.trading_day_checker import is_trading_day

def main():
    """主程序入口"""
    logger.info(f"QMT自动交易服务 v{settings.__dict__.get('version', '1.0.0')}")
    logger.info("=" * 50)

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == "run":
            run_service()
        elif command == "test-run":
            run_service(test_mode=True)
        elif command == "test":
            test_system()
        elif command == "backup":
            manual_backup()
        elif command == "backup-config":
            show_backup_config()
        elif command == "stock-info":
            manage_stock_info()
        elif command == "calendar":
            manage_trading_calendar()
        elif command == "pnl-summary":
            send_pnl_summary()
        else:
            print_usage()
    else:
        # 没有参数时显示使用说明
        print_usage()

def run_service(test_mode: bool = False):
    """直接运行服务"""
    if test_mode:
        logger.info("启动交易服务（测试模式）...")
        # 临时启用测试模式
        os.environ['TEST_MODE_ENABLED'] = 'true'
        # 重新加载配置
        from src.config import Settings
        global settings
        settings = Settings()
    else:
        logger.info("启动交易服务（控制台模式）...")
    
    # 检查是否为交易日
    if not is_trading_day():
        if test_mode:
            logger.warning("测试模式下检测到非交易日，但仍将继续运行")
        else:
            logger.info("今天不是交易日，服务将退出")
            logger.info("如需强制运行，请使用: python main.py test-run")
            logger.info("或设置环境变量 TEST_MODE_ENABLED=true")
            return
    
    service = None
    try:
        service = TradingService()
        # start() 方法现在包含了 run_forever() 阻塞调用，会一直运行直到收到中断
        service.start()
            
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在退出...")
    except Exception as e:
        logger.error(f"服务运行错误: {e}")
    finally:
        if service:
            service.stop()

def test_system():
    """测试系统连接"""
    logger.info("正在测试系统连接...")

    # 测试Redis连接
    listener = RedisSignalListener(lambda x: None)
    redis_ok = listener.test_connection()

    # 测试数据库
    try:
        from src.database import create_tables, SessionLocal
        create_tables()
        db = SessionLocal()
        db.close()
        db_ok = True
        logger.info("数据库连接正常")
    except Exception as e:
        db_ok = False
        logger.error(f"数据库连接失败: {e}")

    # 测试QMT连接
    try:
        from src.trader import QMTTrader
        trader = QMTTrader()
        qmt_ok = trader.connect()
        if qmt_ok:
            trader.disconnect()
    except Exception as e:
        qmt_ok = False
        logger.error(f"QMT连接失败: {e}")

    logger.info("\n系统测试结果:")
    logger.info(f"Redis: {'OK' if redis_ok else 'FAIL'}")
    logger.info(f"数据库: {'OK' if db_ok else 'FAIL'}")
    logger.info(f"QMT: {'OK' if qmt_ok else 'FAIL'}")

    if redis_ok and db_ok and qmt_ok:
        logger.info("\n所有系统组件正常，可以启动服务")

        # 发布测试信号
        if input("\n是否发布测试交易信号？(y/N): ").lower() == 'y':
            test_signal = {
                "signal_id": f"TEST_{int(__import__('time').time())}",
                "stock_code": "000001",
                "direction": "BUY",
                "volume": 100,
                "price": 10.0
            }
            listener.publish_test_signal(test_signal)
            logger.info(f"测试信号已发布: {test_signal}")
    else:
        logger.error("\n系统存在问题，请检查配置")


def manual_backup():
    """手动执行数据备份"""
    logger.info("正在执行手动数据备份...")
    try:
        from src.backup_service import DatabaseBackupService
        
        backup_service = DatabaseBackupService()
        
        success = backup_service.manual_backup()
        if success:
            logger.info("√ 数据备份完成")
        else:
            logger.error("× 数据备份失败")
            
    except Exception as e:
        logger.error(f"× 备份失败: {e}")

def show_backup_config():
    """显示备份配置"""
    try:
        from src.backup_service import get_backup_config
        
        config = get_backup_config()
        logger.info("当前备份配置:")
        logger.info("=" * 50)
        
        for key, value in config.items():
            if 'password' in key.lower() or 'token' in key.lower():
                # 隐藏敏感信息
                value = "***" if value else ""
            logger.info(f"{key:20}: {value}")
            
        logger.info("\n配置位置: .env 文件")
        logger.info("修改配置后需要重启服务生效")
        
    except Exception as e:
        logger.error(f"× 读取备份配置失败: {e}")

def manage_stock_info():
    """管理股票信息"""
    try:
        from src.stock_info import stock_info_cache
        
        logger.info("股票信息管理:")
        logger.info("=" * 50)
        
        # 显示缓存状态
        stats = stock_info_cache.get_cache_stats()
        logger.info(f"缓存统计:")
        logger.info(f"  数据库总缓存: {stats['total_cached']}")
        logger.info(f"  有效缓存(24h内): {stats['valid_cached']}")
        logger.info(f"  过期缓存: {stats['expired_cached']}")
        logger.info(f"  缓存超时: {stats['cache_timeout_hours']}小时")
        
        # 检查是否需要进行批量更新
        if len(sys.argv) > 2:
            action = sys.argv[2].lower()
            if action == "update":
                logger.info("\n开始批量更新股票信息...")
                updated_count = stock_info_cache.bulk_update_stock_info()
                logger.info(f"✓ 批量更新完成，共更新 {updated_count} 条股票信息")
                return
            elif action == "clear":
                logger.info("\n清空股票信息缓存...")
                stock_info_cache.clear_cache()
                logger.info("✓ 股票信息缓存已清空")
                return
            elif action == "test":
                # 测试股票名称查询
                logger.info("\n测试股票名称查询:")
                test_codes = ['000001.SZ', '600519.SH', '000977.SZ', '605069.SH', '001231.SZ', '999999.SZ']
                for code in test_codes:
                    name = stock_info_cache.get_stock_display_name(code)
                    logger.info(f"  {code} -> {name}")
                return
        
        # 默认显示帮助信息
        logger.info("\n可用操作:")
        logger.info("  python main.py stock-info update  - 批量更新所有股票信息")
        logger.info("  python main.py stock-info clear   - 清空股票信息缓存")
        logger.info("  python main.py stock-info test    - 测试股票名称查询")
        logger.info("  python main.py stock-info         - 显示缓存状态")
            
    except Exception as e:
        logger.error(f"× 管理股票信息失败: {e}")

def manage_trading_calendar():
    """管理交易日历"""
    try:
        from src.trading_calendar_manager import trading_calendar_manager, initialize_trading_calendar
        from datetime import date
        
        logger.info("交易日历管理:")
        logger.info("=" * 50)
        
        # 初始化当前年份的交易日历
        current_year = date.today().year
        logger.info(f"正在初始化{current_year}年交易日历...")
        initialize_trading_calendar()
        
        # 检查今天是否为交易日
        today = date.today()
        is_trading = trading_calendar_manager.is_trading_day(today)
        
        logger.info(f"\n今日({today.strftime('%Y-%m-%d')})：{'交易日' if is_trading else '非交易日'}")
        
        # 显示下一个交易日
        next_trading = trading_calendar_manager.get_next_trading_day(today)
        if next_trading:
            logger.info(f"下一个交易日：{next_trading.strftime('%Y-%m-%d')}")
        
        # 显示上一个交易日
        prev_trading = trading_calendar_manager.get_previous_trading_day(today)
        if prev_trading:
            logger.info(f"上一个交易日：{prev_trading.strftime('%Y-%m-%d')}")
        
        # 询问是否更新下一年
        if input(f"\n是否更新{current_year + 1}年交易日历？(y/N): ").lower() == 'y':
            success = trading_calendar_manager.update_calendar_for_year(current_year + 1, force=True)
            if success:
                logger.info(f"✓ {current_year + 1}年交易日历更新成功")
            else:
                logger.error(f"✗ {current_year + 1}年交易日历更新失败")
                
    except Exception as e:
        logger.error(f"管理交易日历失败: {e}")

def send_pnl_summary():
    """手动发送当日盈亏汇总通知"""
    logger.info("手动发送当日盈亏汇总通知")
    logger.info("=" * 50)
    
    try:
        from src.daily_pnl_calculator import calculate_daily_summary
        from src.notifications import FeishuNotifier
        
        # 计算当日交易汇总
        logger.info("正在计算当日盈亏汇总...")
        pnl_data = calculate_daily_summary()
        
        if not pnl_data:
            logger.error("无法生成盈亏汇总数据")
            return
            
        logger.info(f"✓ 成功生成 {pnl_data['date_display']} 的交易汇总")
        logger.info(f"  总成交订单：{pnl_data['summary']['total_orders']}笔")
        logger.info(f"  总成交金额：¥{pnl_data['summary']['total_amount']:,.2f}")
        
        # 创建通知器并发送
        notifier = FeishuNotifier()
        
        logger.info("\n正在发送飞书通知...")
        success = notifier.notify_daily_pnl_summary(pnl_data)
        
        if success:
            logger.info("✓ 盈亏汇总通知发送成功！")
        else:
            logger.error("× 盈亏汇总通知发送失败")
            
    except Exception as e:
        logger.error(f"发送盈亏汇总通知失败: {e}")

def print_usage():
    """打印使用说明"""
    logger.info("使用方法:")
    logger.info("  python main.py run               - 直接运行服务（控制台模式）")
    logger.info("  python main.py test-run          - 测试模式运行服务（跳过交易日检查）")
    logger.info("  python main.py test              - 测试系统连接")
    logger.info("  python main.py backup            - 手动执行数据备份")
    logger.info("  python main.py backup-config     - 显示备份配置")
    logger.info("  python main.py stock-info        - 管理股票信息缓存")
    logger.info("  python main.py calendar          - 管理交易日历")
    logger.info("  python main.py pnl-summary       - 手动发送当日盈亏汇总通知")

if __name__ == "__main__":
    main()
