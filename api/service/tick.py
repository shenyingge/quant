from utils.redis import RedisTool
from decimal import Decimal


class TickService:
    def __init__(self, redis_tool: RedisTool):
        self.redis_tool = redis_tool

    def _get_tick(self, symbol: str):
        return self.redis_tool.get(symbol)

    def get_ctp_tick(self, symbol: str):
        tick_str = self._get_tick(symbol)
        """
            std::string redis_message = std::string(pDepthMarketData->TradingDay) + std::string("|") + std::string(pDepthMarketData->ExchangeID) + std::string("|") + std::to_string(pDepthMarketData->LastPrice) + std::string("|") + std::to_string(pDepthMarketData->PreSettlementPrice) + std::string("|") + std::to_string(pDepthMarketData->PreClosePrice) + std::string("|") + std::to_string(pDepthMarketData->PreOpenInterest) + std::string("|") + std::to_string(pDepthMarketData->OpenPrice) + std::string("|") + std::to_string(pDepthMarketData->HighestPrice) + std::string("|") + std::to_string(pDepthMarketData->LowestPrice) + std::string("|") + std::to_string(pDepthMarketData->Volume) + std::string("|") + std::to_string(pDepthMarketData->Turnover) + std::string("|") + std::to_string(pDepthMarketData->OpenInterest) + std::string("|") + std::to_string(pDepthMarketData->ClosePrice) + std::string("|") + std::to_string(pDepthMarketData->SettlementPrice) + std::string("|") + std::to_string(pDepthMarketData->UpperLimitPrice) + std::string("|") + std::to_string(pDepthMarketData->LowerLimitPrice) + std::string("|") + std::string(pDepthMarketData->UpdateTime) + std::string("|") + std::to_string(pDepthMarketData->UpdateMillisec) + std::string("|") + std::to_string(pDepthMarketData->BidPrice1) + std::string("|") + std::to_string(pDepthMarketData->BidVolume1) + std::string("|") + std::to_string(pDepthMarketData->AskPrice1) + std::string("|") + std::to_string(pDepthMarketData->AskVolume1);
        """

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
