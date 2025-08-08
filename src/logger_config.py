"""
统一的日志配置模块
"""
import sys
import os
from loguru import logger

# 全局变量，确保只配置一次
_logger_configured = False

def setup_logger():
    """配置全局日志器"""
    global _logger_configured
    
    # 如果已经配置过，直接返回
    if _logger_configured:
        return logger
    
    # 移除所有默认handler
    logger.remove()
    
    # Windows系统需要特殊处理编码
    if sys.platform.startswith('win'):
        # 设置环境变量
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        
        # 尝试重新配置stdout/stderr编码
        if hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8')
            except:
                pass
        if hasattr(sys.stderr, 'reconfigure'):
            try:
                sys.stderr.reconfigure(encoding='utf-8')
            except:
                pass
    
    # 统一使用无颜色格式（因为输出被重定向到文件）
    log_format = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"
    
    # 只添加一个handler到stdout，避免重复
    # 包含所有级别的日志
    logger.add(
        sys.stdout,
        format=log_format,
        level="DEBUG",  # 设置为DEBUG以捕获所有日志
        enqueue=True,   # 使用队列，避免多线程问题
        backtrace=False,  # 不显示完整的错误堆栈
        diagnose=False   # 不显示诊断信息
    )
    
    _logger_configured = True
    return logger

# 在模块导入时自动配置
configured_logger = setup_logger()