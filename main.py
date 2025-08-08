
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

def main():
    """主程序入口"""
    logger.info(f"QMT自动交易服务 v{settings.__dict__.get('version', '1.0.0')}")
    logger.info("=" * 50)

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == "test":
            test_system()
        elif command == "backup":
            manual_backup()
        elif command == "backup-config":
            show_backup_config()
        elif command == "stock-info":
            manage_stock_info()
        else:
            print_usage()
    else:
        # 直接运行服务（非Windows服务模式）
        run_service()

def run_service():
    """直接运行服务"""
    logger.info("启动交易服务（控制台模式）...")
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
        logger.info(f"  总缓存数: {stats['total_cached']}")
        logger.info(f"  有效缓存: {stats['valid_cached']}")
        logger.info(f"  过期缓存: {stats['expired_cached']}")
        logger.info(f"  预设数量: {stats['preset_count']}")
        logger.info(f"  缓存超时: {stats['cache_timeout']}秒")
        
        logger.info("\n预设股票列表:")
        preset_names = stock_info_cache._preset_names
        for code, name in sorted(preset_names.items()):
            display_name = stock_info_cache.get_stock_display_name(code)
            logger.info(f"  {display_name}")
            
        # 测试股票名称查询
        logger.info("\n测试股票名称查询:")
        test_codes = ['000001', '600519', '300750', '999999']
        for code in test_codes:
            name = stock_info_cache.get_stock_display_name(code)
            logger.info(f"  {code} -> {name}")
            
    except Exception as e:
        logger.error(f"× 管理股票信息失败: {e}")

def print_usage():
    """打印使用说明"""
    logger.info("使用方法:")
    logger.info("  python main.py                   - 直接运行服务（控制台模式）")
    logger.info("  python main.py test              - 测试系统连接")
    logger.info("  python main.py backup            - 手动执行数据备份")
    logger.info("  python main.py backup-config     - 显示备份配置")
    logger.info("  python main.py stock-info        - 管理股票信息缓存")

if __name__ == "__main__":
    main()
