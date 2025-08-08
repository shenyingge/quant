import time
import threading
from typing import Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
import sys

# 使用统一的日志配置
from src.logger_config import configured_logger as logger

from src.redis_listener import RedisSignalListener
from src.trader import QMTTrader
from src.notifications import FeishuNotifier
from src.database import create_tables, SessionLocal, TradingSignal, OrderRecord
from src.config import settings
from src.backup_service import DatabaseBackupService

class TradingService:
    def __init__(self):
        self.notifier = FeishuNotifier()
        self.trader = QMTTrader(self.notifier)
        self.redis_listener = None
        self.is_running = False
        self.order_monitor_thread = None
        
        # 初始化备份服务
        self.backup_service = DatabaseBackupService()

        # 初始化数据库
        create_tables()
        
        # 注意：日志已经通过 logger_config 统一配置
        # 所有输出会被脚本重定向到 task_execution.log

    def start(self):
        """启动服务"""
        logger.info("正在启动交易服务...")

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

        # 发送服务启动通知
        self.notifier.notify_service_status("已启动", "交易服务成功启动")

        # 开始监听Redis信号（这是阻塞调用）
        try:
            self.redis_listener.start_listening()
        except KeyboardInterrupt:
            logger.info("收到停止信号")
        except Exception as e:
            logger.error(f"服务运行时发生错误: {e}")
            self.notifier.notify_error(str(e), "服务运行")
        finally:
            self.stop()

        return True

    def stop(self):
        """停止服务"""
        if not self.is_running:
            logger.debug("服务已经停止，跳过重复停止操作")
            return
            
        logger.info("正在停止交易服务...")

        self.is_running = False

        if self.redis_listener:
            self.redis_listener.stop()

        if self.trader:
            self.trader.disconnect()
            
        # 停止备份调度器
        if self.backup_service:
            self.backup_service.stop_scheduler()

        # 发送服务停止通知
        self.notifier.notify_service_status("已停止", "交易服务已安全停止")
        logger.info("交易服务已停止")

    def _handle_trading_signal(self, signal_data: Dict[str, Any]):
        """处理交易信号"""
        try:
            logger.info(f"开始处理交易信号: {signal_data}")

            # 验证信号数据 - 使用A股市场常用术语
            required_fields = ['signal_id', 'stock_code', 'direction', 'volume']
            
            # 字段名映射：兼容多种输入格式，统一转换为A股常用术语
            field_mappings = {
                # 信号ID字段
                'order_signal_id': 'signal_id',
                'id': 'signal_id',
                # 证券代码字段  
                'symbol': 'stock_code',
                'code': 'stock_code',
                'instrument': 'stock_code',
                # 买卖方向字段
                'side': 'direction',
                'action': 'direction',
                'order_side': 'direction',
                # 数量字段
                'quantity': 'volume',
                'qty': 'volume',
                'size': 'volume',
                'amount': 'volume',
                # 价格字段
                'order_price': 'price',
                'limit_price': 'price'
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
                existing_signal = db.query(TradingSignal).filter(
                    TradingSignal.signal_id == signal_data['signal_id']
                ).first()

                if existing_signal:
                    logger.warning(f"信号已存在，跳过处理: {signal_data['signal_id']}")
                    return

                # 保存新信号
                trading_signal = TradingSignal(
                    signal_id=signal_data['signal_id'],
                    stock_code=signal_data['stock_code'],
                    direction=signal_data['direction'],
                    volume=signal_data['volume'],
                    price=signal_data.get('price'),
                    signal_time=datetime.utcnow()
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
            self.notifier.notify_error(str(e), f"处理信号: {signal_data.get('signal_id', 'Unknown')}")

    def _execute_trade(self, signal_data: Dict[str, Any], db: Session):
        """执行交易（使用超时保护的同步下单）"""
        try:
            # 使用带超时保护的同步下单
            logger.info(f"执行交易，使用超时保护的同步下单: {signal_data}")
            order_id = self.trader.place_order(signal_data)

            if order_id:
                # 保存订单记录
                order_record = OrderRecord(
                    signal_id=signal_data['signal_id'],
                    order_id=order_id,
                    stock_code=signal_data['stock_code'],
                    direction=signal_data['direction'],
                    volume=signal_data['volume'],
                    price=signal_data.get('price'),
                    order_status="PENDING"
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
                    signal_id=signal_data['signal_id'],
                    order_id=f"FAILED_{int(time.time())}",
                    stock_code=signal_data['stock_code'],
                    direction=signal_data['direction'],
                    volume=signal_data['volume'],
                    price=signal_data.get('price'),
                    order_status="FAILED",
                    error_message="委托失败"
                )
                db.add(order_record)
                db.commit()

                self.notifier.notify_error("下单失败", f"信号ID: {signal_data['signal_id']}")

        except Exception as e:
            logger.error(f"执行交易时发生错误: {e}")
            self.notifier.notify_error(str(e), f"执行交易: {signal_data.get('signal_id', 'Unknown')}")
    
    def _execute_trade_async(self, signal_data: Dict[str, Any], trading_signal):
        """执行异步交易（立即返回，不阻塞）"""
        signal_id = signal_data['signal_id']
        
        def trade_callback(order_id, error):
            """异步交易回调函数"""
            db = SessionLocal()
            try:
                # 重新获取信号记录（因为可能在不同的线程中）
                signal_record = db.query(TradingSignal).filter(
                    TradingSignal.signal_id == signal_id
                ).first()
                
                if not signal_record:
                    logger.error(f"找不到信号记录: {signal_id}")
                    return
                
                if order_id and not error:
                    # 检查是否是序列号，如果是序列号说明还在等待真实order_id
                    if str(order_id).startswith('seq_'):
                        logger.info(f"异步下单已提交，序列号: {order_id}, 信号ID: {signal_id}, 等待真实委托编号...")
                        return  # 不保存到数据库，等待真实order_id回调
                    
                    logger.info(f"异步下单成功，订单ID: {order_id}, 信号ID: {signal_id}")
                    
                    # 检查订单记录是否已存在，避免重复插入
                    existing_record = db.query(OrderRecord).filter(
                        OrderRecord.order_id == str(order_id)
                    ).first()
                    
                    if not existing_record:
                        # 保存订单记录
                        order_record = OrderRecord(
                            signal_id=signal_id,
                            order_id=str(order_id),
                            stock_code=signal_data['stock_code'],
                            direction=signal_data['direction'],
                            volume=signal_data['volume'],
                            price=signal_data.get('price'),
                            order_status="PENDING"
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
                        stock_code=signal_data['stock_code'],
                        direction=signal_data['direction'],
                        volume=signal_data['volume'],
                        price=signal_data.get('price'),
                        order_status="FAILED",
                        error_message=str(error) if error else "异步委托失败"
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
            logger.info(f"提交异步交易任务: {signal_id}, 股票: {signal_data.get('stock_code', 'Unknown')}")
            
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
            self.notifier.notify_error(str(e), f"提交异步交易失败: {signal_data.get('signal_id', 'Unknown')}")

    def _monitor_orders(self):
        """监控订单状态"""
        logger.info("订单监控线程已启动")

        while self.is_running:
            try:
                db = SessionLocal()
                try:
                    # 查询待处理的订单
                    pending_orders = db.query(OrderRecord).filter(
                        OrderRecord.order_status == "PENDING"
                    ).all()

                    for order in pending_orders:
                        order_status = self.trader.get_order_status(order.order_id)

                        if order_status:
                            # 更新订单状态
                            order.order_status = order_status.get('order_status', 'UNKNOWN')
                            filled_volume = order_status.get('filled_volume', 0)
                            if filled_volume > 0:
                                order.fill_quantity = filled_volume
                                order.fill_price = order_status.get('avg_price', 0)
                                order.fill_time = datetime.utcnow()

                                # 如果完全成交，发送通知
                                if order.fill_quantity >= order.volume:
                                    self.notifier.notify_order_filled({
                                        'order_id': order.order_id,
                                        'stock_code': order.stock_code,
                                        'filled_qty': order.fill_quantity,
                                        'avg_price': order.fill_price
                                    })

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

