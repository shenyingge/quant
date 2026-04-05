import sys
import time
from datetime import date
from typing import List, Optional

from src.config import settings
from src.logger_config import configure_process_logger
from src.logger_config import configured_logger as logger
from src.trading_day_checker import is_trading_day

STRATEGY_ENGINE_NAME = "策略引擎"
TRADING_ENGINE_NAME = "交易引擎"


# ============================================================================
# 辅助函数
# ============================================================================

def parse_retry_params(args: List[str]) -> tuple:
    """解析重试参数"""
    max_retries = 3
    retry_delay = 60

    for arg in args:
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

    return max_retries, retry_delay


def _resolve_qmt_session_id(mode: str) -> int:
    """解析模式对应的 QMT session ID"""
    session_id_map = {
        "trading-service": settings.qmt_session_id_trading_service,
        "t0-daemon": settings.qmt_session_id_t0_daemon,
        "t0-sync": settings.qmt_session_id_t0_sync,
    }
    return session_id_map.get(mode) or settings.qmt_session_id


def _should_skip_non_trading_day(component_name: str) -> bool:
    """检查是否应该跳过非交易日"""
    if is_trading_day():
        return False

    logger.info(f"今天不是交易日，跳过启动 {component_name}")
    return True


# ============================================================================
# 交易引擎命令
# ============================================================================

def run_trading_service(args: List[str]) -> int:
    """启动交易引擎（生产环境）"""
    from src.trading_engine import TradingEngine

    logger.info(f"启动{TRADING_ENGINE_NAME}（控制台模式）...")

    if not is_trading_day():
        logger.info("今天不是交易日，服务将退出")
        logger.info("如需强制运行，请使用: python main.py test-run")
        return 0

    max_retries, retry_delay = parse_retry_params(args)
    retry_count = 0

    while retry_count <= max_retries:
        service = None
        try:
            if retry_count > 0:
                logger.info(f"第 {retry_count}/{max_retries} 次重试启动服务...")

            service = TradingEngine()
            if service.start():
                logger.info("服务正常退出")
                break
            else:
                raise Exception("服务启动失败")

        except KeyboardInterrupt:
            logger.info("收到停止信号，正在退出...")
            break
        except Exception as e:
            logger.error(f"服务运行错误: {e}")
            retry_count += 1

            if retry_count <= max_retries:
                logger.warning(f"服务将在 {retry_delay} 秒后进行第 {retry_count}/{max_retries} 次重试")
                try:
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
    return 0


def run_trading_service_test(args: List[str]) -> int:
    """测试模式运行交易引擎"""
    import os
    from src.trading_engine import TradingEngine

    logger.info(f"启动{TRADING_ENGINE_NAME}（测试模式）...")
    logger.warning("测试模式下检测到非交易日，但仍将继续运行")

    # 临时启用测试模式
    os.environ["TEST_MODE_ENABLED"] = "true"

    max_retries, retry_delay = parse_retry_params(args)
    retry_count = 0

    while retry_count <= max_retries:
        service = None
        try:
            if retry_count > 0:
                logger.info(f"第 {retry_count}/{max_retries} 次重试启动服务...")

            service = TradingEngine()
            if service.start():
                logger.info("服务正常退出")
                break
            else:
                raise Exception("服务启动失败")

        except KeyboardInterrupt:
            logger.info("收到停止信号，正在退出...")
            break
        except Exception as e:
            logger.error(f"服务运行错误: {e}")
            retry_count += 1

            if retry_count <= max_retries:
                logger.warning(f"服务将在 {retry_delay} 秒后进行第 {retry_count}/{max_retries} 次重试")
                try:
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
    return 0


def test_system(args: List[str]) -> int:
    """测试系统连接"""
    from src.redis_listener import RedisSignalListener
    from src.database import SessionLocal, create_tables
    from src.trader import QMTTrader

    logger.info("正在测试系统连接...")

    # 测试 Redis
    listener = RedisSignalListener(lambda x: None)
    redis_ok = listener.test_connection()

    # 测试数据库
    try:
        create_tables()
        db = SessionLocal()
        db.close()
        db_ok = True
        logger.info("数据库连接正常")
    except Exception as e:
        db_ok = False
        logger.error(f"数据库连接失败: {e}")

    # 测试 QMT
    try:
        trader = QMTTrader(session_id=_resolve_qmt_session_id("trading-service"))
        qmt_ok = trader.connect()
        if qmt_ok:
            trader.disconnect()
    except Exception as e:
        qmt_ok = False
        logger.error(f"QMT连接失败: {e}")

    # 输出结果
    logger.info("\n系统测试结果:")
    logger.info(f"Redis: {'OK' if redis_ok else 'FAIL'}")
    logger.info(f"数据库: {'OK' if db_ok else 'FAIL'}")
    logger.info(f"QMT: {'OK' if qmt_ok else 'FAIL'}")

    if redis_ok and db_ok and qmt_ok:
        logger.info("\n所有系统组件正常")
        return 0
    else:
        logger.error("\n系统存在问题，请检查配置")
        return 1


# ============================================================================
# T+0 策略命令
# ============================================================================

def run_t0_daemon(args: List[str]) -> int:
    """启动 T+0 策略守护进程"""
    if _should_skip_non_trading_day(STRATEGY_ENGINE_NAME):
        return 0

    from src.strategy.strategy_engine import StrategyEngine
    from src.notifications import FeishuNotifier

    logger.info(f"启动 {STRATEGY_ENGINE_NAME}")

    poll_interval = max(int(getattr(settings, "t0_poll_interval_seconds", 60)), 1)
    notifier = FeishuNotifier()

    notifier.notify_runtime_event(
        STRATEGY_ENGINE_NAME,
        "启动",
        f"开始轮询策略信号: interval={poll_interval}s",
        "info",
    )

    exit_detail = "守护进程已停止"
    exit_level = "success"

    try:
        strategy_engine = StrategyEngine()

        while True:
            try:
                now = time.localtime()
                if 9 <= now.tm_hour < 15:
                    strategy_engine.run_once()

                # 对齐睡眠
                aligned_sleep = poll_interval - (time.time() % poll_interval)
                if aligned_sleep <= 0 or aligned_sleep > poll_interval:
                    aligned_sleep = poll_interval
                time.sleep(aligned_sleep)

            except KeyboardInterrupt:
                logger.info("收到停止信号")
                exit_detail = "收到停止信号，守护进程正常退出"
                break
            except Exception as e:
                logger.error(f"策略执行异常: {e}")
                notifier.notify_runtime_event(STRATEGY_ENGINE_NAME, "轮询异常", str(e), "error")
                time.sleep(poll_interval)

    except Exception as e:
        logger.error(f"{STRATEGY_ENGINE_NAME} 启动失败: {e}")
        exit_detail = f"启动失败: {e}"
        exit_level = "error"
    finally:
        notifier.notify_runtime_event(STRATEGY_ENGINE_NAME, "停止", exit_detail, exit_level)

    return 0


def run_t0_strategy(args: List[str]) -> int:
    """运行一次 T+0 策略"""
    if _should_skip_non_trading_day(STRATEGY_ENGINE_NAME):
        return 0

    from src.strategy.strategy_engine import StrategyEngine

    logger.info(f"运行 {STRATEGY_ENGINE_NAME} 一次")

    try:
        strategy_engine = StrategyEngine()
        signal_card = strategy_engine.run_once()
        logger.info(f"策略执行完成: {signal_card['signal']['action']}")
        return 0
    except Exception as e:
        logger.error(f"{STRATEGY_ENGINE_NAME} 执行失败: {e}")
        return 1


def sync_t0_position(args: List[str]) -> int:
    """同步 T+0 仓位"""
    if _should_skip_non_trading_day(STRATEGY_ENGINE_NAME):
        return 0

    from src.notifications import FeishuNotifier
    from src.strategy.position_syncer import PositionSyncer
    from src.trader import QMTTrader

    logger.info(f"同步 {STRATEGY_ENGINE_NAME} 仓位")

    session_id = _resolve_qmt_session_id("t0-sync")
    logger.info(f"{STRATEGY_ENGINE_NAME} 仓位同步使用 QMT Session ID: {session_id}")

    connect_retry_attempts = max(int(settings.t0_sync_connect_retry_attempts), 1)
    connect_retry_delay = max(int(settings.t0_sync_connect_retry_delay_seconds), 1)

    trader = None
    connected = False

    try:
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
                time.sleep(connect_retry_delay)

        if not connected:
            logger.error("QMT 连接失败")
            FeishuNotifier().notify_t0_position_sync(
                settings.t0_stock_code,
                False,
                f"QMT 连接失败（已重试 {connect_retry_attempts} 次）",
            )
            return 1

        syncer = PositionSyncer()
        success = syncer.sync_from_qmt(trader, settings.t0_stock_code)

        if success:
            logger.info("仓位同步成功")
            FeishuNotifier().notify_t0_position_sync(
                settings.t0_stock_code, True, "已从 QMT 成功同步仓位"
            )
            return 0
        else:
            logger.error("仓位同步失败")
            FeishuNotifier().notify_t0_position_sync(
                settings.t0_stock_code, False, "同步过程返回失败结果"
            )
            return 1

    except Exception as e:
        logger.error(f"仓位同步失败: {e}")
        FeishuNotifier().notify_t0_position_sync(settings.t0_stock_code, False, f"同步异常: {e}")
        return 1
    finally:
        if trader:
            try:
                trader.disconnect()
            except Exception:
                pass


def reconcile_t0_state(args: List[str]) -> int:
    """收盘对账"""
    if _should_skip_non_trading_day(STRATEGY_ENGINE_NAME):
        return 0

    from src.notifications import FeishuNotifier
    from src.strategy.t0_reconciler import T0Reconciler
    from src.trader import QMTTrader

    logger.info(f"收盘对账 {STRATEGY_ENGINE_NAME}")

    session_id = _resolve_qmt_session_id("t0-sync")
    connect_retry_attempts = max(int(settings.t0_sync_connect_retry_attempts), 1)
    connect_retry_delay = max(int(settings.t0_sync_connect_retry_delay_seconds), 1)

    trader = None
    connected = False

    try:
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
                time.sleep(connect_retry_delay)

        if not connected:
            logger.error("QMT 连接失败，无法执行收盘对账")
            FeishuNotifier().notify_runtime_event(
                STRATEGY_ENGINE_NAME,
                "收盘对账异常",
                f"QMT 连接失败（已重试 {connect_retry_attempts} 次）",
                "warning",
            )
            return 1

        reconciler = T0Reconciler(notifier=FeishuNotifier())
        report = reconciler.run(trader, notify=True)

        if report.get("ok"):
            logger.info("收盘对账通过")
            return 0
        else:
            logger.warning("收盘对账发现异常: {}".format(" | ".join(report.get("issues", []))))
            return 1

    except Exception as e:
        logger.error(f"收盘对账失败: {e}")
        FeishuNotifier().notify_runtime_event(
            STRATEGY_ENGINE_NAME, "收盘对账异常", f"执行异常: {e}", "warning"
        )
        return 1
    finally:
        if trader:
            try:
                trader.disconnect()
            except Exception:
                pass


def run_t0_backtest(args: List[str]) -> int:
    """运行 T+0 回测"""
    from src.backtest.cli import run_backtest_cli

    try:
        return run_backtest_cli(args)
    except SystemExit as exc:
        return exc.code if exc.code not in (0, None) else 0
    except Exception as e:
        logger.error(f"T+0 回测执行失败: {e}")
        return 1


def run_t0_diagnose(args: List[str]) -> int:
    """运行 T+0 策略诊断"""
    from src.strategy.strategy_diagnostics import StrategyDiagnostics

    logger.info("启动 T+0 策略诊断工具")

    try:
        diagnostics = StrategyDiagnostics()
        diagnostics.diagnose()
        return 0
    except Exception as e:
        logger.error(f"策略诊断失败: {e}")
        return 1


# ============================================================================
# 监控命令
# ============================================================================

def run_cms_check(args: List[str]) -> int:
    """CMS 健康检查"""
    import json
    from src.cms_server import ProjectCmsChecker

    logger.remove()
    snapshot = ProjectCmsChecker(scope="project").build_snapshot().to_dict()
    pretty = not args or "--compact" not in args
    print(json.dumps(snapshot, ensure_ascii=False, indent=2 if pretty else None))
    return 0 if snapshot["status"] != "down" else 1


def run_cms_server(args: List[str]) -> int:
    """启动 CMS HTTP 服务"""
    from src.cms_server import serve_cms_server

    host = settings.cms_server_host
    port = settings.cms_server_port

    for arg in args:
        if arg.startswith("--host="):
            host = arg.split("=", 1)[1].strip() or host
        elif arg.startswith("--port="):
            try:
                port = int(arg.split("=", 1)[1].strip())
            except ValueError:
                logger.warning(f"无效的 CMS server 端口参数: {arg}")

    serve_cms_server(host=host, port=port, scope="project")
    return 0


def run_watchdog(args: List[str]) -> int:
    """启动看门狗服务"""
    from src.watchdog_service import run_watchdog_service

    once = False
    dry_run = False

    for arg in args:
        if arg == "--once":
            once = True
        elif arg == "--dry-run":
            dry_run = True

    run_watchdog_service(once=once, dry_run=dry_run)
    return 0


def export_minute_history(args: List[str]) -> int:
    """导出分钟历史行情包"""
    from src.minute_history_exporter import main as export_main

    return export_main(args)


def export_minute_daily(args: List[str]) -> int:
    """按日任务默认参数导出分钟行情包"""
    if not is_trading_day():
        logger.info("今天不是交易日，跳过分钟行情导出")
        return 0

    trade_date = date.today().strftime("%Y%m%d")
    default_args = ["--trade-date", trade_date, "--listed-only", "--overwrite", "--skip-zip"]
    return export_minute_history(default_args + list(args))


def ingest_minute_history(args: List[str]) -> int:
    """将分钟历史行情入库到 Meta DB"""
    from src.minute_history_ingestor import main as ingest_main

    return ingest_main(args)


def ingest_minute_daily(args: List[str]) -> int:
    """按日任务默认参数将当日分钟行情入库"""
    if not is_trading_day():
        logger.info("今天不是交易日，跳过分钟行情入库")
        return 0

    trade_date = date.today().strftime("%Y%m%d")
    default_args = ["--trade-date", trade_date, "--listed-only"]
    return ingest_minute_history(default_args + list(args))


# ============================================================================
# 命令注册表
# ============================================================================

COMMANDS = {
    # 交易引擎
    'run': run_trading_service,
    'test-run': run_trading_service_test,
    'test': test_system,

    # T+0 策略
    't0-daemon': run_t0_daemon,
    't0-strategy': run_t0_strategy,
    't0-sync-position': sync_t0_position,
    't0-reconcile': reconcile_t0_state,
    't0-backtest': run_t0_backtest,
    't0-diagnose': run_t0_diagnose,

    # 监控
    'cms-check': run_cms_check,
    'cms-server': run_cms_server,
    'watchdog': run_watchdog,

    # 分钟行情
    'export-minute-history': export_minute_history,
    'export-minute-daily': export_minute_daily,
    'ingest-minute-history': ingest_minute_history,
    'ingest-minute-daily': ingest_minute_daily,
}


# ============================================================================
# 主函数
# ============================================================================

def _resolve_app_role(command: Optional[str]) -> str:
    """解析命令对应的应用角色（用于日志配置）"""
    role_map = {
        "run": "trading_engine",
        "test-run": "trading_engine",
        "test": "system_test",
        "t0-strategy": "strategy_engine",
        "t0-daemon": "strategy_engine",
        "t0-sync-position": "strategy_engine",
        "t0-reconcile": "strategy_engine",
        "t0-backtest": "strategy_engine",
        "t0-diagnose": "strategy_engine",
        "cms-check": "cms_server",
        "cms-server": "cms_server",
        "watchdog": "watchdog",
        "export-minute-history": "minute_history_export",
        "export-minute-daily": "minute_history_export",
        "ingest-minute-history": "minute_history_ingest",
        "ingest-minute-daily": "minute_history_ingest",
    }
    return role_map.get(command or "", "cli")


def main() -> int:
    """命令行入口"""
    command = sys.argv[1].lower() if len(sys.argv) > 1 else None
    configure_process_logger(_resolve_app_role(command))

    if command != "cms-check":
        logger.info(f"QMT服务 v{settings.__dict__.get('version', '1.0.0')}")
        logger.info("=" * 50)

    if command in COMMANDS:
        try:
            return COMMANDS[command](sys.argv[2:])
        except Exception as e:
            logger.error(f"命令执行失败: {e}")
            return 1
    else:
        print_usage()
        return 1


def print_usage():
    """打印使用说明"""
    logger.info("使用方法:")
    logger.info("")
    logger.info("交易引擎:")
    logger.info(f"  python main.py run                    - 运行 {TRADING_ENGINE_NAME}")
    logger.info(f"  python main.py test-run               - 测试模式运行 {TRADING_ENGINE_NAME}")
    logger.info("  python main.py test                   - 运行系统连接检查")
    logger.info("")
    logger.info("T+0 策略:")
    logger.info(f"  python main.py t0-daemon              - 持续运行 {STRATEGY_ENGINE_NAME}")
    logger.info(f"  python main.py t0-strategy            - 运行一次 {STRATEGY_ENGINE_NAME}")
    logger.info("  python main.py t0-sync-position       - 从 QMT 手工同步 T0 仓位")
    logger.info("  python main.py t0-reconcile           - 收盘后校验 T0 持仓与成交")
    logger.info("  python main.py t0-backtest            - 运行 T+0 文件回测")
    logger.info("  python main.py t0-diagnose            - 运行 T+0 策略诊断工具")
    logger.info("")
    logger.info("监控:")
    logger.info("  python main.py cms-check              - 输出 CMS check JSON 结果")
    logger.info("  python main.py cms-server             - 启动独立常驻的 HTTP /health CMS 服务")
    logger.info("  python main.py watchdog               - 启动 24x7 看门狗服务")
    logger.info("")
    logger.info("分钟行情:")
    logger.info("  python main.py export-minute-history  - 导出分钟历史行情包")
    logger.info("  python main.py export-minute-daily    - 按日任务导出当日分钟行情包")
    logger.info("  python main.py ingest-minute-history  - 分钟历史行情入库")
    logger.info("  python main.py ingest-minute-daily    - 按日任务入库当日分钟行情")
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
