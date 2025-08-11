import sys
import threading
import time
from datetime import datetime
from typing import Any, Dict

from schedule import Scheduler
from sqlalchemy.orm import Session

from src.backup_service import DatabaseBackupService
from src.config import settings
from src.connection_manager import ConnectionManager, MultiConnectionManager
from src.daily_pnl_calculator import calculate_daily_summary
from src.database import OrderRecord, SessionLocal, TradingSignal, create_tables

# 使用统一的日志配置
from src.logger_config import configured_logger as logger
from src.notifications import FeishuNotifier
from src.qmt_constants import OrderStatus, get_status_name, is_filled_status, is_finished_status
from src.redis_listener import RedisSignalListener
from src.stock_info import get_stock_display_name
from src.trader import QMTTrader
from src.trading_calendar_manager import initialize_trading_calendar, trading_calendar_manager


class TradingService:
    def __init__(self):
        self.notifier = FeishuNotifier()
        self.trader = QMTTrader(self.notifier)
        self.redis_listener = None
        self.is_running = False
        self.order_monitor_thread = None

        # 初始化备份服务
        self.backup_service = DatabaseBackupService()

        # 初始化盈亏汇总调度器
        self.pnl_scheduler = Scheduler()

        # 初始化数据库
        create_tables()

        # 初始化连接管理器
        self.connection_manager = None
        if settings.auto_reconnect_enabled:
            self._setup_connection_managers()

        # 注意：日志已经通过 logger_config 统一配置
        # 所有输出会被脚本重定向到 task_execution.log

    def start(self):
        """启动服务"""
        logger.info("正在启动交易服务...")

        if settings.auto_reconnect_enabled and self.connection_manager:
            # 使用连接管理器启动连接
            logger.info("使用自动重连机制启动连接...")
            if not self.connection_manager.start_all():
                logger.warning("部分连接启动失败，但已启用自动重连机制")
        else:
            # 传统方式启动连接
            logger.info("使用传统方式启动连接...")

            # 连接QMT
            if not self.trader.connect():
                logger.error("无法连接QMT，服务启动失败")
                self.notifier.notify_error("QMT连接失败", "服务启动")
                return False

            # 初始化Redis监听器
            self.redis_listener = RedisSignalListener(self._handle_trading_signal)

            # 测试Redis连接
            if not self.redis_listener.test_connection():
                logger.error("无法连接Redis，服务启动失败")
                self.notifier.notify_error("Redis连接失败", "服务启动")
                return False

        self.is_running = True

        # 启动订单监控线程
        self.order_monitor_thread = threading.Thread(target=self._monitor_orders)
        self.order_monitor_thread.daemon = True
        self.order_monitor_thread.start()

        # 启动备份调度器
        self.backup_service.start_scheduler()

        # 启动盈亏汇总调度器
        self._setup_pnl_summary_scheduler()

        # 初始化交易日历并设置自动更新
        self._setup_trading_calendar()

        # 发送服务启动通知
        self.notifier.notify_service_status("已启动", "交易服务成功启动")

        # 开始监听Redis信号（这是阻塞调用）
        try:
            if not self.redis_listener:
                self.redis_listener = RedisSignalListener(self._handle_trading_signal)
            self.redis_listener.start_listening()
        except KeyboardInterrupt:
            logger.info("收到停止信号")
        except Exception as e:
            logger.error(f"服务运行时发生错误: {e}")
            self.notifier.notify_error(str(e), "服务运行")
        finally:
            self.stop()

        return True

    def _setup_connection_managers(self):
        """设置连接管理器"""
        try:
            logger.info("设置自动重连管理器...")

            self.connection_manager = MultiConnectionManager()

            # Redis连接管理器
            redis_manager = ConnectionManager(
                name="Redis",
                connect_func=self._connect_redis,
                disconnect_func=self._disconnect_redis,
                health_check_func=self._health_check_redis,
                notifier=self.notifier,
            )
            self.connection_manager.add_connection("Redis", redis_manager)

            # QMT连接管理器
            qmt_manager = ConnectionManager(
                name="QMT",
                connect_func=self._connect_qmt,
                disconnect_func=self._disconnect_qmt,
                health_check_func=self._health_check_qmt,
                notifier=self.notifier,
            )
            self.connection_manager.add_connection("QMT", qmt_manager)

            logger.info("连接管理器设置完成")

        except Exception as e:
            logger.error(f"设置连接管理器失败: {e}")

    def _connect_redis(self) -> bool:
        """连接Redis"""
        try:
            if not self.redis_listener:
                self.redis_listener = RedisSignalListener(self._handle_trading_signal)
            return self.redis_listener.connect()
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            return False

    def _disconnect_redis(self):
        """断开Redis连接"""
        try:
            if self.redis_listener:
                self.redis_listener.disconnect()
        except Exception as e:
            logger.error(f"断开Redis连接失败: {e}")

    def _health_check_redis(self) -> bool:
        """Redis健康检查"""
        try:
            if self.redis_listener:
                return self.redis_listener.test_connection()
            return False
        except Exception as e:
            return False

    def _connect_qmt(self) -> bool:
        """连接QMT"""
        try:
            return self.trader.connect()
        except Exception as e:
            logger.error(f"QMT连接失败: {e}")
            return False

    def _disconnect_qmt(self):
        """断开QMT连接"""
        try:
            self.trader.disconnect()
        except Exception as e:
            logger.error(f"断开QMT连接失败: {e}")

    def _health_check_qmt(self) -> bool:
        """QMT健康检查"""
        try:
            return self.trader.is_healthy()
        except Exception as e:
            logger.debug(f"QMT健康检查失败: {e}")
            return False

    def stop(self):
        """停止服务"""
        if not self.is_running:
            logger.debug("服务已经停止，跳过重复停止操作")
            return

        logger.info("正在停止交易服务...")

        self.is_running = False

        # 停止连接管理器
        if settings.auto_reconnect_enabled and self.connection_manager:
            logger.info("停止连接管理器...")
            self.connection_manager.stop_all()
        else:
            # 传统方式停止连接
            if self.redis_listener:
                self.redis_listener.stop()

            if self.trader:
                self.trader.disconnect()

        # 停止备份调度器
        if self.backup_service:
            self.backup_service.stop_scheduler()

        # 停止盈亏汇总调度器
        if hasattr(self, "pnl_scheduler"):
            # 调度器没有显式的停止方法，但服务停止后线程会自然结束
            pass

        # 发送服务停止通知
        self.notifier.notify_service_status("已停止", "交易服务已安全停止")
        logger.info("交易服务已停止")

    def _handle_trading_signal(self, signal_data: Dict[str, Any]):
        """处理交易信号"""
        try:
            logger.info(f"开始处理交易信号: {signal_data}")

            # 验证信号数据 - 使用A股市场常用术语
            required_fields = ["signal_id", "stock_code", "direction", "volume"]

            # 字段名映射：兼容多种输入格式，统一转换为A股常用术语
            field_mappings = {
                # 信号ID字段
                "order_signal_id": "signal_id",
                "id": "signal_id",
                # 证券代码字段
                "symbol": "stock_code",
                "code": "stock_code",
                "instrument": "stock_code",
                # 买卖方向字段
                "side": "direction",
                "action": "direction",
                "order_side": "direction",
                # 数量字段
                "quantity": "volume",
                "qty": "volume",
                "size": "volume",
                "amount": "volume",
                # 价格字段
                "order_price": "price",
                "limit_price": "price",
            }

            # 转换字段名到A股常用术语
            normalized_data = {}
            for key, value in signal_data.items():
                standard_key = field_mappings.get(key, key)
                normalized_data[standard_key] = value

            # 更新signal_data为标准化后的数据
            signal_data = normalized_data

            for field in required_fields:
                if field not in signal_data:
                    logger.error(f"交易信号缺少必需字段: {field}")
                    return

            # 保存信号到数据库
            db = SessionLocal()
            try:
                # 检查信号是否已处理
                existing_signal = (
                    db.query(TradingSignal)
                    .filter(TradingSignal.signal_id == signal_data["signal_id"])
                    .first()
                )

                if existing_signal:
                    logger.warning(f"信号已存在，跳过处理: {signal_data['signal_id']}")
                    return

                # 保存新信号
                trading_signal = TradingSignal(
                    signal_id=signal_data["signal_id"],
                    stock_code=signal_data["stock_code"],
                    direction=signal_data["direction"],
                    volume=signal_data["volume"],
                    price=signal_data.get("price"),
                    signal_time=datetime.utcnow(),
                )
                db.add(trading_signal)
                db.commit()

                # 发送信号接收通知
                self.notifier.notify_signal_received(signal_data)

                # 异步执行交易（不等待结果，立即处理下一个信号）
                self._execute_trade_async(signal_data, trading_signal)

            finally:
                db.close()

        except Exception as e:
            logger.error(f"处理交易信号时发生错误: {e}")
            self.notifier.notify_error(
                str(e), f"处理信号: {signal_data.get('signal_id', 'Unknown')}"
            )

    def _execute_trade(self, signal_data: Dict[str, Any], db: Session):
        """执行交易（使用超时保护的同步下单）"""
        try:
            # 使用带超时保护的同步下单
            logger.info(f"执行交易，使用超时保护的同步下单: {signal_data}")
            order_id = self.trader.place_order(signal_data)

            if order_id:
                # 保存订单记录
                order_record = OrderRecord(
                    signal_id=signal_data["signal_id"],
                    order_id=order_id,
                    stock_code=signal_data["stock_code"],
                    direction=signal_data["direction"],
                    volume=signal_data["volume"],
                    price=signal_data.get("price"),
                    order_status="PENDING",
                )
                db.add(order_record)
                db.commit()

                # 发送下单成功通知
                self.notifier.notify_order_placed(signal_data, order_id)
                logger.info(f"交易执行成功，订单ID: {order_id}")
            else:
                logger.error("下单失败")
                # 保存失败记录
                order_record = OrderRecord(
                    signal_id=signal_data["signal_id"],
                    order_id=f"FAILED_{int(time.time())}",
                    stock_code=signal_data["stock_code"],
                    direction=signal_data["direction"],
                    volume=signal_data["volume"],
                    price=signal_data.get("price"),
                    order_status="FAILED",
                    error_message="委托失败",
                )
                db.add(order_record)
                db.commit()

                self.notifier.notify_error("下单失败", f"信号ID: {signal_data['signal_id']}")

        except Exception as e:
            logger.error(f"执行交易时发生错误: {e}")
            self.notifier.notify_error(
                str(e), f"执行交易: {signal_data.get('signal_id', 'Unknown')}"
            )

    def _execute_trade_async(self, signal_data: Dict[str, Any], trading_signal):
        """执行异步交易（立即返回，不阻塞）"""
        signal_id = signal_data["signal_id"]

        def trade_callback(order_id, error):
            """异步交易回调函数"""
            db = SessionLocal()
            try:
                # 重新获取信号记录（因为可能在不同的线程中）
                signal_record = (
                    db.query(TradingSignal).filter(TradingSignal.signal_id == signal_id).first()
                )

                if not signal_record:
                    logger.error(f"找不到信号记录: {signal_id}")
                    return

                if order_id and not error:
                    # 检查是否是序列号，如果是序列号说明还在等待真实order_id
                    if str(order_id).startswith("seq_"):
                        logger.info(
                            f"异步下单已提交，序列号: {order_id}, 信号ID: {signal_id}, 等待真实委托编号..."
                        )
                        return  # 不保存到数据库，等待真实order_id回调

                    logger.info(f"异步下单成功，订单ID: {order_id}, 信号ID: {signal_id}")

                    # 检查订单记录是否已存在，避免重复插入
                    existing_record = (
                        db.query(OrderRecord).filter(OrderRecord.order_id == str(order_id)).first()
                    )

                    if not existing_record:
                        # 保存订单记录
                        order_record = OrderRecord(
                            signal_id=signal_id,
                            order_id=str(order_id),
                            stock_code=signal_data["stock_code"],
                            direction=signal_data["direction"],
                            volume=signal_data["volume"],
                            price=signal_data.get("price"),
                            order_status="PENDING",
                        )
                        db.add(order_record)

                        # 标记信号为已处理
                        signal_record.processed = True
                        db.commit()

                        # 发送成功通知
                        self.notifier.notify_order_placed(signal_data, order_id)
                    else:
                        logger.warning(f"订单记录已存在，跳过插入: {order_id}")

                else:
                    logger.error(f"异步下单失败: {error}, 信号ID: {signal_id}")

                    # 保存失败记录
                    order_record = OrderRecord(
                        signal_id=signal_id,
                        order_id=f"FAILED_{int(time.time())}_{signal_id}",  # 确保唯一性
                        stock_code=signal_data["stock_code"],
                        direction=signal_data["direction"],
                        volume=signal_data["volume"],
                        price=signal_data.get("price"),
                        order_status="FAILED",
                        error_message=str(error) if error else "异步委托失败",
                    )
                    db.add(order_record)

                    # 标记信号处理失败但已尝试
                    signal_record.processed = True
                    signal_record.error_message = str(error) if error else "异步下单失败"
                    db.commit()

                    # 发送失败通知
                    self.notifier.notify_error(str(error), f"异步下单失败: {signal_id}")

            except Exception as e:
                logger.error(f"异步交易回调异常: {e}")
                try:
                    db.rollback()
                except:
                    pass
            finally:
                db.close()

        try:
            stock_code = signal_data.get("stock_code", "Unknown")
            stock_display = (
                get_stock_display_name(stock_code) if stock_code != "Unknown" else stock_code
            )
            logger.info(f"提交异步交易任务: {signal_id}, 股票: {stock_display}")

            # 立即提交异步下单任务，不等待结果
            self.trader.place_order_async(signal_data, trade_callback)

            logger.info(f"异步交易任务已提交: {signal_id}")

        except Exception as e:
            logger.error(f"提交异步交易任务失败: {e}")
            # 如果提交任务失败，立即标记信号为处理失败
            try:
                db = SessionLocal()
                trading_signal.processed = True
                trading_signal.error_message = f"提交异步任务失败: {str(e)}"
                db.commit()
                db.close()
            except:
                pass
            self.notifier.notify_error(
                str(e), f"提交异步交易失败: {signal_data.get('signal_id', 'Unknown')}"
            )

    def _setup_trading_calendar(self):
        """设置交易日历和自动更新"""
        try:
            # 初始化交易日历（确保当前年份的数据存在）
            initialize_trading_calendar()

            # 如果是12月，设置定时任务更新下一年的交易日历
            current_month = datetime.now().month
            if current_month == 12:
                # 设置每天检查一次，如果还没更新下一年就更新
                def check_and_update_next_year():
                    while self.is_running:
                        try:
                            next_year = datetime.now().year + 1
                            # 检查是否已有下一年数据
                            db = SessionLocal()
                            from src.database import TradingCalendar

                            count = (
                                db.query(TradingCalendar)
                                .filter(TradingCalendar.year == next_year)
                                .count()
                            )
                            db.close()

                            if count == 0:
                                logger.info(f"检测到12月，自动更新{next_year}年交易日历...")
                                trading_calendar_manager.auto_update_next_year()
                                break  # 更新成功后退出循环
                            else:
                                logger.debug(f"{next_year}年交易日历已存在")
                                break

                        except Exception as e:
                            logger.error(f"自动更新交易日历失败: {e}")

                        # 每天检查一次
                        time.sleep(86400)

                # 启动后台线程进行检查
                update_thread = threading.Thread(target=check_and_update_next_year)
                update_thread.daemon = True
                update_thread.start()
                logger.info("已设置12月交易日历自动更新任务")

        except Exception as e:
            logger.error(f"设置交易日历失败: {e}")
            # 即使交易日历设置失败，也不影响服务启动

    def _monitor_orders(self):
        """监控订单状态"""
        logger.info("订单监控线程已启动")

        while self.is_running:
            try:
                db = SessionLocal()
                try:
                    # 查询需要监控的订单（待处理的和部分成交的）
                    pending_statuses = ["PENDING"] + OrderStatus.get_pending_statuses()
                    pending_orders = (
                        db.query(OrderRecord)
                        .filter(OrderRecord.order_status.in_(pending_statuses))
                        .all()
                    )

                    for order in pending_orders:
                        order_status = self.trader.get_order_status(order.order_id)

                        if order_status:
                            # 更新订单状态
                            current_status = order_status.get("order_status", "UNKNOWN")
                            order.order_status = current_status
                            filled_volume = order_status.get("filled_volume", 0)

                            logger.debug(
                                f"订单 {order.order_id} 状态: {current_status}({get_status_name(current_status) if isinstance(current_status, int) else current_status}), 成交数量: {filled_volume}"
                            )

                            # 检查订单是否有成交
                            # 注意：只有当状态明确表示成交时，才处理成交数量
                            # 避免在非成交状态下错误处理成交数量
                            logger.debug(
                                f"状态检查: {current_status} 是否为成交状态: {is_filled_status(current_status)}"
                            )

                            # 严格检查：状态必须表示成交，且成交数量大于已记录数量
                            has_valid_fill = (
                                is_filled_status(current_status)
                                and filled_volume > 0
                                and filled_volume > (order.filled_volume or 0)
                            )

                            if has_valid_fill:
                                logger.info(
                                    f"订单 {order.order_id} 有新成交: 状态={current_status}({get_status_name(current_status) if isinstance(current_status, int) else current_status}), 成交={filled_volume}"
                                )

                                order.filled_volume = filled_volume
                                order.filled_price = order_status.get("avg_price", 0)
                                order.filled_time = datetime.utcnow()

                                # 如果完全成交且还没发送过成交通知，则发送通知
                                if order.filled_volume >= order.volume and not getattr(
                                    order, "fill_notified", False
                                ):

                                    logger.info(f"订单 {order.order_id} 完全成交，发送通知")
                                    self.notifier.notify_order_filled(
                                        {
                                            "order_id": order.order_id,
                                            "stock_code": order.stock_code,
                                            "filled_qty": order.filled_volume,
                                            "avg_price": order.filled_price,
                                        }
                                    )
                                    order.fill_notified = True
                            else:
                                logger.debug(
                                    f"订单 {order.order_id} 无有效成交: 状态={current_status}({get_status_name(current_status) if isinstance(current_status, int) else current_status}), "
                                    f"成交量={filled_volume}, 已记录成交量={order.filled_volume or 0}"
                                )

                            # 如果订单已完成（成交或取消），更新状态为非PENDING
                            if is_finished_status(current_status):
                                logger.info(
                                    f"订单 {order.order_id} 已完成: {current_status}({get_status_name(current_status) if isinstance(current_status, int) else current_status})"
                                )

                                # 检查是否是超时撤单（支持数字状态码）
                                is_cancelled = (
                                    isinstance(current_status, int)
                                    and current_status == OrderStatus.CANCELED
                                ) or (
                                    isinstance(current_status, str)
                                    and current_status in ["已撤销", "CANCELLED"]
                                )

                                if is_cancelled:
                                    # 检查活跃订单中是否有超时信息
                                    active_order_info = self.trader.active_orders.get(
                                        order.order_id, {}
                                    )
                                    if active_order_info.get("timeout_cancelled"):
                                        order.error_message = "超时自动撤单"
                                        logger.info(f"订单 {order.order_id} 标记为超时撤单")

                            order.updated_at = datetime.utcnow()
                            db.commit()

                finally:
                    db.close()

                # 每30秒检查一次
                time.sleep(30)

            except Exception as e:
                logger.error(f"订单监控时发生错误: {e}")
                time.sleep(30)

        logger.info("订单监控线程已停止")

    def _setup_pnl_summary_scheduler(self):
        """设置盈亏汇总调度器"""
        try:
            # 设置每天下午3:10发送汇总通知
            self.pnl_scheduler.every().day.at("15:10").do(self._send_daily_pnl_summary)

            # 启动调度器线程
            def run_pnl_scheduler():
                logger.info("盈亏汇总调度器已启动，每天15:10发送汇总通知")
                while self.is_running:
                    try:
                        self.pnl_scheduler.run_pending()
                        time.sleep(60)  # 每分钟检查一次
                    except Exception as e:
                        logger.error(f"盈亏汇总调度器运行异常: {e}")
                        time.sleep(60)
                logger.info("盈亏汇总调度器已停止")

            pnl_scheduler_thread = threading.Thread(target=run_pnl_scheduler)
            pnl_scheduler_thread.daemon = True
            pnl_scheduler_thread.start()

            logger.info("盈亏汇总调度器设置完成：每天15:10发送当日交易汇总")

        except Exception as e:
            logger.error(f"设置盈亏汇总调度器失败: {e}")

    def _send_daily_pnl_summary(self):
        """发送当日盈亏汇总通知"""
        try:
            logger.info("开始生成当日盈亏汇总...")

            # 计算当日交易汇总
            pnl_data = calculate_daily_summary()

            if pnl_data:
                # 发送汇总通知
                success = self.notifier.notify_daily_pnl_summary(pnl_data)
                if success:
                    logger.info("当日盈亏汇总通知发送成功")
                else:
                    logger.error("当日盈亏汇总通知发送失败")
            else:
                logger.warning("无法生成当日盈亏汇总数据")

        except Exception as e:
            logger.error(f"发送当日盈亏汇总时发生错误: {e}")
            # 发送错误通知
            try:
                self.notifier.notify_error(f"生成当日盈亏汇总失败: {str(e)}", "定时任务")
            except:
                pass  # 避免通知发送失败导致的递归错误
