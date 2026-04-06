#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""股票信息查询模块"""

import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

from sqlalchemy.orm import Session

from src.infrastructure.db import SessionLocal, StockInfo
from src.infrastructure.logger_config import configured_logger as logger


class StockInfoCache:
    """股票信息缓存（基于数据库）"""

    def __init__(self):
        self._lock = threading.Lock()
        self._cache_timeout = 24 * 3600  # 缓存24小时

    def get_stock_name(self, stock_code: str) -> str:
        """获取股票名称"""
        if not stock_code:
            return "未知股票"

        # 清理股票代码
        stock_code = str(stock_code).strip()
        normalized_code = self._normalize_stock_code(stock_code)

        db = SessionLocal()
        try:
            # 从数据库查询股票信息
            stock_info = db.query(StockInfo).filter(StockInfo.stock_code == normalized_code).first()

            # 如果数据库中有记录且未过期
            if stock_info:
                # 检查是否需要更新（24小时过期）
                if datetime.utcnow() - stock_info.updated_at < timedelta(hours=24):
                    return stock_info.stock_name

            # 尝试从akshare获取股票信息
            name = self._fetch_stock_info_from_akshare(normalized_code)
            if name:
                # 更新或插入数据库
                if stock_info:
                    stock_info.stock_name = name
                    stock_info.updated_at = datetime.utcnow()
                else:
                    stock_info = StockInfo(
                        stock_code=normalized_code,
                        stock_name=name,
                        market=self._extract_market(normalized_code),
                    )
                    db.add(stock_info)

                db.commit()
                return name

            # 如果akshare也获取失败，返回已有数据或默认值
            if stock_info:
                return stock_info.stock_name

            # 最后返回默认格式
            pure_code = normalized_code.split(".")[0]
            return f"股票{pure_code}"

        except Exception as e:
            logger.error(f"获取股票名称失败 {stock_code}: {e}")
            pure_code = normalized_code.split(".")[0] if "." in normalized_code else normalized_code
            return f"股票{pure_code}"
        finally:
            db.close()

    def _normalize_stock_code(self, stock_code: str) -> str:
        """规范化股票代码，确保有市场后缀"""
        if "." in stock_code:
            return stock_code.upper()

        # 根据代码前缀推断市场
        if stock_code.startswith(("000", "002", "003", "300")):
            return f"{stock_code}.SZ"
        elif stock_code.startswith(("600", "601", "603", "605", "688")):
            return f"{stock_code}.SH"
        else:
            # 默认深圳
            return f"{stock_code}.SZ"

    def _extract_market(self, stock_code: str) -> str:
        """从股票代码提取市场"""
        if stock_code.endswith(".SH"):
            return "SH"
        elif stock_code.endswith(".SZ"):
            return "SZ"
        return "SZ"  # 默认

    def _fetch_stock_info_from_akshare(self, stock_code: str) -> Optional[str]:
        """从akshare获取股票信息"""
        try:
            import akshare as ak

            # 获取股票基本信息
            # 使用akshare的股票信息接口
            pure_code = stock_code.split(".")[0]

            # 尝试获取个股信息
            try:
                # 获取股票基本信息
                stock_info_df = ak.stock_individual_info_em(symbol=pure_code)
                if not stock_info_df.empty:
                    # 查找股票名称
                    for _, row in stock_info_df.iterrows():
                        if row["item"] == "股票简称":
                            return row["value"]
                        elif row["item"] == "股票名称":
                            return row["value"]
            except:
                pass

            # 备用方法：从实时行情获取
            try:
                # 获取实时行情数据
                df = ak.stock_zh_a_spot_em()
                stock_row = df[df["代码"] == pure_code]
                if not stock_row.empty:
                    return stock_row.iloc[0]["名称"]
            except:
                pass

            logger.debug(f"akshare未找到股票信息: {stock_code}")
            return None

        except ImportError:
            logger.warning("akshare未安装，无法获取股票信息")
            return None
        except Exception as e:
            logger.debug(f"从akshare获取股票信息失败 {stock_code}: {e}")
            return None

    def get_stock_display_name(self, stock_code: str) -> str:
        """获取股票显示名称（代码+名称）"""
        name = self.get_stock_name(stock_code)
        pure_code = stock_code.split(".")[0] if "." in stock_code else stock_code
        if name and not name.startswith(f"股票"):
            return f"{stock_code}({name})"
        return stock_code

    def update_stock_name(self, stock_code: str, name: str):
        """手动更新股票名称"""
        normalized_code = self._normalize_stock_code(stock_code)

        db = SessionLocal()
        try:
            stock_info = db.query(StockInfo).filter(StockInfo.stock_code == normalized_code).first()

            if stock_info:
                stock_info.stock_name = name
                stock_info.updated_at = datetime.utcnow()
            else:
                stock_info = StockInfo(
                    stock_code=normalized_code,
                    stock_name=name,
                    market=self._extract_market(normalized_code),
                )
                db.add(stock_info)

            db.commit()
            logger.info(f"更新股票名称: {normalized_code} -> {name}")
        except Exception as e:
            logger.error(f"更新股票名称失败: {e}")
            db.rollback()
        finally:
            db.close()

    def clear_cache(self):
        """清空数据库缓存"""
        db = SessionLocal()
        try:
            db.query(StockInfo).delete()
            db.commit()
            logger.info("股票名称缓存已清空")
        except Exception as e:
            logger.error(f"清空股票缓存失败: {e}")
            db.rollback()
        finally:
            db.close()

    def get_cache_stats(self) -> Dict[str, any]:
        """获取缓存统计信息"""
        db = SessionLocal()
        try:
            total_count = db.query(StockInfo).count()
            # 统计24小时内更新的记录
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            valid_count = db.query(StockInfo).filter(StockInfo.updated_at > cutoff_time).count()

            return {
                "total_cached": total_count,
                "valid_cached": valid_count,
                "expired_cached": total_count - valid_count,
                "cache_timeout_hours": 24,
            }
        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return {
                "total_cached": 0,
                "valid_cached": 0,
                "expired_cached": 0,
                "cache_timeout_hours": 24,
            }
        finally:
            db.close()

    def bulk_update_stock_info(self, batch_size: int = 100) -> int:
        """批量更新股票信息"""
        db = SessionLocal()
        updated_count = 0
        try:
            import akshare as ak

            # 获取所有A股基本信息
            logger.info("开始批量获取股票信息...")
            df = ak.stock_zh_a_spot_em()

            for i, (_, row) in enumerate(df.iterrows()):
                if i % batch_size == 0 and i > 0:
                    db.commit()
                    logger.info(f"已处理 {i} 条股票信息")

                code = row["代码"]
                name = row["名称"]
                normalized_code = self._normalize_stock_code(code)

                stock_info = (
                    db.query(StockInfo).filter(StockInfo.stock_code == normalized_code).first()
                )

                if stock_info:
                    if stock_info.stock_name != name:
                        stock_info.stock_name = name
                        stock_info.updated_at = datetime.utcnow()
                        updated_count += 1
                else:
                    stock_info = StockInfo(
                        stock_code=normalized_code,
                        stock_name=name,
                        market=self._extract_market(normalized_code),
                    )
                    db.add(stock_info)
                    updated_count += 1

            db.commit()
            logger.info(f"批量更新完成，共更新 {updated_count} 条股票信息")
            return updated_count

        except ImportError:
            logger.error("akshare未安装，无法批量更新股票信息")
            return 0
        except Exception as e:
            logger.error(f"批量更新股票信息失败: {e}")
            db.rollback()
            return 0
        finally:
            db.close()


# 全局股票信息缓存实例
stock_info_cache = StockInfoCache()


def get_stock_name(stock_code: str) -> str:
    """获取股票名称的便捷函数"""
    return stock_info_cache.get_stock_name(stock_code)


def get_stock_display_name(stock_code: str) -> str:
    """获取股票显示名称的便捷函数"""
    return stock_info_cache.get_stock_display_name(stock_code)
