import time
import threading
import queue
import concurrent.futures
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from src.logger_config import configured_logger as logger
from sqlalchemy.orm import Session
from concurrent.futures import ThreadPoolExecutor
from src.qmt_constants import OrderStatus, is_filled_status, is_finished_status

from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount
from xtquant import xtconstant
from src.database import TradingSignal, OrderRecord, get_db, SessionLocal
from src.config import settings
from src.redis_client import redis_trade_client
from src.stock_info import get_stock_display_name


class QMTCallback(XtQuantTraderCallback):
    """QMT交易回调处理类"""

    def __init__(self, trader_instance):
        super().__init__()
        self.trader = trader_instance

    def on_disconnected(self):
        """
        连接断开回调
        :return:
        """
        logger.error("QMT连接已断开")
        if hasattr(self.trader, 'notifier') and self.trader.notifier:
            self.trader.notifier.notify_error("QMT连接已断开", "连接状态")
        
        # 标记连接状态
        self.trader.is_connected = False
        
        # 触发重连（如果启用）
        if hasattr(self.trader, 'trigger_reconnect'):
            self.trader.trigger_reconnect()

    def on_stock_order(self, order):
        """
        委托回报推送
        :param order: XtOrder对象
        :return:
        """
        try:
            order_id = getattr(order, 'order_id', '')
            stock_code = getattr(order, 'stock_code', '')
            order_status = getattr(order, 'order_status', '')
            order_sysid = getattr(order, 'order_sysid', '')

            # 创建回调数据的唯一标识
            callback_key = f"stock_order_{order_id}_{order_status}_{order_sysid}"

            # 检查是否是重复回调
            if callback_key in self.trader._last_callback_data:
                logger.debug(f"跳过重复的委托回报: {callback_key}")
                return

            # 记录这次回调，防止重复
            self.trader._last_callback_data[callback_key] = True

            # 清理过期的回调记录（保留最近100个）
            if len(self.trader._last_callback_data) > 100:
                # 删除一半较旧的记录
                keys_to_remove = list(self.trader._last_callback_data.keys())[:50]
                for key in keys_to_remove:
                    del self.trader._last_callback_data[key]

            stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
            logger.info(f"委托回报: 股票{stock_display}, 状态{order_status}, 委托号{order_id}, 系统号{order_sysid}")

            # 更新统计信息
            with self.trader.stats_lock:
                if order_status in ['已报', '已确认']:  # 这些状态表示已提交但未成交
                    self.trader.stats['confirmed_orders'] = self.trader.stats.get('confirmed_orders', 0) + 1
                elif is_filled_status(order_status):
                    self.trader.stats['filled_orders'] = self.trader.stats.get('filled_orders', 0) + 1
                elif order_status in ['已撤销', '废单']:  # 这些状态表示取消或失败
                    self.trader.stats['cancelled_orders'] = self.trader.stats.get('cancelled_orders', 0) + 1

        except Exception as e:
            logger.error(f"委托回报处理异常: {e}")

    def on_stock_trade(self, trade):
        """
        成交变动推送
        :param trade: XtTrade对象
        :return:
        """
        try:
            account_id = getattr(trade, 'account_id', '')
            stock_code = getattr(trade, 'stock_code', '')
            order_id = getattr(trade, 'order_id', '')
            traded_volume = getattr(trade, 'traded_volume', getattr(trade, 'filled_qty', 0))
            traded_price = getattr(trade, 'traded_price', getattr(trade, 'filled_price', 0))
            trade_id = getattr(trade, 'trade_id', f"trade_{int(__import__('time').time())}")
            trade_amount = traded_volume * traded_price

            # 创建回调数据的唯一标识
            callback_key = f"stock_trade_{order_id}_{trade_id}_{traded_volume}_{traded_price}"

            # 检查是否是重复回调
            if callback_key in self.trader._last_callback_data:
                logger.debug(f"跳过重复的成交推送: {callback_key}")
                return

            # 记录这次回调，防止重复
            self.trader._last_callback_data[callback_key] = True

            stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
            logger.info(f"成交推送: 账户{account_id}, 股票{stock_display}, 委托{order_id}, 数量{traded_volume}, 价格{traded_price}, 金额{trade_amount:.2f}")

            # 更新数据库记录并发送成交通知
            try:
                from src.database import SessionLocal, OrderRecord
                from datetime import datetime
                
                db = SessionLocal()
                try:
                    # 查找对应的订单记录
                    order_record = db.query(OrderRecord).filter(
                        OrderRecord.order_id == order_id
                    ).first()
                    
                    if order_record:
                        # 更新成交信息
                        order_record.filled_volume = traded_volume
                        order_record.filled_price = traded_price
                        order_record.filled_time = datetime.utcnow()
                        
                        # 检查是否已经发送过成交通知
                        if not getattr(order_record, 'fill_notified', False):
                            # 发送成交通知
                            if hasattr(self.trader, 'notifier') and self.trader.notifier:
                                stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
                                logger.info(f"QMT回调：订单 {order_id} ({stock_display}) 成交，发送通知")
                                self.trader.notifier.notify_order_filled({
                                    'order_id': order_id,
                                    'stock_code': stock_code,
                                    'filled_qty': traded_volume,
                                    'avg_price': traded_price,
                                    'trade_amount': trade_amount
                                })
                                order_record.fill_notified = True
                        else:
                            stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
                        logger.debug(f"订单 {order_id} ({stock_display}) 已经发送过成交通知，跳过")
                        
                        db.commit()
                    else:
                        stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
                        logger.warning(f"未找到订单记录: {order_id} ({stock_display})")
                        # 如果找不到订单记录，仍然发送通知（可能是手动下单等情况）
                        if hasattr(self.trader, 'notifier') and self.trader.notifier:
                            self.trader.notifier.notify_order_filled({
                                'order_id': order_id,
                                'stock_code': stock_code,
                                'filled_qty': traded_volume,
                                'avg_price': traded_price,
                                'trade_amount': trade_amount
                            })
                finally:
                    db.close()
                    
            except Exception as e:
                logger.error(f"更新订单记录时出错: {e}")
                # 即使更新失败，也发送通知
                if hasattr(self.trader, 'notifier') and self.trader.notifier:
                    self.trader.notifier.notify_order_filled({
                        'order_id': order_id,
                        'stock_code': stock_code,
                        'filled_qty': traded_volume,
                        'avg_price': traded_price,
                        'trade_amount': trade_amount
                    })

            # 更新统计信息
            with self.trader.stats_lock:
                self.trader.stats['total_trade_amount'] = self.trader.stats.get('total_trade_amount', 0) + trade_amount
                self.trader.stats['total_trade_volume'] = self.trader.stats.get('total_trade_volume', 0) + traded_volume

        except Exception as e:
            logger.error(f"成交推送处理异常: {e}")

    def on_order_error(self, order_error):
        """
        委托失败推送
        :param order_error:XtOrderError 对象
        :return:
        """
        try:
            order_id = getattr(order_error, 'order_id', '')
            error_id = getattr(order_error, 'error_id', 0)
            error_msg = getattr(order_error, 'error_msg', '')
            stock_code = getattr(order_error, 'stock_code', '')

            stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
            logger.error(f"委托失败: 委托{order_id}, 股票{stock_display}, 错误码{error_id}, 错误信息: {error_msg}")

            # 发送错误通知
            if hasattr(self.trader, 'notifier') and self.trader.notifier:
                self.trader.notifier.notify_error(
                    f"委托失败: {error_msg}", f"委托{order_id}, 股票{stock_display}"
                )

            # 更新统计信息
            with self.trader.stats_lock:
                self.trader.stats['failed_orders'] = self.trader.stats.get('failed_orders', 0) + 1

            # 从活跃委托列表中移除失败的委托
            with self.trader.order_lock:
                if order_id in self.trader.active_orders:
                    order_info = self.trader.active_orders.pop(order_id)
                    logger.info(f"已移除失败委托 {order_id} 从活跃列表")

                    # 保存失败记录
                    signal_data = order_info.get('signal_data', {})
                    self.trader._save_order_to_redis(order_id, signal_data, 'failed', error_msg)

                    # 调用外部回调，通知失败
                    callback = order_info.get('callback')
                    if callback:
                        callback(None, f"委托失败: {error_msg}")

                # 也检查是否是序列号格式的失败
                else:
                    # 遍历所有active_orders，查找匹配的seq_id
                    for temp_id, order_info in list(self.trader.active_orders.items()):
                        if temp_id.startswith('seq_') and order_info.get('seq_id') == int(order_id) if str(order_id).isdigit() else False:
                            # 找到对应的序列号记录
                            self.trader.active_orders.pop(temp_id)
                            logger.info(f"已移除失败委托序列 {temp_id} 从活跃列表")

                            signal_data = order_info.get('signal_data', {})
                            self.trader._save_order_to_redis(temp_id, signal_data, 'failed', error_msg)

                            # 调用外部回调，通知失败
                            callback = order_info.get('callback')
                            if callback:
                                callback(None, f"委托失败: {error_msg}")
                            break

        except Exception as e:
            logger.error(f"委托错误处理异常: {e}")

    def on_cancel_error(self, cancel_error):
        """
        撤单失败推送
        :param cancel_error: XtCancelError 对象
        :return:
        """
        try:
            order_id = getattr(cancel_error, 'order_id', '')
            error_id = getattr(cancel_error, 'error_id', 0)
            error_msg = getattr(cancel_error, 'error_msg', '')
            stock_code = getattr(cancel_error, 'stock_code', '')

            stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
            logger.error(f"撤单失败: 委托{order_id}, 股票{stock_display}, 错误码{error_id}, 错误信息: {error_msg}")

            # 发送错误通知
            if hasattr(self.trader, 'notifier') and self.trader.notifier:
                self.trader.notifier.notify_error(
                    f"撤单失败: {error_msg}", f"委托{order_id}, 股票{stock_display}"
                )

            # 更新统计信息
            with self.trader.stats_lock:
                self.trader.stats['cancel_failed'] = self.trader.stats.get('cancel_failed', 0) + 1

        except Exception as e:
            logger.error(f"撤单错误处理异常: {e}")

    def on_account_status(self, status):
        """
        账户状态变化回调
        :param status: XtAccountStatus 对象
        :return:
        """
        try:
            account_id = getattr(status, 'account_id', '')
            account_type = getattr(status, 'account_type', '')
            account_status = getattr(status, 'status', '')

            logger.info(f"账户状态变化: 账户{account_id}, 类型{account_type}, 状态{account_status}")

            # 如果账户状态异常，发送通知
            if account_status not in ['正常', '连接', 'CONNECTED', '1']:
                if hasattr(self.trader, 'notifier') and self.trader.notifier:
                    self.trader.notifier.notify_error(
                        f"账户状态异常: {account_status}", f"账户{account_id}"
                    )

            # 更新连接状态
            if account_status in ['正常', '连接', 'CONNECTED', '1']:
                self.trader.is_connected = True
            elif account_status in ['断开', 'DISCONNECTED', '0']:
                self.trader.is_connected = False

        except Exception as e:
            logger.error(f"账户状态处理异常: {e}")

    def on_order_stock_async_response(self, response):
        """异步下单回调"""
        try:
            logger.info(f"异步下单回调: {response.__dict__}")
            # 处理异步下单结果
            order_id = getattr(response, 'order_id', None)
            seq_id = getattr(response, 'seq', None)
            error_id = getattr(response, 'error_id', 0)
            error_msg = getattr(response, 'error_msg', '')

            if error_id == 0 and order_id:
                logger.info(f"异步下单成功，委托编号: {order_id}，序列号: {seq_id}")

                # 更新active_orders，用真实order_id替换序列号
                if seq_id:
                    temp_id = f"seq_{seq_id}"
                    with self.trader.order_lock:
                        if temp_id in self.trader.active_orders:
                            order_info = self.trader.active_orders.pop(temp_id)
                            # 使用真实order_id作为key
                            self.trader.active_orders[str(order_id)] = order_info
                            logger.info(f"委托序列 {seq_id} 已更新为真实委托编号 {order_id}")

                            # 保存成功的委托记录到Redis
                            signal_data = order_info.get('signal_data', {})
                            self.trader._save_order_to_redis(
                                str(order_id), signal_data, 'submitted'
                            )

                            # 调用外部回调，通知TradingService真实的order_id
                            callback = order_info.get('callback')
                            if callback:
                                callback(str(order_id), None)
            else:
                logger.error(f"异步下单失败: {error_msg} (错误代码: {error_id})")

                # 如果失败，移除临时序列号记录并保存失败记录
                if seq_id:
                    temp_id = f"seq_{seq_id}"
                    with self.trader.order_lock:
                        if temp_id in self.trader.active_orders:
                            order_info = self.trader.active_orders.pop(temp_id)
                            logger.info(f"移除失败的委托序列 {seq_id}")

                            # 保存失败的委托记录到Redis
                            signal_data = order_info.get('signal_data', {})
                            self.trader._save_order_to_redis(None, signal_data, 'failed', error_msg)

                            # 调用外部回调，通知失败
                            callback = order_info.get('callback')
                            if callback:
                                callback(None, f"异步下单失败: {error_msg}")

        except Exception as e:
            logger.error(f"异步下单回调异常: {e}")

    def on_cancel_order_stock_async_response(self, response):
        """异步撤单回调"""
        try:
            logger.info(f"异步撤单回调: {response.__dict__}")
            error_id = getattr(response, 'error_id', 0)
            error_msg = getattr(response, 'error_msg', '')

            if error_id == 0:
                logger.info("异步撤单成功")
            else:
                logger.error(f"异步撤单失败: {error_msg} (错误代码: {error_id})")

        except Exception as e:
            logger.error(f"异步撤单回调异常: {e}")

    def on_order_status(self, order_status):
        """委托状态变化回调"""
        try:
            order_id = str(order_status.order_id)
            status = order_status.order_status
            logger.info(f"委托状态变化: {order_id} -> {status}")

            # 更新委托状态记录
            with self.trader.order_lock:
                if order_id in self.trader.active_orders:
                    order_info = self.trader.active_orders[order_id]
                    order_info['last_status'] = status
                    order_info['last_update'] = datetime.now()

                    # 如果委托完成，移除并保存最终记录
                    if is_finished_status(status):
                        order_info = self.trader.active_orders.pop(order_id)
                        logger.info(f"委托 {order_id} 最终状态: {status}，移出活跃列表")

                        # 保存最终状态记录
                        signal_data = order_info.get('signal_data', {})
                        final_status = (
                            'filled'
                            if status == '已成交'  # 保留这个比较，因为需要区分具体的成交状态
                            else 'cancelled' if status == '已撤销' else 'rejected'
                        )

                        # 构建状态更新记录
                        status_record = {
                            'order_id': order_id,
                            'final_status': final_status,
                            'order_status': status,
                            'update_time': datetime.now().isoformat(),
                        }

                        # 如果是成交，添加成交信息
                        if status == '已成交':
                            filled_qty = getattr(
                                order_status, 'filled_qty', getattr(order_status, 'order_volume', 0)
                            )
                            avg_price = getattr(
                                order_status, 'avg_price', getattr(order_status, 'price', 0)
                            )

                            status_record.update(
                                {
                                    'filled_volume': filled_qty,
                                    'avg_price': avg_price,
                                    'stock_code': getattr(
                                        order_status,
                                        'stock_code',
                                        signal_data.get('stock_code', ''),
                                    ),
                                }
                            )

                            # 保存成交记录到Redis
                            self.trader._save_trade_execution_to_redis(order_id, status_record)

                        # 更新委托记录状态到Redis
                        self.trader._save_order_to_redis(order_id, signal_data, final_status)

        except Exception as e:
            logger.error(f"委托状态回调异常: {e}")


class QMTTrader:
    def __init__(self, notifier=None):
        self.session_id = settings.qmt_session_id
        self.is_connected = False
        self.xt_trader = None
        self.account = None
        self.callback = None  # QMT回调对象
        self.notifier = notifier  # 通知器，用于回调中发送通知

        # 添加回调去重机制
        self._last_callback_data = {}  # 缓存最近的回调数据，用于去重

        # 订单跟踪（简化版，主要用于回调处理）
        self.active_orders = (
            {}
        )  # {order_id: {'signal_data': dict, 'timestamp': datetime, 'trades': list}}
        self.order_lock = threading.Lock()

        # 主线程运行xtquant
        self._shutdown = False

        # 异步交易线程池（只处理业务逻辑，xtquant在主线程运行）
        self.trade_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="TradeLogic")

        # 统计信息
        self.stats = {
            'total_orders': 0,  # 总委托数
            'successful_orders': 0,  # 成功委托数
            'failed_orders': 0,  # 失败委托数
            'timeout_orders': 0,  # 超时委托数
            'pending_count': 0,  # 排队中委托数
        }
        self.stats_lock = threading.Lock()
        
        # 重连相关
        self.reconnect_lock = threading.Lock()
        self.reconnect_thread = None
        self.reconnect_attempts = 0
        self.last_connect_time = None

    def connect(self) -> bool:
        """连接QMT"""
        try:
            # 创建回调对象（必须在创建trader之前，确保强引用）
            self.callback = QMTCallback(self)

            # 创建交易对象
            logger.info(f"正在连接QMT，Session ID: {self.session_id}, Path: {settings.qmt_path}")
            # XtQuantTrader需要两个参数：path和session_id（可能作为log_dir）
            self.xt_trader = XtQuantTrader(settings.qmt_path, self.session_id)

            # 尝试注册回调（某些版本可能不支持或返回None）
            try:
                self.xt_trader.register_callback(self.callback)
                logger.info("QMT回调注册成功")
            except AttributeError:
                logger.warning("当前QMT版本不支持register_callback，跳过回调注册")
                logger.info("可能是模拟环境或旧版本QMT，委托可能不会有回调响应")
            except Exception as e:
                logger.warning(f"注册QMT回调异常: {e}，继续连接")

            # 添加回调测试信息
            logger.info(f"回调对象引用: {self.callback is not None}")

            # 启动交易服务
            try:
                self.xt_trader.start()
                logger.info("QMT交易服务启动成功")
            except Exception as e:
                logger.warning(f"启动QMT服务异常: {e}，尝试继续连接")

            # 创建账户对象
            self.account = StockAccount(
                account_id=settings.qmt_account_id,
                # account_type=settings.qmt_account_type
            )

            # 连接QMT
            result = self.xt_trader.connect()
            if result == 0:
                logger.info("QMT连接成功")
                self.is_connected = True
                self.reconnect_attempts = 0  # 重置重连计数
                self.last_connect_time = time.time()
                logger.info(f"QMT账户: {settings.qmt_account_id}")

                # 某些版本的QMT可能需要订阅账户
                try:
                    if hasattr(self.xt_trader, 'subscribe'):
                        subscribe_result = self.xt_trader.subscribe(self.account)
                        if subscribe_result == 0:
                            logger.info("QMT账户订阅成功")
                        else:
                            logger.warning(f"QMT账户订阅失败，错误代码: {subscribe_result}")
                    else:
                        logger.info("当前QMT版本无需显式订阅账户")
                except Exception as e:
                    logger.warning(f"账户订阅异常: {e}")
                    # 不影响主流程，继续执行

                # 连接Redis（用于交易记录存储）
                if settings.redis_trade_records_enabled:
                    redis_connected = redis_trade_client.connect()
                    if redis_connected:
                        logger.info("Redis交易记录存储已启用")
                    else:
                        logger.warning("Redis连接失败，交易记录将仅存储到数据库")

                # xtquant将在主线程中运行，等待run_forever调用
                logger.info("xtquant将在主线程中运行，等待run_forever调用")

                return True
            else:
                logger.error(f"QMT连接失败，错误代码: {result}")
                return False
        except Exception as e:
            logger.error(f"连接QMT时发生错误: {e}")
            return False

    def disconnect(self):
        """断开QMT连接"""
        try:
            self._shutdown = True

            # 停止异步交易线程池
            if hasattr(self, 'trade_executor') and self.trade_executor:
                self.trade_executor.shutdown(wait=True)

            # 停止xtquant
            self._shutdown = True

            # 断开Redis连接
            if settings.redis_trade_records_enabled:
                redis_trade_client.disconnect()

            if self.xt_trader:
                self.xt_trader.stop()
                self.is_connected = False
                logger.info("QMT连接已断开")
        except Exception as e:
            logger.error(f"断开QMT连接时发生错误: {e}")
    
    def trigger_reconnect(self):
        """触发QMT重连"""
        if not settings.auto_reconnect_enabled:
            logger.info("QMT自动重连已禁用")
            return
            
        with self.reconnect_lock:
            # 如果重连线程已在运行，不重复启动
            if self.reconnect_thread and self.reconnect_thread.is_alive():
                logger.debug("QMT重连线程已在运行")
                return
                
            self.reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
            self.reconnect_thread.start()
            logger.info("QMT重连线程已启动")
    
    def _reconnect_loop(self):
        """QMT重连循环"""
        while self.reconnect_attempts < settings.reconnect_max_attempts and not self._shutdown:
            try:
                self.reconnect_attempts += 1
                
                # 计算重连延迟（指数退避）
                delay = min(
                    settings.reconnect_initial_delay * (settings.reconnect_backoff_factor ** (self.reconnect_attempts - 1)),
                    settings.reconnect_max_delay
                )
                
                logger.info(f"QMT第 {self.reconnect_attempts}/{settings.reconnect_max_attempts} 次重连，"
                           f"将在 {delay:.1f} 秒后尝试")
                
                # 等待重连延迟
                for _ in range(int(delay)):
                    if self._shutdown:
                        logger.info("QMT服务停止，取消重连")
                        return
                    time.sleep(1)
                
                if self._shutdown:
                    logger.info("QMT服务停止，取消重连")
                    return
                
                # 尝试重连
                if self.connect():
                    logger.info("QMT重连成功")
                    if self.notifier and hasattr(self.notifier, 'notify_connection_restored'):
                        self.notifier.notify_connection_restored("QMT")
                    return
                else:
                    logger.warning(f"QMT第 {self.reconnect_attempts} 次重连失败")
                    
            except Exception as e:
                logger.error(f"QMT重连异常: {e}")
        
        # 重连失败
        logger.error(f"QMT重连失败，已达到最大尝试次数 {settings.reconnect_max_attempts}")
        
        # 发送重连失败通知
        if self.notifier and hasattr(self.notifier, 'notify_reconnect_failed'):
            self.notifier.notify_reconnect_failed("QMT", self.reconnect_attempts)
    
    def is_healthy(self) -> bool:
        """检查QMT连接健康状态"""
        if not self.is_connected or not self.xt_trader:
            return False
            
        try:
            # 尝试获取账户信息来测试连接
            if hasattr(self.xt_trader, 'query_stock_asset') and self.account:
                result = self.xt_trader.query_stock_asset(self.account)
                return result is not None
            else:
                # 如果没有查询方法，只检查连接状态
                return self.is_connected
        except Exception as e:
            logger.debug(f"QMT健康检查异常: {e}")
            return False

    def place_order(self, signal_data: Dict[str, Any]) -> Optional[str]:
        """下单（同步版本，使用异步线程但等待结果）"""
        if not self.is_connected or not self.xt_trader or not self.account:
            logger.error("QMT未连接或未初始化，无法委托下单")
            return None

        try:
            stock_code = signal_data.get('stock_code', signal_data.get('symbol', '')).strip()
            direction = signal_data.get('direction', signal_data.get('action', '')).upper()
            volume = int(signal_data.get('volume', signal_data.get('quantity', 0)))
            price = signal_data.get('price')

            if not stock_code or not direction or volume <= 0:
                logger.error(f"无效的委托参数: {signal_data}")
                return None

            stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
            logger.info(f"准备委托下单: 证券={stock_display}, 方向={direction}, 数量={volume}, 价格={price}")

            # 使用异步线程池提交任务，但等待结果
            future = self.trade_executor.submit(self._execute_order, signal_data)

            try:
                order_id = future.result(timeout=settings.order_submit_timeout)
                return order_id
            except concurrent.futures.TimeoutError:
                logger.error(f"委托操作超时（{settings.order_submit_timeout}秒）")
                future.cancel()
                return None

        except Exception as e:
            logger.error(f"委托下单时发生错误: {e}")
            return None

    def place_order_async(self, signal_data: Dict[str, Any], callback=None) -> None:
        """异步委托下单"""
        if not self.is_connected or not self.xt_trader or not self.account:
            logger.error("QMT未连接或未初始化，无法委托下单")
            if callback:
                callback(None, "QMT未连接")
            return

        # 更新统计
        with self.stats_lock:
            self.stats['total_orders'] += 1
            self.stats['pending_count'] += 1

        stock_code = signal_data.get('stock_code', signal_data.get('symbol', 'Unknown'))
        direction = signal_data.get('direction', signal_data.get('action', 'Unknown'))
        stock_display = get_stock_display_name(stock_code) if stock_code != 'Unknown' else stock_code
        logger.info(
            f"提交异步委托任务: {stock_display} {direction} [队列中: {self.stats['pending_count']}]"
        )

        def _async_order_callback(future):
            try:
                order_id = future.result()
                with self.stats_lock:
                    self.stats['pending_count'] -= 1
                    if order_id:
                        self.stats['successful_orders'] += 1
                    else:
                        self.stats['failed_orders'] += 1

                if callback:
                    callback(order_id, None if order_id else "下单失败")
            except concurrent.futures.TimeoutError:
                with self.stats_lock:
                    self.stats['pending_count'] -= 1
                    self.stats['timeout_orders'] += 1
                error_msg = f"异步委托超时"
                logger.error(error_msg)
                if callback:
                    callback(None, error_msg)
            except Exception as e:
                with self.stats_lock:
                    self.stats['pending_count'] -= 1
                    self.stats['failed_orders'] += 1
                error_msg = f"异步委托异常: {e}"
                logger.error(error_msg)
                if callback:
                    callback(None, error_msg)

        future = self.trade_executor.submit(self._execute_order, signal_data, callback)
        future.add_done_callback(_async_order_callback)

    def _execute_order(self, signal_data: Dict[str, Any], callback=None) -> Optional[str]:
        """实际执行委托操作（使用passorder）"""
        try:
            stock_code = signal_data.get('stock_code', '').strip()
            direction = signal_data.get('direction', '').upper()
            volume = int(signal_data.get('volume', 0))
            price = signal_data.get('price')

            # 确定市场类型并格式化股票代码
            if stock_code.startswith('6'):
                market = 'SH'  # 上海
                full_stock_code = f"{stock_code}.SH"
            elif stock_code.startswith('8') or (
                stock_code.startswith('4') and len(stock_code) == 6
            ):
                market = 'BJ'  # 北京（新三板精选层/北交所）
                full_stock_code = f"{stock_code}.BJ"
            elif stock_code.startswith(('0', '3')):
                market = 'SZ'  # 深圳
                full_stock_code = f"{stock_code}.SZ"
            else:
                # 默认判断
                market = 'SH'
                full_stock_code = f"{stock_code}.SH"

            # 如果已经包含市场后缀，不重复添加
            if '.' in stock_code:
                full_stock_code = stock_code

            # 转换买卖方向 - 使用xtconstant常量
            if direction == 'BUY':
                xt_direction = xtconstant.STOCK_BUY
            elif direction == 'SELL':
                xt_direction = xtconstant.STOCK_SELL
            else:
                logger.error(f"不支持的交易方向: {direction}")
                return None

            # 价格类型 - 根据交易所和是否有价格来确定
            if price and price > 0:
                # 有价格指定，使用限价
                price_type = xtconstant.FIX_PRICE
                order_price = price
            else:
                # 没有价格指定，根据交易所使用不同的市价单类型
                if market == 'SH' or market == 'BJ':
                    # 上交所/北交所：最优五档即时成交剩余撤销
                    price_type = xtconstant.MARKET_SH_CONVERT_5_CANCEL  # 42
                elif market == 'SZ':
                    # 深交所：即时成交剩余撤销
                    price_type = xtconstant.MARKET_SZ_INSTBUSI_RESTCANCEL  # 46
                    logger.debug(f"深交所市价单类型: MARKET_SZ_INSTBUSI_RESTCANCEL = {xtconstant.MARKET_SZ_INSTBUSI_RESTCANCEL}")
                else:
                    # 默认使用最优五档
                    price_type = xtconstant.MARKET_SH_CONVERT_5_CANCEL
                    logger.warning(f"未知市场 {market}，使用默认市价单类型")

                order_price = 0  # 市价单价格设为0

            stock_display = get_stock_display_name(stock_code) if stock_code else stock_code
            logger.info(
                f"执行委托(order_stock_async): 证券={stock_display}({full_stock_code}), 市场={market}, 方向={direction}({xt_direction}), 数量={volume}, 价格类型={price_type}({price_type}), 价格={order_price}"
            )

            # 添加调试信息，显示xtconstant的实际值
            logger.debug(f"xtconstant values - STOCK_BUY={xtconstant.STOCK_BUY}, STOCK_SELL={xtconstant.STOCK_SELL}, FIX_PRICE={xtconstant.FIX_PRICE}")

            # 使用order_stock_async执行异步委托，避免阻塞
            try:
                # 按照QMT API: order_stock_async(account, stock_code, order_type, order_volume, price_type, price, strategy_name, order_remark)
                seq = self.xt_trader.order_stock_async(
                    self.account,  # 账户对象
                    full_stock_code,  # 证券代码（带市场后缀）
                    xt_direction,  # 买卖方向: STOCK_BUY, STOCK_SELL
                    volume,  # 委托数量
                    price_type,  # 价格类型: FIX_PRICE, MARKET_PRICE
                    order_price,  # 委托价格
                    'auto_trader',  # 策略名称
                    f'Signal_{signal_data.get("signal_id", "unknown")}',  # 订单备注
                )

                # 异步方法返回seq序列号，>0表示成功提交
                if seq and seq > 0:
                    logger.info(f"异步委托提交成功，序列号: {seq}")
                    # 暂时返回序列号作为order_id，实际order_id会在回调中获得
                    order_result = seq
                else:
                    logger.error(f"异步委托提交失败，序列号: {seq}")
                    return None

                # 异步API无需等待，结果会通过回调返回

            except AttributeError as e:
                logger.error(f"order 出错: {e}")
                # 如果没有async版本，使用同步版本但加超时保护
                logger.warning("使用同步order_stock (可能阻塞)")

                import concurrent.futures
                import threading

                # 直接调用同步下单，不使用线程池
                order_result = self.xt_trader.order_stock(
                    account=self.account,
                    stock_code=full_stock_code,  # 使用带市场后缀的股票代码
                    order_type=xt_direction,
                    order_volume=volume,
                    price_type=price_type,
                    price=order_price,
                    strategy_name='auto_trader',
                    order_remark=f'Signal_{signal_data.get("signal_id", "unknown")}',
                )

            # 异步API返回seq序列号，>0表示提交成功
            if order_result and isinstance(order_result, int) and order_result > 0:
                seq_id = order_result
                logger.info(f"异步委托提交成功，序列号: {seq_id}")

                # 使用序列号作为临时ID，实际order_id会在回调中更新
                temp_id = f"seq_{seq_id}"

                # 将委托加入活跃列表，用于回调处理
                with self.order_lock:
                    self.active_orders[temp_id] = {
                        'timestamp': datetime.now(),
                        'signal_data': signal_data,
                        'seq_id': seq_id,  # 保存序列号
                        'trades': [],  # 成交记录列表
                        'total_filled': 0,  # 总成交量
                        'callback': callback,  # 保存外部回调函数
                    }
                logger.info(f"委托序列 {seq_id} 已加入活跃列表")

                # 保存委托记录到Redis（使用临时ID）
                self._save_order_to_redis(temp_id, signal_data, 'submitted')

                return temp_id
            else:
                error_msg = f"委托失败，返回值: {order_result}"
                logger.error(f"委托失败(order_stock): {error_msg}")

                # 保存失败的委托记录到Redis
                self._save_order_to_redis(None, signal_data, 'failed', error_msg)

                return None

        except Exception as e:
            logger.error(f"执行委托时发生错误: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        """撤销委托（异步执行但等待结果）"""
        if not self.xt_trader or not self.account:
            logger.error("QMT未连接或未初始化，无法撤销委托")
            return False

        try:
            # 直接调用撤单方法（在主线程中运行xtquant）
            return self._cancel_order(order_id)

        except Exception as e:
            logger.error(f"撤销委托时发生错误: {e}")
            return False

    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """查询委托状态（异步执行但等待结果）"""
        if not self.xt_trader or not self.account:
            logger.error("QMT未连接或未初始化，无法查询委托状态")
            return None

        try:
            # 直接调用查询方法（在主线程中运行xtquant）
            return self._get_order_status(order_id)

        except Exception as e:
            logger.error(f"查询委托状态时发生错误: {e}")
            return None

    def get_positions(self) -> List[Dict[str, Any]]:
        """获取持仓信息（异步执行但等待结果）"""
        if not self.xt_trader or not self.account:
            logger.error("QMT未连接或未初始化，无法获取持仓")
            return []

        try:
            # 直接调用查询方法（在主线程中运行xtquant）
            return self._get_positions()

        except Exception as e:
            logger.error(f"获取持仓信息时发生错误: {e}")
            return []

    def get_active_orders_count(self) -> int:
        """获取活跃订单数量"""
        with self.order_lock:
            return len(self.active_orders)

    def get_active_orders_info(self) -> List[Dict[str, Any]]:
        """获取活跃委托信息"""
        with self.order_lock:
            return [
                {
                    'order_id': order_id,
                    'signal_data': info.get('signal_data', {}),
                    'timestamp': info['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                    'elapsed_seconds': (datetime.now() - info['timestamp']).total_seconds(),
                    'last_status': info.get('last_status', 'unknown'),
                    'total_filled': info.get('total_filled', 0),
                    'trades_count': len(info.get('trades', [])),
                }
                for order_id, info in self.active_orders.items()
            ]

    def get_trading_stats(self) -> Dict[str, Any]:
        """获取交易统计信息"""
        with self.stats_lock:
            stats = self.stats.copy()

        # 添加成功率和队列状态
        total = stats['total_orders']
        if total > 0:
            stats['success_rate'] = (stats['successful_orders'] / total) * 100
        else:
            stats['success_rate'] = 0

        # 添加线程池状态
        stats['thread_pool_active'] = (
            len(self.trade_executor._threads)
            if hasattr(self.trade_executor, '_threads') and self.trade_executor._threads
            else 0
        )
        stats['thread_pool_max'] = self.trade_executor._max_workers
        stats['xtquant_main_thread'] = True  # xtquant运行在主线程

        return stats

    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        return {
            'active_orders_count': self.get_active_orders_count(),
            'thread_queue_pending': self.stats['pending_count'],
            'total_orders_submitted': self.stats['total_orders'],
            'success_rate': f"{self.get_trading_stats()['success_rate']:.1f}%",
            'xtquant_main_thread': True,
        }

    def _save_order_to_redis(
        self, order_id: str, signal_data: Dict[str, Any], status: str, error_msg: str = None
    ):
        """保存委托记录到Redis"""
        if not settings.redis_trade_records_enabled:
            return

        try:
            # 构建交易记录数据
            trade_record = {
                'order_id': order_id,
                'stock_code': signal_data.get('stock_code', signal_data.get('symbol', '')),
                'direction': signal_data.get('direction', signal_data.get('action', '')),
                'volume': signal_data.get('volume', signal_data.get('quantity', 0)),
                'price': signal_data.get('price', 0),
                'status': status,
                'timestamp': datetime.now().isoformat(),
                'signal_data': signal_data
            }

            # 如果有错误信息，添加到记录中
            if error_msg:
                trade_record['error_message'] = error_msg

            # 使用order_id作为trade_id（后续如果有实际成交记录可以更新）
            trade_id = f"order_{order_id}"

            # 保存到Redis
            success = redis_trade_client.save_trade_record(order_id, trade_id, trade_record)
            if success:
                logger.info(f"委托记录已保存到Redis: {order_id}_{trade_id}")

        except Exception as e:
            logger.error(f"保存委托记录到Redis异常: {e}")

    def _save_trade_execution_to_redis(self, order_id: str, trade_info: Dict[str, Any]):
        """保存成交记录到Redis"""
        if not settings.redis_trade_records_enabled:
            return

        try:
            # 获取实际成交信息
            filled_volume = trade_info.get('filled_volume', trade_info.get('traded_volume', 0))
            avg_price = trade_info.get('avg_price', trade_info.get('traded_price', 0))

            if filled_volume > 0:  # 有成交量才保存
                # 构建成交记录
                execution_record = {
                    'order_id': order_id,
                    'trade_id': f"exec_{order_id}_{int(time.time())}",
                    'stock_code': trade_info.get('stock_code', ''),
                    'filled_volume': filled_volume,
                    'avg_price': avg_price,
                    'trade_amount': filled_volume * avg_price,
                    'execution_time': datetime.now().isoformat(),
                    'order_status': trade_info.get('order_status', ''),
                    'original_trade_info': trade_info
                }

                trade_id = execution_record['trade_id']

                # 保存成交记录到Redis
                success = redis_trade_client.save_trade_record(order_id, trade_id, execution_record)
                if success:
                    logger.info(f"成交记录已保存到Redis: {order_id}_{trade_id} (成交量:{filled_volume}, 成交价:{avg_price})")

        except Exception as e:
            logger.error(f"保存成交记录到Redis异常: {e}")

    def get_redis_trade_records_info(self) -> Dict[str, Any]:
        """获取Redis交易记录信息"""
        if not settings.redis_trade_records_enabled:
            return {'enabled': False, 'message': 'Redis交易记录存储未启用'}

        try:
            count = redis_trade_client.get_trade_records_count()
            return {
                'enabled': True,
                'records_count': count,
                'cleanup_time': settings.redis_trade_cleanup_time,
                'redis_host': settings.redis_host,
                'redis_port': settings.redis_port
            }
        except Exception as e:
            return {'enabled': True, 'error': str(e)}

    def _cancel_order(self, order_id: str) -> bool:
        """撤销委托"""
        try:
            # 如果是序列号格式，无法直接撤单
            if order_id.startswith('seq_'):
                logger.warning(f"无法撤销序列号委托 {order_id}，等待真实order_id")
                return False

            result = self.xt_trader.cancel_order_stock(self.account, int(order_id))

            if result == 0:
                logger.info(f"撤销委托成功，委托编号: {order_id}")
                # 从活跃列表中移除委托
                with self.order_lock:
                    self.active_orders.pop(order_id, None)
                return True
            else:
                logger.error(f"撤销委托失败，委托编号: {order_id}, 错误代码: {result}")
                return False

        except Exception as e:
            logger.error(f"撤单异常: {e}")
            return False

    def _get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """查询委托状态"""
        try:
            # 如果是序列号格式，暂时跳过查询
            if order_id.startswith('seq_'):
                return None

            order = self.xt_trader.query_stock_order(self.account, int(order_id))

            if order:
                return {
                    'order_id': str(order.order_id),
                    'stock_code': order.stock_code,
                    'order_status': order.order_status,
                    'filled_volume': getattr(
                        order, 'filled_qty', getattr(order, 'order_volume', 0)
                    ),
                    'avg_price': getattr(order, 'avg_price', getattr(order, 'price', 0)),
                }
            return None

        except Exception as e:
            logger.error(f"查询委托状态异常: {e}")
            return None

    def _get_positions(self) -> List[Dict[str, Any]]:
        """查询持仓"""
        try:
            positions = self.xt_trader.query_stock_positions(self.account)

            if not positions:
                return []

            return [
                {
                    'stock_code': pos.stock_code,
                    'volume': getattr(pos, 'volume', 0),
                    'available_volume': getattr(pos, 'can_use_volume', 0),
                    'avg_price': getattr(pos, 'avg_price', 0),
                    'market_value': getattr(pos, 'market_value', 0),
                    'account_id': getattr(pos, 'account_id', ''),
                }
                for pos in positions
                if pos
            ]

        except Exception as e:
            logger.error(f"查询持仓异常: {e}")
            return []
