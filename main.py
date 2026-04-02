import codecs
import locale
import os
import sys
import time
from datetime import date
from typing import Optional

# 设置编码环境
if sys.platform.startswith("win"):
    # Windows系统编码设置
    os.environ["PYTHONIOENCODING"] = "utf-8"
    # 设置控制台输出编码
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
else:
    # 非Windows系统
    for locale_name in ("zh_CN.UTF-8", "C.UTF-8", ""):
        try:
            locale.setlocale(locale.LC_ALL, locale_name)
            break
        except locale.Error:
            continue

from src.config import settings
from src.logger_config import configure_process_logger
from src.logger_config import configured_logger as logger
from src.trading_day_checker import is_trading_day

STRATEGY_ENGINE_NAME = "策略引擎"
TRADING_ENGINE_NAME = "交易引擎"


def _resolve_app_role(command: Optional[str]) -> str:
    role_map = {
        "run": "trading_engine",
        "test-run": "trading_engine",
        "test": "system_test",
        "backup": "backup_service",
        "backup-config": "backup_service",
        "stock-info": "stock_info",
        "calendar": "calendar",
        "pnl-summary": "pnl_summary",
        "export-daily": "daily_export",
        "export-minute-history": "minute_history_export",
        "export-minute-daily": "minute_history_export",
        "t0-strategy": "strategy_engine",
        "t0-daemon": "strategy_engine",
        "t0-sync-position": "strategy_engine",
        "t0-reconcile": "strategy_engine",
        "t0-backtest": "strategy_engine",
        "cms-check": "cms_server",
        "cms-server": "cms_server",
        "watchdog": "watchdog",
    }
    return role_map.get(command or "", "cli")


def _resolve_qmt_session_id(mode: str) -> int:
    """Resolve a mode-specific QMT session id with fallback to the default value."""
    session_id_map = {
        "trading-service": settings.qmt_session_id_trading_service,
        "t0-daemon": settings.qmt_session_id_t0_daemon,
        "t0-sync": settings.qmt_session_id_t0_sync,
    }
    return session_id_map.get(mode) or settings.qmt_session_id


def main():
    """命令行入口。"""
    command = sys.argv[1].lower() if len(sys.argv) > 1 else None
    configure_process_logger(_resolve_app_role(command))

    if command != "cms-check":
        logger.info(f"QMT服务 v{settings.__dict__.get('version', '1.0.0')}")
        logger.info("=" * 50)

    if len(sys.argv) > 1:
        # 解析重试参数
        max_retries = 3
        retry_delay = 60

        # 查找重试参数
        for arg in sys.argv[2:]:
            if arg.startswith("--max-retries="):
                try:
                    max_retries = int(arg.split("=")[1])
                except ValueError:
                    logger.warning(f"无效的重试次数参数: {arg}")
            elif arg.startswith("--retry-delay="):
                try:
                    retry_delay = int(arg.split("=")[1])
                except ValueError:
                    logger.warning(f"无效的重试延迟参数: {arg}")

        if command == "run":
            run_service(max_retries=max_retries, retry_delay=retry_delay)
            return 0
        elif command == "test-run":
            run_service(test_mode=True, max_retries=max_retries, retry_delay=retry_delay)
            return 0
        elif command == "test":
            test_system()
            return 0
        elif command == "backup":
            manual_backup()
            return 0
        elif command == "backup-config":
            show_backup_config()
            return 0
        elif command == "stock-info":
            manage_stock_info()
            return 0
        elif command == "calendar":
            manage_trading_calendar()
            return 0
        elif command == "pnl-summary":
            send_pnl_summary()
            return 0
        elif command == "export-daily":
            export_daily()
            return 0
        elif command == "export-minute-history":
            return export_minute_history(sys.argv[2:])
        elif command == "export-minute-daily":
            return export_minute_daily(sys.argv[2:])
        elif command == "t0-strategy":
            run_t0_strategy()
            return 0
        elif command == "t0-daemon":
            run_t0_daemon()
            return 0
        elif command == "t0-sync-position":
            sync_t0_position()
            return 0
        elif command == "t0-reconcile":
            reconcile_t0_state()
            return 0
        elif command == "t0-backtest":
            run_t0_backtest(sys.argv[2:])
            return 0
        elif command == "t0-signal-viewer":
            run_signal_viewer()
            return 0
        elif command == "cms-check":
            return run_cms_check(sys.argv[2:])
        elif command == "cms-server":
            return run_cms_server(sys.argv[2:])
        elif command == "watchdog":
            return run_watchdog(sys.argv[2:])
        else:
            print_usage()
            return 1
    else:
        # 没有参数时显示使用说明
        print_usage()

        return 1


def run_service(test_mode: bool = False, max_retries: int = 3, retry_delay: int = 60):
    """直接运行服务，支持重试机制"""
    from src.trading_engine import TradingEngine

    if test_mode:
        logger.info(f"启动{TRADING_ENGINE_NAME}（测试模式）...")
        # 临时启用测试模式
        os.environ["TEST_MODE_ENABLED"] = "true"
        # 重新加载配置
        from src.config import Settings

        global settings
        settings = Settings()
    else:
        logger.info(f"启动{TRADING_ENGINE_NAME}（控制台模式）...")

    # 检查是否为交易日
    if not is_trading_day():
        if test_mode:
            logger.warning("测试模式下检测到非交易日，但仍将继续运行")
        else:
            logger.info("今天不是交易日，服务将退出")
            logger.info("如需强制运行，请使用: python main.py test-run")
            logger.info("或设置环境变量 TEST_MODE_ENABLED=true")
            return

    retry_count = 0
    while retry_count <= max_retries:
        service = None
        try:
            if retry_count > 0:
                logger.info(f"第 {retry_count}/{max_retries} 次重试启动服务...")

            service = TradingEngine()

            # 尝试启动服务
            start_success = service.start()

            if start_success:
                # 服务正常启动并运行完成
                logger.info("服务正常退出")
                break
            else:
                # 启动失败
                raise Exception("服务启动失败")

        except KeyboardInterrupt:
            logger.info("收到停止信号，正在退出...")
            break
        except Exception as e:
            logger.error(f"服务运行错误: {e}")
            retry_count += 1

            if retry_count <= max_retries:
                logger.warning(
                    f"服务将在 {retry_delay} 秒后进行第 {retry_count}/{max_retries} 次重试"
                )
                try:
                    import time

                    time.sleep(retry_delay)
                except KeyboardInterrupt:
                    logger.info("收到停止信号，取消重试")
                    break
            else:
                logger.error(f"服务重试 {max_retries} 次后仍然失败，停止重试")
        finally:
            if service:
                service.stop()

    logger.info(f"{TRADING_ENGINE_NAME}已退出")


def test_system():
    """测试系统连接"""
    from src.redis_listener import RedisSignalListener

    logger.info("正在测试系统连接...")

    # 测试Redis连接
    listener = RedisSignalListener(lambda x: None)
    redis_ok = listener.test_connection()

    # 测试数据库
    try:
        from src.database import SessionLocal, create_tables

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

        trader = QMTTrader(session_id=_resolve_qmt_session_id("trading-service"))
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
        if input("\n是否发布测试交易信号？(y/N): ").lower() == "y":
            test_signal = {
                "signal_id": f"TEST_{int(__import__('time').time())}",
                "stock_code": "000001",
                "direction": "BUY",
                "volume": 100,
                "price": 10.0,
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
            if "password" in key.lower() or "token" in key.lower():
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
                test_codes = [
                    "000001.SZ",
                    "600519.SH",
                    "000977.SZ",
                    "605069.SH",
                    "001231.SZ",
                    "999999.SZ",
                ]
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
        from datetime import date

        from src.trading_calendar_manager import (
            initialize_trading_calendar,
            trading_calendar_manager,
        )

        logger.info("交易日历管理:")
        logger.info("=" * 50)

        # 初始化当前年份的交易日历
        current_year = date.today().year
        logger.info(f"正在初始化{current_year}年交易日历...")
        initialize_trading_calendar()

        # 检查今天是否为交易日
        today = date.today()
        is_trading = trading_calendar_manager.is_trading_day(today)

        logger.info(
            f"\n今日({today.strftime('%Y-%m-%d')})：{'交易日' if is_trading else '非交易日'}"
        )

        # 显示下一个交易日
        next_trading = trading_calendar_manager.get_next_trading_day(today)
        if next_trading:
            logger.info(f"下一个交易日：{next_trading.strftime('%Y-%m-%d')}")

        # 显示上一个交易日
        prev_trading = trading_calendar_manager.get_previous_trading_day(today)
        if prev_trading:
            logger.info(f"上一个交易日：{prev_trading.strftime('%Y-%m-%d')}")

        # 询问是否更新下一年
        if input(f"\n是否更新{current_year + 1}年交易日历？(y/N): ").lower() == "y":
            success = trading_calendar_manager.update_calendar_for_year(
                current_year + 1, force=True
            )
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


def export_daily():
    """导出每日持仓与成交记录"""
    logger.info("导出每日持仓与成交记录")
    logger.info("=" * 50)

    try:
        from src.daily_exporter import export_daily_data

        # 执行导出
        success = export_daily_data()

        if success:
            logger.info("✓ 每日数据导出完成")
        else:
            logger.error("× 每日数据导出失败")

    except Exception as e:
        logger.error(f"导出每日数据失败: {e}")


def export_minute_history(argv=None):
    """导出分钟历史行情"""
    logger.info("导出分钟历史行情...")
    logger.info("=" * 50)

    try:
        from src.minute_history_exporter import main as export_main

        return export_main(argv)
    except Exception as e:
        logger.error(f"导出分钟历史行情失败: {e}")
        return 1


def export_minute_daily(argv=None):
    """导出当日分钟行情。"""
    logger.info("导出当日分钟行情...")
    logger.info("=" * 50)

    if not is_trading_day():
        logger.info("今天不是交易日，跳过导出当日分钟行情")
        return 0

    trade_date = date.today().strftime("%Y%m%d")
    default_args = ["--trade-date", trade_date, "--listed-only", "--overwrite", "--skip-zip"]
    return export_minute_history(default_args + (argv or []))


def _notify_t0_runtime(component: str, event: str, detail: str = "", level: str = "info"):
    """尽力发送 T+0 运行时通知。"""
    try:
        from src.notifications import FeishuNotifier

        FeishuNotifier().notify_runtime_event(component, event, detail, level)
    except Exception as notify_error:
        logger.error(f"T+0 运行通知发送失败: {notify_error}")


def _get_t0_poll_interval_seconds() -> int:
    raw_value = getattr(settings, "t0_poll_interval_seconds", 60)
    if raw_value is None:
        raw_value = 60
    return max(int(raw_value), 1)


def _sleep_until_next_t0_poll(interval_seconds: int) -> None:
    import time

    aligned_sleep = interval_seconds - (time.time() % interval_seconds)
    if aligned_sleep <= 0 or aligned_sleep > interval_seconds:
        aligned_sleep = interval_seconds
    time.sleep(aligned_sleep)


def _should_skip_non_trading_day(component_name: str) -> bool:
    if is_trading_day():
        return False

    logger.info(f"今天不是交易日，跳过启动 {component_name}")
    return True


def _sync_t0_position_via_qmt(*, notify: bool = False) -> bool:
    from src.notifications import FeishuNotifier
    from src.strategy.position_syncer import PositionSyncer
    from src.trader import QMTTrader

    notifier = FeishuNotifier() if notify else None
    session_id = _resolve_qmt_session_id("t0-sync")
    logger.info(f"{STRATEGY_ENGINE_NAME} position sync uses QMT Session ID: {session_id}")

    connect_retry_attempts = max(int(settings.t0_sync_connect_retry_attempts), 1)
    connect_retry_delay_seconds = max(int(settings.t0_sync_connect_retry_delay_seconds), 1)
    connected = False
    trader = None

    try:
        for attempt in range(1, connect_retry_attempts + 1):
            trader = QMTTrader(session_id=session_id)
            if trader.connect():
                connected = True
                break

            logger.warning(
                f"QMT position sync connect failed, retry {attempt}/{connect_retry_attempts}"
            )
            try:
                trader.disconnect()
            except Exception:
                pass
            if attempt < connect_retry_attempts:
                time.sleep(connect_retry_delay_seconds)

        if not connected:
            logger.error("QMT connection failed during T0 position sync")
            if notifier:
                notifier.notify_t0_position_sync(
                    settings.t0_stock_code,
                    False,
                    (
                        f"QMT connection failed for T0 position sync "
                        f"(retries={connect_retry_attempts}, delay={connect_retry_delay_seconds}s)"
                    ),
                )
            return False

        success = PositionSyncer().sync_from_qmt(trader, settings.t0_stock_code)
        if notifier:
            if success:
                notifier.notify_t0_position_sync(
                    settings.t0_stock_code, True, "T0 position synced from QMT"
                )
            else:
                notifier.notify_t0_position_sync(
                    settings.t0_stock_code, False, "QMT sync returned an unsuccessful result"
                )
        return success
    finally:
        if trader is not None:
            try:
                trader.disconnect()
            except Exception:
                pass


def _ensure_t0_position_state() -> bool:
    from src.strategy.position_syncer import PositionSyncer

    syncer = PositionSyncer()
    if not syncer.needs_qmt_sync():
        return True

    logger.info("No fresh T0 baseline position snapshot exists for today, syncing from QMT")
    success = _sync_t0_position_via_qmt(notify=False)
    if not success:
        logger.warning(
            "Failed to initialize today's T0 baseline position snapshot, continuing with the last local state"
        )
    return success


def run_t0_strategy():
    """运行一次策略引擎。"""
    if _should_skip_non_trading_day(STRATEGY_ENGINE_NAME):
        return

    logger.info(f"运行 {STRATEGY_ENGINE_NAME} 一次")
    _notify_t0_runtime(STRATEGY_ENGINE_NAME, "启动", "开始执行一次策略信号生成", "info")
    try:
        from src.strategy.strategy_engine import StrategyEngine

        _ensure_t0_position_state()
        strategy_engine = StrategyEngine()
        signal_card = strategy_engine.run_once()
        logger.info(f"Strategy execution completed: {signal_card['signal']['action']}")
        _notify_t0_runtime(
            STRATEGY_ENGINE_NAME,
            "完成",
            f"本次结果: {signal_card['signal']['action']}",
            "success" if not signal_card.get("error") else "warning",
        )
    except Exception as e:
        logger.error(f"{STRATEGY_ENGINE_NAME} execution failed: {e}")
        _notify_t0_runtime(STRATEGY_ENGINE_NAME, "轮询异常", str(e), "error")


def run_t0_daemon():
    """持续运行策略引擎守护进程。"""
    if _should_skip_non_trading_day(STRATEGY_ENGINE_NAME):
        return

    logger.info(f"启动 {STRATEGY_ENGINE_NAME}")
    poll_interval_seconds = _get_t0_poll_interval_seconds()
    intraday_bar_period = getattr(settings, "t0_intraday_bar_period", "1m")
    _notify_t0_runtime(
        STRATEGY_ENGINE_NAME,
        "启动",
        f"开始轮询策略信号: interval={poll_interval_seconds}s, bar_period={intraday_bar_period}",
        "info",
    )

    exit_detail = "守护进程已停止"
    exit_level = "success"
    try:
        from src.strategy.strategy_engine import StrategyEngine

        _ensure_t0_position_state()
        session_id = _resolve_qmt_session_id("t0-daemon")
        logger.info(f"{STRATEGY_ENGINE_NAME} 使用 QMT Session ID: {session_id}")
        strategy_engine = StrategyEngine()

        while True:
            try:
                now = time.localtime()
                if 9 <= now.tm_hour < 15:
                    strategy_engine.run_once()
                _sleep_until_next_t0_poll(poll_interval_seconds)
            except KeyboardInterrupt:
                logger.info("收到停止信号")
                exit_detail = "收到停止信号，守护进程正常退出"
                break
            except Exception as e:
                logger.error(f"策略执行异常: {e}")
                _notify_t0_runtime(STRATEGY_ENGINE_NAME, "轮询异常", str(e), "error")
                _sleep_until_next_t0_poll(poll_interval_seconds)
    except Exception as e:
        logger.error(f"{STRATEGY_ENGINE_NAME} 启动失败: {e}")
        exit_detail = f"启动失败: {e}"
        exit_level = "error"
    finally:
        _notify_t0_runtime(STRATEGY_ENGINE_NAME, "停止", exit_detail, exit_level)


def sync_t0_position():
    """从 QMT 同步 T0 仓位。"""
    if _should_skip_non_trading_day(STRATEGY_ENGINE_NAME):
        return

    logger.info(f"同步 {STRATEGY_ENGINE_NAME} 仓位")
    _notify_t0_runtime(
        STRATEGY_ENGINE_NAME, "仓位同步启动", f"开始同步 {settings.t0_stock_code} 仓位", "info"
    )
    try:
        from src.notifications import FeishuNotifier
        from src.strategy.position_syncer import PositionSyncer
        from src.trader import QMTTrader

        session_id = _resolve_qmt_session_id("t0-sync")
        logger.info(f"{STRATEGY_ENGINE_NAME} 仓位同步使用 QMT Session ID: {session_id}")
        connect_retry_attempts = max(int(settings.t0_sync_connect_retry_attempts), 1)
        connect_retry_delay_seconds = max(int(settings.t0_sync_connect_retry_delay_seconds), 1)
        connected = False
        trader = None

        for attempt in range(1, connect_retry_attempts + 1):
            trader = QMTTrader(session_id=session_id)
            if trader.connect():
                connected = True
                break

            logger.warning(f"QMT 连接失败，仓位同步重试 {attempt}/{connect_retry_attempts}")
            try:
                trader.disconnect()
            except Exception:
                pass
            if attempt < connect_retry_attempts:
                time.sleep(connect_retry_delay_seconds)

        if not connected:
            logger.error("QMT 连接失败")
            FeishuNotifier().notify_t0_position_sync(
                settings.t0_stock_code,
                False,
                (
                    f"QMT 连接失败，未能同步仓位"
                    f"（已重试 {connect_retry_attempts} 次，间隔 {connect_retry_delay_seconds} 秒）"
                ),
            )
            return

        syncer = PositionSyncer()
        success = syncer.sync_from_qmt(trader, settings.t0_stock_code)

        if success:
            logger.info("仓位同步成功")
            FeishuNotifier().notify_t0_position_sync(
                settings.t0_stock_code, True, "已从 QMT 成功同步仓位"
            )
        else:
            logger.error("仓位同步失败")
            FeishuNotifier().notify_t0_position_sync(
                settings.t0_stock_code, False, "同步过程返回失败结果"
            )

        trader.disconnect()
    except Exception as e:
        logger.error(f"仓位同步失败: {e}")
        FeishuNotifier().notify_t0_position_sync(settings.t0_stock_code, False, f"同步异常: {e}")


def reconcile_t0_state():
    """Run the end-of-day read-only T0 reconciliation."""
    if _should_skip_non_trading_day(STRATEGY_ENGINE_NAME):
        return

    logger.info(f"收盘对账 {STRATEGY_ENGINE_NAME}")
    try:
        from src.notifications import FeishuNotifier
        from src.strategy.t0_reconciler import T0Reconciler
        from src.trader import QMTTrader

        session_id = _resolve_qmt_session_id("t0-sync")
        logger.info(f"{STRATEGY_ENGINE_NAME} 收盘对账使用 QMT Session ID: {session_id}")
        connect_retry_attempts = max(int(settings.t0_sync_connect_retry_attempts), 1)
        connect_retry_delay_seconds = max(int(settings.t0_sync_connect_retry_delay_seconds), 1)
        connected = False
        trader = None

        for attempt in range(1, connect_retry_attempts + 1):
            trader = QMTTrader(session_id=session_id)
            if trader.connect():
                connected = True
                break

            logger.warning(f"QMT 收盘对账连接失败，重试 {attempt}/{connect_retry_attempts}")
            try:
                trader.disconnect()
            except Exception:
                pass
            if attempt < connect_retry_attempts:
                time.sleep(connect_retry_delay_seconds)

        if not connected:
            logger.error("QMT 连接失败，无法执行收盘对账")
            FeishuNotifier().notify_runtime_event(
                STRATEGY_ENGINE_NAME,
                "收盘对账异常",
                (
                    f"QMT 连接失败，未能执行收盘对账 "
                    f"(retries={connect_retry_attempts}, delay={connect_retry_delay_seconds}s)"
                ),
                "warning",
            )
            return

        reconciler = T0Reconciler(notifier=FeishuNotifier())
        report = reconciler.run(trader, notify=True)
        if report.get("ok"):
            logger.info("收盘对账通过")
        else:
            logger.warning("收盘对账发现异常: {}", " | ".join(report.get("issues", [])))

        trader.disconnect()
    except Exception as e:
        logger.error(f"收盘对账失败: {e}")
        FeishuNotifier().notify_runtime_event(
            STRATEGY_ENGINE_NAME, "收盘对账异常", f"执行异常: {e}", "warning"
        )


def run_t0_backtest(argv=None):
    """运行 T+0 文件回测。"""
    try:
        from src.backtest.cli import run_backtest_cli

        raise_code = run_backtest_cli(argv)
        if raise_code:
            logger.error(f"T+0 回测执行失败，退出码: {raise_code}")
    except SystemExit as exc:
        if exc.code not in (0, None):
            logger.error(f"T+0 回测参数错误，退出码: {exc.code}")
    except Exception as e:
        logger.error(f"T+0 回测执行失败: {e}")


def run_signal_viewer():
    """运行 T+0 信号查看器 - 从 Redis 读取信号并展示到文件"""
    from src.strategy.signal_viewer import SignalViewer

    logger.info("启动 T+0 信号查看器")
    viewer = SignalViewer()
    viewer.watch(interval=settings.t0_poll_interval_seconds)


def run_cms_check(argv=None):
    """输出一次标准化 health check 结果。"""
    import json

    from src.cms_server import ProjectCmsChecker

    logger.remove()
    snapshot = ProjectCmsChecker(scope="project").build_snapshot().to_dict()
    pretty = not argv or "--compact" not in argv
    print(json.dumps(snapshot, ensure_ascii=False, indent=2 if pretty else None))
    return 0 if snapshot["status"] != "down" else 1


def run_cms_server(argv=None):
    """启动轻量级 HTTP CMS 服务。"""
    from src.cms_server import serve_cms_server

    host = settings.cms_server_host
    port = settings.cms_server_port

    for arg in argv or []:
        if arg.startswith("--host="):
            host = arg.split("=", 1)[1].strip() or host
        elif arg.startswith("--port="):
            try:
                port = int(arg.split("=", 1)[1].strip())
            except ValueError:
                logger.warning(f"无效的 CMS server 端口参数: {arg}")

    serve_cms_server(host=host, port=port, scope="project")
    return 0


def run_watchdog(argv=None):
    """Run the local watchdog service."""
    from src.watchdog_service import run_watchdog_service

    once = False
    dry_run = False

    for arg in argv or []:
        if arg == "--once":
            once = True
        elif arg == "--dry-run":
            dry_run = True

    run_watchdog_service(once=once, dry_run=dry_run)
    return 0


def print_usage():
    logger.info("  python main.py watchdog               - start the 24x7 watchdog service")
    """打印命令行使用说明。"""
    logger.info("使用方法:")
    logger.info(f"  python main.py run                    - 运行 {TRADING_ENGINE_NAME}")
    logger.info(f"  python main.py test-run               - 测试模式运行 {TRADING_ENGINE_NAME}")
    logger.info("  python main.py test                   - 运行系统连接检查")
    logger.info("  python main.py backup                 - 手动执行数据备份")
    logger.info("  python main.py backup-config          - 显示备份配置")
    logger.info("  python main.py stock-info             - 管理股票信息缓存")
    logger.info("  python main.py calendar               - 管理交易日历")
    logger.info("  python main.py pnl-summary            - 发送当日盈亏汇总通知")
    logger.info("  python main.py export-daily           - 导出每日持仓与成交记录")
    logger.info(f"  python main.py t0-strategy            - 运行一次 {STRATEGY_ENGINE_NAME}")
    logger.info(f"  python main.py t0-daemon              - 持续运行 {STRATEGY_ENGINE_NAME}")
    logger.info("  python main.py t0-sync-position       - 从 QMT 手工同步 T0 仓位")
    logger.info("  python main.py t0-reconcile           - 收盘后校验 T0 持仓与成交")
    logger.info("  python main.py t0-backtest            - 运行 T+0 文件回测")
    logger.info("  python main.py t0-signal-viewer       - 启动 T+0 信号查看器（从 Redis 读取并展示）")
    logger.info("  python main.py export-minute-history  - 导出分钟历史行情")
    logger.info("  python main.py export-minute-daily    - 导出当日分钟行情")
    logger.info("  python main.py cms-check              - 输出 CMS check JSON 结果")
    logger.info("  python main.py cms-server             - 启动独立常驻的 HTTP /health CMS 服务")
    logger.info("")
    logger.info("重试参数（仅适用于 run / test-run）:")
    logger.info("  --max-retries=N                       - 最大重试次数（默认: 3）")
    logger.info("  --retry-delay=N                       - 重试间隔秒数（默认: 60）")
    logger.info("")
    logger.info("示例:")
    logger.info("  python main.py run --max-retries=5 --retry-delay=30")
    logger.info("  python main.py test-run --max-retries=2")
    logger.info("  python main.py cms-check")
    logger.info("  python main.py cms-server --port=8780")


if __name__ == "__main__":
    raise SystemExit(main())
