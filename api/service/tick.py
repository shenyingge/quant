from utils.redis import RedisTool
from decimal import Decimal


class TickService:
    def __init__(self, redis_tool: RedisTool):
        self.redis_tool = redis_tool

    def _get_tick(self, symbol: str):
        b_value = self.redis_tool.get(symbol)
        return b_value.decode("utf-8")

    def get_ctp_tick(self, symbol: str):
        tick_str = self._get_tick(symbol)
        tick_list = tick_str.split("|")

        return {
            "TradingDay": tick_list[0],
            "ExchangeID": tick_list[1],
            "LastPrice": Decimal(tick_list[2]),
            "PreSettlementPrice": Decimal(tick_list[3]),
            "PreClosePrice": Decimal(tick_list[4]),
            "PreOpenInterest": Decimal(tick_list[5]),
            "OpenPrice": Decimal(tick_list[6]),
            "HighestPrice": Decimal(tick_list[7]),
            "LowestPrice": Decimal(tick_list[8]),
            "Volume": Decimal(tick_list[9]),
            "Turnover": Decimal(tick_list[10]),
            "OpenInterest": Decimal(tick_list[11]),
            "ClosePrice": Decimal(tick_list[12]),
            "SettlementPrice": Decimal(tick_list[13]),
            "UpperLimitPrice": Decimal(tick_list[14]),
            "LowerLimitPrice": Decimal(tick_list[15]),
            "UpdateTime": tick_list[16],
            "UpdateMillisec": Decimal(tick_list[17]),
            "BidPrice1": Decimal(tick_list[18]),
            "BidVolume1": Decimal(tick_list[19]),
            "AskPrice1": Decimal(tick_list[20]),
            "AskVolume1": Decimal(tick_list[21]),
        }
