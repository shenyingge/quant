"""
Redis 信号发送模块
用于策略发送交易信号到 Redis，供 QMT 自动交易服务执行
"""

import redis
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
import os


def jq_to_qmt_code(jq_code: str) -> str:
    """
    将聚宽股票代码转换为 QMT 格式
    
    Args:
        jq_code: 聚宽格式代码，如 '000001.XSHE', '600000.XSHG'
        
    Returns:
        QMT 格式代码，如 '000001.SZ', '600000.SH'
    """
    if not jq_code or '.' not in jq_code:
        return jq_code
        
    code, exchange = jq_code.split('.')
    
    # 转换交易所代码
    exchange_map = {
        'XSHE': 'SZ',  # 深圳证券交易所
        'XSHG': 'SH',  # 上海证券交易所
    }
    
    qmt_exchange = exchange_map.get(exchange, exchange)
    return f"{code}.{qmt_exchange}"


def qmt_to_jq_code(qmt_code: str) -> str:
    """
    将 QMT 股票代码转换为聚宽格式
    
    Args:
        qmt_code: QMT 格式代码，如 '000001.SZ', '600000.SH'
        
    Returns:
        聚宽格式代码，如 '000001.XSHE', '600000.XSHG'
    """
    if not qmt_code or '.' not in qmt_code:
        return qmt_code
        
    code, exchange = qmt_code.split('.')
    
    # 转换交易所代码
    exchange_map = {
        'SZ': 'XSHE',  # 深圳证券交易所
        'SH': 'XSHG',  # 上海证券交易所
    }
    
    jq_exchange = exchange_map.get(exchange, exchange)
    return f"{code}.{jq_exchange}"


class RedisSignalSender:
    """Redis 交易信号发送器"""
    
    def __init__(self, 
                 host: str = None,
                 port: int = None,
                 password: str = None,
                 signal_channel: str = None,
                 trade_records_prefix: str = None):
        """
        初始化 Redis 信号发送器
        
        Args:
            host: Redis 服务器地址
            port: Redis 端口
            password: Redis 密码
            signal_channel: 信号发布频道
            trade_records_prefix: 交易记录前缀
        """
        # 从环境变量或参数获取配置
        self.host = host or os.getenv('REDIS_HOST', '10.0.12.2')
        self.port = port or int(os.getenv('REDIS_PORT', '30102'))
        self.password = password or os.getenv('REDIS_PASSWORD', '')
        self.signal_channel = signal_channel or os.getenv('REDIS_SIGNAL_CHANNEL', 'trading_signals')
        self.trade_records_prefix = trade_records_prefix or os.getenv('REDIS_TRADE_RECORDS_PREFIX', 'trade_record:')
        
        # 初始化 Redis 连接
        self.redis_client = None
        self.connect()
        
    def connect(self) -> bool:
        """连接 Redis"""
        try:
            self.redis_client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password if self.password else None,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # 测试连接
            self.redis_client.ping()
            print(f"Redis 连接成功: {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"Redis 连接失败: {e}")
            return False
    
    def send_order_signal(self,
                         stock_code: str,
                         direction: str,
                         volume: int,
                         price: Optional[float] = None,
                         order_type: int = 23,
                         strategy_name: str = "quick_roll",
                         extra: Dict[str, Any] = None) -> str:
        """
        发送交易信号到 Redis
        
        Args:
            stock_code: 股票代码（聚宽格式）
            direction: 交易方向 ('BUY' 或 'SELL')
            volume: 交易数量
            price: 交易价格（None 表示市价）
            order_type: 订单类型（默认 23 为限价单）
            strategy_name: 策略名称
            extra: 额外信息
            
        Returns:
            signal_id: 信号ID
        """
        if not self.redis_client:
            print("Redis 未连接")
            return None
            
        # 转换股票代码格式：聚宽 -> QMT
        qmt_code = jq_to_qmt_code(stock_code)
        
        # 生成唯一信号ID
        signal_id = f"{strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # 构建信号数据（使用 QMT 格式代码）
        signal_data = {
            "signal_id": signal_id,
            "stock_code": qmt_code,  # 使用转换后的 QMT 格式
            "direction": direction.upper(),
            "volume": volume,
            "order_type": order_type,
            "strategy_name": strategy_name,
            "timestamp": datetime.now().isoformat(),
            "jq_code": stock_code,  # 保留原始聚宽格式用于记录
        }
        
        # 添加价格（如果有）
        if price is not None:
            signal_data["price"] = price
            
        # 添加额外信息
        if extra:
            signal_data["extra"] = extra
        
        try:
            # 发布信号到 Redis 频道
            message = json.dumps(signal_data, ensure_ascii=False)
            result = self.redis_client.publish(self.signal_channel, message)
            
            if result > 0:
                print(f"✓ 信号发送成功: {signal_id}")
                print(f"  股票: {stock_code} -> {qmt_code}, 方向: {direction}, 数量: {volume}, 价格: {price}")
                return signal_id
            else:
                print(f"✗ 信号发送失败: 没有订阅者")
                return None
                
        except Exception as e:
            print(f"✗ 发送信号异常: {e}")
            return None
    
    def get_trade_records(self, 
                         date_str: Optional[str] = None,
                         strategy_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取交易记录
        
        Args:
            date_str: 日期字符串 (格式: YYYYMMDD)，默认为今天
            strategy_name: 策略名称筛选
            
        Returns:
            交易记录列表（股票代码转换为聚宽格式）
        """
        if not self.redis_client:
            print("Redis 未连接")
            return []
            
        if date_str is None:
            date_str = datetime.now().strftime('%Y%m%d')
            
        try:
            # 获取所有交易记录键
            pattern = f"{self.trade_records_prefix}*"
            keys = self.redis_client.keys(pattern)
            
            trade_records = []
            for key in keys:
                record_str = self.redis_client.get(key)
                if record_str:
                    record = json.loads(record_str)
                    
                    # 检查日期
                    if 'filled_time' in record:
                        record_date = record['filled_time'][:10].replace('-', '')
                        if record_date != date_str:
                            continue
                    
                    # 检查策略名称
                    if strategy_name and record.get('strategy_name') != strategy_name:
                        continue
                    
                    # 转换股票代码格式：QMT -> 聚宽
                    if 'stock_code' in record:
                        # 优先使用原始的聚宽格式（如果有）
                        if 'jq_code' in record:
                            record['stock_code'] = record['jq_code']
                        else:
                            # 否则转换 QMT 格式到聚宽格式
                            record['stock_code'] = qmt_to_jq_code(record['stock_code'])
                        
                    trade_records.append(record)
            
            print(f"获取到 {len(trade_records)} 条交易记录")
            return trade_records
            
        except Exception as e:
            print(f"获取交易记录失败: {e}")
            return []
    
    def get_filled_orders(self, 
                         signal_ids: List[str] = None,
                         date_str: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        获取已成交的订单
        
        Args:
            signal_ids: 信号ID列表
            date_str: 日期字符串
            
        Returns:
            {signal_id: trade_record} 的字典
        """
        trade_records = self.get_trade_records(date_str)
        
        filled_orders = {}
        for record in trade_records:
            signal_id = record.get('signal_id')
            if signal_ids is None or signal_id in signal_ids:
                filled_orders[signal_id] = record
                
        return filled_orders
    
    def get_today_summary(self, strategy_name: Optional[str] = None) -> Dict[str, Any]:
        """
        获取今日交易汇总
        
        Args:
            strategy_name: 策略名称
            
        Returns:
            交易汇总信息
        """
        trade_records = self.get_trade_records(strategy_name=strategy_name)
        
        summary = {
            'total_trades': len(trade_records),
            'buy_trades': 0,
            'sell_trades': 0,
            'total_buy_amount': 0,
            'total_sell_amount': 0,
            'stocks': set(),
            'details': []
        }
        
        for record in trade_records:
            direction = record.get('direction', '')
            filled_volume = record.get('filled_volume', 0)
            filled_price = record.get('filled_price', 0)
            amount = filled_volume * filled_price
            
            if direction == 'BUY':
                summary['buy_trades'] += 1
                summary['total_buy_amount'] += amount
            elif direction == 'SELL':
                summary['sell_trades'] += 1
                summary['total_sell_amount'] += amount
                
            summary['stocks'].add(record.get('stock_code', ''))
            
            # 添加详细信息
            summary['details'].append({
                'time': record.get('filled_time', ''),
                'stock_code': record.get('stock_code', ''),
                'direction': direction,
                'volume': filled_volume,
                'price': filled_price,
                'amount': amount,
                'signal_id': record.get('signal_id', '')
            })
        
        summary['stocks'] = list(summary['stocks'])
        return summary
    
    def get_positions(self, date_str: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        获取持仓信息（从前一交易日的成交记录推算）
        
        Args:
            date_str: 日期字符串 (格式: YYYYMMDD)，默认为昨天
            
        Returns:
            {stock_code: {'volume': xxx, 'avg_cost': xxx}} 的字典（聚宽格式代码）
        """
        if not self.redis_client:
            print("Redis 未连接")
            return {}
            
        # 如果没有指定日期，使用昨天
        if date_str is None:
            from datetime import timedelta
            yesterday = datetime.now() - timedelta(days=1)
            date_str = yesterday.strftime('%Y%m%d')
            
        try:
            # 获取指定日期的所有成交记录
            positions = {}
            
            # 从 Redis 获取持仓数据（假设有专门的持仓记录）
            position_key = f"positions:{date_str}"
            position_data = self.redis_client.get(position_key)
            
            if position_data:
                positions_raw = json.loads(position_data)
                # 转换股票代码格式：QMT -> 聚宽
                for qmt_code, position_info in positions_raw.items():
                    jq_code = qmt_to_jq_code(qmt_code)
                    positions[jq_code] = position_info
                print(f"获取到 {len(positions)} 个持仓")
            else:
                # 如果没有持仓记录，尝试从成交记录推算
                trade_records = self.get_trade_records(date_str)
                
                for record in trade_records:
                    stock_code = record.get('stock_code')  # 已经是聚宽格式
                    direction = record.get('direction')
                    filled_volume = record.get('filled_volume', 0)
                    filled_price = record.get('filled_price', 0)
                    
                    if not stock_code:
                        continue
                        
                    if stock_code not in positions:
                        positions[stock_code] = {'volume': 0, 'avg_cost': 0, 'total_cost': 0}
                    
                    if direction == 'BUY':
                        # 买入：增加持仓
                        old_volume = positions[stock_code]['volume']
                        old_total_cost = positions[stock_code].get('total_cost', 0)
                        
                        new_volume = old_volume + filled_volume
                        new_total_cost = old_total_cost + filled_volume * filled_price
                        
                        positions[stock_code]['volume'] = new_volume
                        positions[stock_code]['total_cost'] = new_total_cost
                        positions[stock_code]['avg_cost'] = new_total_cost / new_volume if new_volume > 0 else 0
                        
                    elif direction == 'SELL':
                        # 卖出：减少持仓
                        positions[stock_code]['volume'] -= filled_volume
                        if positions[stock_code]['volume'] <= 0:
                            del positions[stock_code]
                
                # 清理无效持仓
                positions = {k: v for k, v in positions.items() if v['volume'] > 0}
                
                print(f"从成交记录推算出 {len(positions)} 个持仓")
            
            return positions
            
        except Exception as e:
            print(f"获取持仓失败: {e}")
            return {}
    
    def disconnect(self):
        """断开 Redis 连接"""
        if self.redis_client:
            self.redis_client.close()
            print("Redis 连接已断开")


# 全局实例
_redis_sender = None


def get_redis_sender() -> RedisSignalSender:
    """获取全局 Redis 发送器实例"""
    global _redis_sender
    if _redis_sender is None:
        _redis_sender = RedisSignalSender()
    return _redis_sender


def send_order_signal(stock_code: str,
                      direction: str,
                      volume: int,
                      price: Optional[float] = None,
                      **kwargs) -> str:
    """
    便捷函数：发送交易信号
    
    Args:
        stock_code: 股票代码
        direction: 交易方向
        volume: 交易数量
        price: 价格
        **kwargs: 其他参数
        
    Returns:
        signal_id: 信号ID
    """
    sender = get_redis_sender()
    return sender.send_order_signal(stock_code, direction, volume, price, **kwargs)


def get_today_trades() -> List[Dict[str, Any]]:
    """便捷函数：获取今日交易记录"""
    sender = get_redis_sender()
    return sender.get_trade_records()


def get_yesterday_positions() -> Dict[str, Dict[str, Any]]:
    """便捷函数：获取昨日持仓"""
    sender = get_redis_sender()
    from datetime import datetime, timedelta
    yesterday = datetime.now() - timedelta(days=1)
    return sender.get_positions(yesterday.strftime('%Y%m%d'))