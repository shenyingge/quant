from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from src.infrastructure.config import settings
from src.infrastructure.logger_config import configured_logger as logger

from src.cli.shared import (
    STRATEGY_ENGINE_NAME,
    get_t0_poll_interval_seconds,
    resolve_qmt_session_id,
    should_skip_non_trading_day,
)


def run_t0_daemon(
    args: Sequence[str],
    *,
    should_skip_non_trading_day_fn: Callable[[str], bool] = should_skip_non_trading_day,
    get_t0_poll_interval_seconds_fn: Callable[[], int] = get_t0_poll_interval_seconds,
    logger_obj=logger,
    time_module=time,
) -> int:
    """启动 T+0 策略守护进程。"""
    del args

    if should_skip_non_trading_day_fn(STRATEGY_ENGINE_NAME):
        return 0

    from src.infrastructure.notifications import FeishuNotifier
    from src.strategy.strategy_engine import StrategyEngine

    logger_obj.info("启动 {}", STRATEGY_ENGINE_NAME)

    poll_interval = get_t0_poll_interval_seconds_fn()
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
                now = time_module.localtime()
                if 9 <= now.tm_hour < 15:
                    strategy_engine.run_once()

                aligned_sleep = poll_interval - (time_module.time() % poll_interval)
                if aligned_sleep <= 0 or aligned_sleep > poll_interval:
                    aligned_sleep = poll_interval
                time_module.sleep(aligned_sleep)
            except KeyboardInterrupt:
                logger_obj.info("收到停止信号")
                exit_detail = "收到停止信号，守护进程正常退出"
                break
            except Exception as exc:
                logger_obj.error("策略执行异常: {}", exc)
                notifier.notify_runtime_event(STRATEGY_ENGINE_NAME, "轮询异常", str(exc), "error")
                time_module.sleep(poll_interval)
    except Exception as exc:
        logger_obj.error("{} 启动失败: {}", STRATEGY_ENGINE_NAME, exc)
        exit_detail = f"启动失败: {exc}"
        exit_level = "error"
    finally:
        notifier.notify_runtime_event(STRATEGY_ENGINE_NAME, "停止", exit_detail, exit_level)

    return 0


def run_t0_strategy(
    args: Sequence[str] | None = None,
    *,
    should_skip_non_trading_day_fn: Callable[[str], bool] = should_skip_non_trading_day,
    logger_obj=logger,
) -> int:
    """运行一次 T+0 策略。"""
    del args

    if should_skip_non_trading_day_fn(STRATEGY_ENGINE_NAME):
        return 0

    from src.strategy.strategy_engine import StrategyEngine

    logger_obj.info("运行 {} 一次", STRATEGY_ENGINE_NAME)

    try:
        strategy_engine = StrategyEngine()
        signal_card = strategy_engine.run_once()
        logger_obj.info("策略执行完成: {}", signal_card["signal"]["action"])
        return 0
    except Exception as exc:
        logger_obj.error("{} 执行失败: {}", STRATEGY_ENGINE_NAME, exc)
        return 1


def sync_t0_position(
    args: Sequence[str],
    *,
    should_skip_non_trading_day_fn: Callable[[str], bool] = should_skip_non_trading_day,
    resolve_qmt_session_id_fn: Callable[[str], int] = resolve_qmt_session_id,
    settings_obj: object = settings,
    logger_obj=logger,
    time_module=time,
) -> int:
    """同步 T+0 仓位。"""
    if should_skip_non_trading_day_fn(STRATEGY_ENGINE_NAME):
        return 0

    from src.infrastructure.notifications import FeishuNotifier
    from src.strategy.position_syncer import PositionSyncer
    from src.trading.execution.qmt_trader import QMTTrader

    del args

    logger_obj.info("同步 {} 仓位", STRATEGY_ENGINE_NAME)

    session_id = resolve_qmt_session_id_fn("t0-sync")
    logger_obj.info("{} 仓位同步使用 QMT Session ID: {}", STRATEGY_ENGINE_NAME, session_id)

    connect_retry_attempts = max(int(getattr(settings_obj, "t0_sync_connect_retry_attempts")), 1)
    connect_retry_delay = max(int(getattr(settings_obj, "t0_sync_connect_retry_delay_seconds")), 1)

    trader = None
    connected = False

    try:
        for attempt in range(1, connect_retry_attempts + 1):
            trader = QMTTrader(session_id=session_id)
            if trader.connect():
                connected = True
                break

            logger_obj.warning(
                "QMT 连接失败，仓位同步重试 {}/{}",
                attempt,
                connect_retry_attempts,
            )
            try:
                trader.disconnect()
            except Exception:
                pass

            if attempt < connect_retry_attempts:
                time_module.sleep(connect_retry_delay)

        if not connected:
            logger_obj.error("QMT 连接失败")
            FeishuNotifier().notify_t0_position_sync(
                getattr(settings_obj, "t0_stock_code"),
                False,
                f"QMT 连接失败（已重试 {connect_retry_attempts} 次）",
            )
            return 1

        syncer = PositionSyncer()
        success = syncer.sync_from_qmt(trader, getattr(settings_obj, "t0_stock_code"))

        if success:
            logger_obj.info("仓位同步成功")
            FeishuNotifier().notify_t0_position_sync(
                getattr(settings_obj, "t0_stock_code"),
                True,
                "已从 QMT 成功同步仓位",
            )
            return 0

        logger_obj.error("仓位同步失败")
        FeishuNotifier().notify_t0_position_sync(
            getattr(settings_obj, "t0_stock_code"),
            False,
            "同步过程返回失败结果",
        )
        return 1
    except Exception as exc:
        logger_obj.error("仓位同步失败: {}", exc)
        FeishuNotifier().notify_t0_position_sync(
            getattr(settings_obj, "t0_stock_code"),
            False,
            f"同步异常: {exc}",
        )
        return 1
    finally:
        if trader:
            try:
                trader.disconnect()
            except Exception:
                pass


def reconcile_t0_state(
    args: Sequence[str],
    *,
    should_skip_non_trading_day_fn: Callable[[str], bool] = should_skip_non_trading_day,
    resolve_qmt_session_id_fn: Callable[[str], int] = resolve_qmt_session_id,
    settings_obj: object = settings,
    logger_obj=logger,
    time_module=time,
) -> int:
    """执行收盘对账。"""
    if should_skip_non_trading_day_fn(STRATEGY_ENGINE_NAME):
        return 0

    from src.infrastructure.notifications import FeishuNotifier
    from src.strategy.t0_reconciler import T0Reconciler
    from src.trading.execution.qmt_trader import QMTTrader

    del args

    logger_obj.info("收盘对账 {}", STRATEGY_ENGINE_NAME)

    session_id = resolve_qmt_session_id_fn("t0-sync")
    connect_retry_attempts = max(int(getattr(settings_obj, "t0_sync_connect_retry_attempts")), 1)
    connect_retry_delay = max(int(getattr(settings_obj, "t0_sync_connect_retry_delay_seconds")), 1)

    trader = None
    connected = False

    try:
        for attempt in range(1, connect_retry_attempts + 1):
            trader = QMTTrader(session_id=session_id)
            if trader.connect():
                connected = True
                break

            logger_obj.warning(
                "QMT 收盘对账连接失败，重试 {}/{}",
                attempt,
                connect_retry_attempts,
            )
            try:
                trader.disconnect()
            except Exception:
                pass

            if attempt < connect_retry_attempts:
                time_module.sleep(connect_retry_delay)

        if not connected:
            logger_obj.error("QMT 连接失败，无法执行收盘对账")
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
            logger_obj.info("收盘对账通过")
            return 0

        logger_obj.warning("收盘对账发现异常: {}", " | ".join(report.get("issues", [])))
        return 1
    except Exception as exc:
        logger_obj.error("收盘对账失败: {}", exc)
        FeishuNotifier().notify_runtime_event(
            STRATEGY_ENGINE_NAME,
            "收盘对账异常",
            f"执行异常: {exc}",
            "warning",
        )
        return 1
    finally:
        if trader:
            try:
                trader.disconnect()
            except Exception:
                pass


def run_t0_backtest(args: Sequence[str], *, logger_obj=logger) -> int:
    """运行 T+0 文件回测。"""
    from src.backtest.cli import run_backtest_cli

    try:
        return run_backtest_cli(list(args))
    except SystemExit as exc:
        return exc.code if exc.code not in (0, None) else 0
    except Exception as exc:
        logger_obj.error("T+0 回测执行失败: {}", exc)
        return 1


def run_t0_diagnose(args: Sequence[str], *, logger_obj=logger) -> int:
    """运行 T+0 策略诊断。"""
    from src.strategy.strategy_diagnostics import StrategyDiagnostics

    del args

    logger_obj.info("启动 T+0 策略诊断工具")

    try:
        diagnostics = StrategyDiagnostics()
        diagnostics.diagnose()
        return 0
    except Exception as exc:
        logger_obj.error("策略诊断失败: {}", exc)
        return 1
