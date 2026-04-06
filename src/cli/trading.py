from __future__ import annotations

import os
import time
from collections.abc import Callable, Sequence

from src.infrastructure.logger_config import configured_logger as logger
from src.trading.calendar.trading_day_checker import is_trading_day

from src.cli.shared import TRADING_ENGINE_NAME, parse_retry_params, resolve_qmt_session_id


def run_trading_service(
    args: Sequence[str],
    *,
    is_trading_day_fn: Callable[[], bool] = is_trading_day,
    logger_obj=logger,
) -> int:
    """启动交易引擎（生产模式）。"""
    from src.trading.runtime.engine import TradingEngine

    logger_obj.info("启动{}（控制台模式）...", TRADING_ENGINE_NAME)

    if not is_trading_day_fn():
        logger_obj.info("今天不是交易日，服务将退出")
        logger_obj.info("如需强制运行，请使用: python main.py test-run")
        return 0

    max_retries, retry_delay = parse_retry_params(args)
    retry_count = 0

    while retry_count <= max_retries:
        service = None
        try:
            if retry_count > 0:
                logger_obj.info("第 {}/{} 次重试启动服务...", retry_count, max_retries)

            service = TradingEngine()
            if service.start():
                logger_obj.info("服务正常退出")
                break
            raise RuntimeError("服务启动失败")
        except KeyboardInterrupt:
            logger_obj.info("收到停止信号，正在退出...")
            break
        except Exception as exc:
            logger_obj.error("服务运行错误: {}", exc)
            retry_count += 1

            if retry_count <= max_retries:
                logger_obj.warning(
                    "服务将在 {} 秒后进行第 {}/{} 次重试",
                    retry_delay,
                    retry_count,
                    max_retries,
                )
                try:
                    time.sleep(retry_delay)
                except KeyboardInterrupt:
                    logger_obj.info("收到停止信号，取消重试")
                    break
            else:
                logger_obj.error("服务重试 {} 次后仍然失败，停止重试", max_retries)
        finally:
            if service:
                service.stop()

    logger_obj.info("{}已退出", TRADING_ENGINE_NAME)
    return 0


def run_trading_service_test(args: Sequence[str], *, logger_obj=logger) -> int:
    """测试模式运行交易引擎。"""
    from src.trading.runtime.engine import TradingEngine

    logger_obj.info("启动{}（测试模式）...", TRADING_ENGINE_NAME)
    logger_obj.warning("测试模式下检测到非交易日，但仍将继续运行")

    os.environ["TEST_MODE_ENABLED"] = "true"

    max_retries, retry_delay = parse_retry_params(args)
    retry_count = 0

    while retry_count <= max_retries:
        service = None
        try:
            if retry_count > 0:
                logger_obj.info("第 {}/{} 次重试启动服务...", retry_count, max_retries)

            service = TradingEngine()
            if service.start():
                logger_obj.info("服务正常退出")
                break
            raise RuntimeError("服务启动失败")
        except KeyboardInterrupt:
            logger_obj.info("收到停止信号，正在退出...")
            break
        except Exception as exc:
            logger_obj.error("服务运行错误: {}", exc)
            retry_count += 1

            if retry_count <= max_retries:
                logger_obj.warning(
                    "服务将在 {} 秒后进行第 {}/{} 次重试",
                    retry_delay,
                    retry_count,
                    max_retries,
                )
                try:
                    time.sleep(retry_delay)
                except KeyboardInterrupt:
                    logger_obj.info("收到停止信号，取消重试")
                    break
            else:
                logger_obj.error("服务重试 {} 次后仍然失败，停止重试", max_retries)
        finally:
            if service:
                service.stop()

    logger_obj.info("{}已退出", TRADING_ENGINE_NAME)
    return 0


def test_system(args: Sequence[str], *, logger_obj=logger) -> int:
    """测试 Redis、数据库和 QMT 连接。"""
    del args

    from src.infrastructure.db import SessionLocal, create_tables
    from src.infrastructure.redis import RedisSignalListener
    from src.trading.execution.qmt_trader import QMTTrader

    logger_obj.info("正在测试系统连接...")

    listener = RedisSignalListener(lambda _: None)
    redis_ok = listener.test_connection()

    try:
        create_tables()
        db = SessionLocal()
        db.close()
        db_ok = True
        logger_obj.info("数据库连接正常")
    except Exception as exc:
        db_ok = False
        logger_obj.error("数据库连接失败: {}", exc)

    try:
        trader = QMTTrader(session_id=resolve_qmt_session_id("trading-service"))
        qmt_ok = trader.connect()
        if qmt_ok:
            trader.disconnect()
    except Exception as exc:
        qmt_ok = False
        logger_obj.error("QMT连接失败: {}", exc)

    logger_obj.info("\n系统测试结果:")
    logger_obj.info("Redis: {}", "OK" if redis_ok else "FAIL")
    logger_obj.info("数据库: {}", "OK" if db_ok else "FAIL")
    logger_obj.info("QMT: {}", "OK" if qmt_ok else "FAIL")

    if redis_ok and db_ok and qmt_ok:
        logger_obj.info("\n所有系统组件正常")
        return 0

    logger_obj.error("\n系统存在问题，请检查配置")
    return 1
