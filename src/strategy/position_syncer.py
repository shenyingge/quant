"""仓位同步模块 - 从QMT同步持仓到JSON文件"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import settings
from src.logger_config import logger
from src.strategy.core.models import PortfolioState


class PositionSyncer:
    """仓位同步器"""

    def __init__(self, output_dir: str = None):
        self.output_dir = Path(output_dir or settings.t0_output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.position_file = self.output_dir / "position_state.json"

    def sync_from_qmt(self, trader, stock_code: str) -> bool:
        """从QMT同步仓位

        Args:
            trader: QMT交易接口
            stock_code: 股票代码

        Returns:
            是否同步成功
        """
        try:
            # 查询持仓
            position_data = trader.query_position(stock_code)

            if position_data is None:
                logger.warning("QMT查询返回空，保留现有仓位数据")
                return False

            # 构造仓位状态
            position_state = {
                "stock_code": stock_code,
                "total_position": position_data.get("volume", 0),
                "available_volume": position_data.get("can_use_volume", 0),
                "cost_price": position_data.get("open_price", 0),
                "last_sync_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_sync_source": "qmt",
            }

            position_state = self._normalize_position_state(position_state)

            # 保存到文件
            self._save_position(position_state)
            logger.info(f"仓位同步成功: {stock_code}, 持仓={position_state['total_position']}")
            return True

        except Exception as e:
            logger.error(f"仓位同步失败: {e}")
            return False

    def load_position(self) -> Optional[dict]:
        """加载仓位状态

        Returns:
            仓位状态字典或None
        """
        if not self.position_file.exists():
            logger.warning("仓位文件不存在，使用默认值")
            return self._get_default_position()

    def load_portfolio_state(self) -> PortfolioState:
        """加载标准化仓位状态对象。"""
        position = self.load_position() or self._get_default_position()
        return PortfolioState(
            total_position=int(position.get("total_position", 0)),
            available_volume=int(position.get("available_volume", 0)),
            cost_price=float(position.get("cost_price", 0) or 0),
            base_position=int(position.get("base_position", settings.t0_base_position)),
            tactical_position=int(position.get("tactical_position", settings.t0_tactical_position)),
            max_position=int(
                position.get(
                    "max_position",
                    settings.t0_base_position + settings.t0_tactical_position,
                )
            ),
            t0_sell_available=int(position.get("t0_sell_available", 0)),
            t0_buy_capacity=int(position.get("t0_buy_capacity", 0)),
            cash_available=float(position.get("cash_available", 0) or 0),
        )

        try:
            with open(self.position_file, "r", encoding="utf-8") as f:
                position = json.load(f)
            position = self._normalize_position_state(position)
            logger.debug(f"加载仓位: {position.get('stock_code')}")
            return position
        except Exception as e:
            logger.error(f"加载仓位失败: {e}")
            return self._get_default_position()

    def _save_position(self, position: dict):
        """保存仓位到文件"""
        try:
            with open(self.position_file, "w", encoding="utf-8") as f:
                json.dump(position, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存仓位失败: {e}")
            raise

    def _get_default_position(self) -> dict:
        """获取默认仓位配置"""
        return self._normalize_position_state(
            {
                "stock_code": settings.t0_stock_code,
                "total_position": settings.t0_base_position,
                "available_volume": 0,
                "cost_price": 80.0,
                "last_sync_time": None,
                "last_sync_source": "default",
            }
        )

    def _normalize_position_state(self, position: dict) -> dict:
        """补齐底仓/机动仓约束下的可交易容量。"""
        normalized = dict(position)

        total_position = int(normalized.get("total_position") or 0)
        available_volume = int(normalized.get("available_volume") or 0)
        base_position = int(normalized.get("base_position") or settings.t0_base_position)
        tactical_position = int(
            normalized.get("tactical_position") or settings.t0_tactical_position
        )
        max_position = base_position + tactical_position

        normalized["base_position"] = base_position
        normalized["tactical_position"] = tactical_position
        normalized["max_position"] = max_position
        normalized["t0_sell_available"] = self._round_down_lot(
            min(available_volume, max(total_position - base_position, 0))
        )
        normalized["t0_buy_capacity"] = self._round_down_lot(max(max_position - total_position, 0))
        return normalized

    def _round_down_lot(self, volume: int) -> int:
        trade_unit = max(int(settings.t0_trade_unit), 1)
        return max(int(volume) // trade_unit * trade_unit, 0)
