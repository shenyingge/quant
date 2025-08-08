#!/usr/bin/env python3
"""
交易系统压力测试脚本
"""
import time
import sys
import os
import threading
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.trader import QMTTrader
from src.config import settings
from loguru import logger

def generate_test_signals(count: int):
    """生成测试信号"""
    symbols = [
        '000001.SZ', '000002.SZ', '000858.SZ', '002415.SZ', '000166.SZ',
        '600000.SH', '600036.SH', '600519.SH', '601318.SH', '600276.SH'
    ]
    directions = ['BUY', 'SELL']
    
    signals = []
    for i in range(count):
        signal = {
            'signal_id': f'STRESS_{i:05d}',
            'stock_code': random.choice(symbols),
            'direction': random.choice(directions),
            'volume': random.randint(1, 10) * 100,
            'price': round(random.uniform(0.5, 100.0), 2)
        }
        signals.append(signal)
    
    return signals

def stress_test_concurrent_orders(order_count: int = 50):
    """压力测试并发下单"""
    logger.info(f"=== 压力测试: {order_count} 个并发订单 ===")
    
    trader = QMTTrader()
    
    if not trader.connect():
        logger.error("无法连接QMT，测试退出")
        return
    
    try:
        test_signals = generate_test_signals(order_count)
        
        results = []
        results_lock = threading.Lock()
        start_time = time.time()
        
        def order_callback(order_id, error, signal_info):
            with results_lock:
                end_time = time.time()
                if order_id:
                    results.append({
                        'status': 'success',
                        'signal_id': signal_info['signal_id'],
                        'order_id': order_id,
                        'elapsed': end_time - start_time
                    })
                else:
                    results.append({
                        'status': 'failed',
                        'signal_id': signal_info['signal_id'],
                        'error': str(error),
                        'elapsed': end_time - start_time
                    })
        
        # 批量快速提交
        logger.info("开始批量提交订单...")
        submit_start = time.time()
        
        for i, signal in enumerate(test_signals):
            callback = lambda oid, err, sig=signal: order_callback(oid, err, sig)
            trader.place_order_async(signal, callback)
            
            if (i + 1) % 10 == 0:
                logger.info(f"已提交 {i + 1}/{order_count} 个订单")
        
        submit_time = time.time() - submit_start
        logger.info(f"批量提交完成，耗时: {submit_time:.3f}秒, 速度: {order_count/submit_time:.1f} 订单/秒")
        
        # 监控处理进度
        logger.info("监控处理进度...")
        last_count = 0
        max_wait_time = 120  # 最大等待2分钟
        
        for i in range(max_wait_time):
            current_count = len(results)
            queue_status = trader.get_queue_status()
            
            if current_count != last_count:
                progress = (current_count / order_count) * 100
                logger.info(f"[{i+1}s] 进度: {current_count}/{order_count} ({progress:.1f}%), "
                          f"队列: {queue_status['thread_queue_pending']}")
                last_count = current_count
            
            if current_count >= order_count:
                logger.info("所有订单处理完成")
                break
                
            time.sleep(1)
        
        # 结果分析
        total_time = time.time() - start_time
        success_count = sum(1 for r in results if r['status'] == 'success')
        failed_count = sum(1 for r in results if r['status'] == 'failed')
        
        logger.info("=== 压力测试结果 ===")
        logger.info(f"总订单数: {order_count}")
        logger.info(f"成功订单: {success_count}")
        logger.info(f"失败订单: {failed_count}")
        logger.info(f"未完成: {order_count - len(results)}")
        logger.info(f"成功率: {success_count/order_count*100:.1f}%")
        logger.info(f"总耗时: {total_time:.3f}秒")
        logger.info(f"平均处理速度: {len(results)/total_time:.1f} 订单/秒")
        
        # 性能统计
        if results:
            completion_times = [r['elapsed'] for r in results]
            avg_time = sum(completion_times) / len(completion_times)
            max_time = max(completion_times)
            min_time = min(completion_times)
            
            logger.info(f"平均完成时间: {avg_time:.3f}秒")
            logger.info(f"最快完成时间: {min_time:.3f}秒") 
            logger.info(f"最慢完成时间: {max_time:.3f}秒")
        
        # 显示失败原因统计
        if failed_count > 0:
            error_stats = {}
            for result in results:
                if result['status'] == 'failed':
                    error = result['error']
                    error_stats[error] = error_stats.get(error, 0) + 1
            
            logger.info("失败原因统计:")
            for error, count in error_stats.items():
                logger.info(f"  {error}: {count} 次")
        
        # 最终系统状态
        final_stats = trader.get_trading_stats()
        logger.info(f"系统统计: {final_stats}")
        
    except Exception as e:
        logger.error(f"压力测试异常: {e}")
    finally:
        trader.disconnect()

def stress_test_burst_orders():
    """突发订单压力测试"""
    logger.info("=== 突发订单压力测试 ===")
    
    trader = QMTTrader()
    
    if not trader.connect():
        logger.error("无法连接QMT，测试退出")
        return
    
    try:
        # 模拟突发的大量订单
        bursts = [
            {'name': '第一波', 'count': 20, 'delay': 0},
            {'name': '第二波', 'count': 15, 'delay': 2},
            {'name': '第三波', 'count': 25, 'delay': 1},
            {'name': '第四波', 'count': 10, 'delay': 3}
        ]
        
        total_orders = sum(burst['count'] for burst in bursts)
        results = []
        results_lock = threading.Lock()
        
        def order_callback(order_id, error, signal_info):
            with results_lock:
                timestamp = time.time()
                if order_id:
                    results.append({
                        'timestamp': timestamp,
                        'status': 'success',
                        'signal_id': signal_info['signal_id'],
                        'order_id': order_id
                    })
                else:
                    results.append({
                        'timestamp': timestamp,
                        'status': 'failed',
                        'signal_id': signal_info['signal_id'],
                        'error': str(error)
                    })
        
        # 执行突发订单测试
        logger.info(f"开始突发订单测试，总计 {total_orders} 个订单...")
        start_time = time.time()
        
        def submit_burst(burst_info):
            logger.info(f"提交{burst_info['name']}: {burst_info['count']} 个订单")
            signals = generate_test_signals(burst_info['count'])
            
            for signal in signals:
                callback = lambda oid, err, sig=signal: order_callback(oid, err, sig)
                trader.place_order_async(signal, callback)
        
        # 用线程池模拟突发提交
        with ThreadPoolExecutor(max_workers=4) as executor:
            for i, burst in enumerate(bursts):
                if i > 0:  # 第一波立即提交
                    time.sleep(burst['delay'])
                executor.submit(submit_burst, burst)
        
        # 监控完成情况
        logger.info("监控突发订单处理...")
        for i in range(90):  # 最多等待90秒
            current_count = len(results)
            queue_status = trader.get_queue_status()
            
            if i % 5 == 0:  # 每5秒报告一次
                logger.info(f"[{i}s] 完成: {current_count}/{total_orders}, "
                          f"队列: {queue_status['thread_queue_pending']}")
            
            if current_count >= total_orders:
                break
            time.sleep(1)
        
        # 结果分析
        total_time = time.time() - start_time
        success_count = sum(1 for r in results if r['status'] == 'success')
        
        logger.info("=== 突发订单测试结果 ===")
        logger.info(f"总订单: {total_orders}, 成功: {success_count}, 成功率: {success_count/total_orders*100:.1f}%")
        logger.info(f"总耗时: {total_time:.3f}秒, 平均速度: {len(results)/total_time:.1f} 订单/秒")
        
    except Exception as e:
        logger.error(f"突发订单测试异常: {e}")
    finally:
        trader.disconnect()

def main():
    """主测试函数"""
    logger.info("开始交易系统压力测试")
    
    # 测试1: 50个并发订单
    stress_test_concurrent_orders(50)
    time.sleep(5)
    
    # 测试2: 100个并发订单
    stress_test_concurrent_orders(100)
    time.sleep(5)
    
    # 测试3: 突发订单
    stress_test_burst_orders()
    
    logger.info("压力测试完成")

if __name__ == "__main__":
    main()