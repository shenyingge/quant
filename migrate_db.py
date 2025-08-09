#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库迁移脚本 - 添加成交通知标记字段
"""

from sqlalchemy import create_engine, text
from src.config import settings
from src.logger_config import configured_logger as logger

def migrate_database():
    """迁移数据库，添加新字段"""
    logger.info("开始数据库迁移...")
    
    try:
        engine = create_engine(settings.db_url)
        
        # 检查 fill_notified 字段是否存在
        with engine.connect() as connection:
            try:
                # 尝试查询新字段，如果不存在会抛出异常
                result = connection.execute(text("SELECT fill_notified FROM order_records LIMIT 1"))
                logger.info("fill_notified 字段已存在，无需迁移")
                return True
            except Exception:
                logger.info("fill_notified 字段不存在，开始添加...")
                
            # 添加新字段
            try:
                connection.execute(text("ALTER TABLE order_records ADD COLUMN fill_notified BOOLEAN DEFAULT FALSE"))
                connection.commit()
                logger.info("✓ 成功添加 fill_notified 字段")
                
                # 更新现有记录：如果已经有成交记录，标记为已通知（避免重复通知）
                connection.execute(text("""
                    UPDATE order_records 
                    SET fill_notified = TRUE 
                    WHERE filled_volume > 0 AND filled_time IS NOT NULL
                """))
                connection.commit()
                logger.info("✓ 已更新现有成交记录的通知状态")
                
                return True
                
            except Exception as e:
                logger.error(f"添加字段失败: {e}")
                return False
                
    except Exception as e:
        logger.error(f"数据库迁移失败: {e}")
        return False

if __name__ == "__main__":
    success = migrate_database()
    if success:
        logger.info("数据库迁移完成")
    else:
        logger.error("数据库迁移失败")
        exit(1)