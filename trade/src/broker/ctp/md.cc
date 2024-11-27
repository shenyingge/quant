#include "md.h"
#include "log.h"
#include <iostream>
#include <string>

void CtpMd::OnFrontConnected()
{

    int ret = this->md_api->ReqUserLogin(this->md_login_field, this->request_handler->get_req_id());
    if (ret != 0)
    {
        std::string message = "front connected !!!";
        Log::error(message);
    }
    else
    {
        Log::info("connect success !!!");
    }
}

void CtpMd::OnRspUserLogin(CThostFtdcRspUserLoginField *pRspUserLogin, CThostFtdcRspInfoField *pRspInfo, int nRequestID, bool bIsLast)
{

    if (!pRspInfo || pRspInfo->ErrorID == 0)
    {
        Log::info("login success");
        char *ins_arr[] = {
            "cu2412",
            "cu2501",
            "cu2502",
            "cu2503",
            "cu2504",
            "cu2505",
            "cu2506",
            "cu2507",
            "cu2508",
            "cu2509",
            "cu2510",
            "cu2511",
            "bc2412",
            "bc2501",
            "bc2502",
            "bc2503",
            "bc2504",
            "bc2505",
            "bc2506",
            "bc2507",
            "bc2508",
            "bc2509",
            "bc2510",
            "bc2511",
            "al2412",
            "al2501",
            "al2502",
            "al2503",
            "al2504",
            "al2505",
            "al2506",
            "al2507",
            "al2508",
            "al2509",
            "al2510",
            "al2511",
            "zn2412",
            "zn2501",
            "zn2502",
            "zn2503",
            "zn2504",
            "zn2505",
            "zn2506",
            "zn2507",
            "zn2508",
            "zn2509",
            "zn2510",
            "zn2511",
            "pb2412",
            "pb2501",
            "pb2502",
            "pb2503",
            "pb2504",
            "pb2505",
            "pb2506",
            "pb2507",
            "pb2508",
            "pb2509",
            "pb2510",
            "pb2511",
            "ni2412",
            "ni2501",
            "ni2502",
            "ni2503",
            "ni2504",
            "ni2505",
            "ni2506",
            "ni2507",
            "ni2508",
            "ni2509",
            "ni2510",
            "ni2511",
            "sn2412",
            "sn2501",
            "sn2502",
            "sn2503",
            "sn2504",
            "sn2505",
            "sn2506",
            "sn2507",
            "sn2508",
            "sn2509",
            "sn2510",
            "sn2511",
            "ao2412",
            "ao2501",
            "ao2502",
            "ao2503",
            "ao2504",
            "ao2505",
            "ao2506",
            "ao2507",
            "ao2508",
            "ao2509",
            "ao2510",
            "ao2511",
            "au2412",
            "au2501",
            "au2502",
            "au2504",
            "au2506",
            "au2508",
            "au2510",
            "au2512",
            "ag2412",
            "ag2501",
            "ag2502",
            "ag2503",
            "ag2504",
            "ag2505",
            "ag2506",
            "ag2507",
            "ag2508",
            "ag2509",
            "ag2510",
            "ag2511",
            "rb2412",
            "rb2501",
            "rb2502",
            "rb2503",
            "rb2504",
            "rb2505",
            "rb2506",
            "rb2507",
            "rb2508",
            "rb2509",
            "rb2510",
            "rb2511",
            "wr2412",
            "wr2501",
            "wr2502",
            "wr2503",
            "wr2504",
            "wr2505",
            "wr2506",
            "wr2507",
            "wr2508",
            "wr2509",
            "wr2510",
            "wr2511",
            "hc2412",
            "hc2501",
            "hc2502",
            "hc2503",
            "hc2504",
            "hc2505",
            "hc2506",
            "hc2507",
            "hc2508",
            "hc2509",
            "hc2510",
            "hc2511",
            "ss2412",
            "ss2501",
            "ss2502",
            "ss2503",
            "ss2504",
            "ss2505",
            "ss2506",
            "ss2507",
            "ss2508",
            "ss2509",
            "ss2510",
            "ss2511",
            "sc2412",
            "sc2501",
            "sc2502",
            "sc2503",
            "sc2504",
            "sc2505",
            "sc2506",
            "sc2507",
            "sc2508",
            "sc2509",
            "sc2510",
            "sc2511",
            "sc2512",
            "sc2603",
            "sc2606",
            "sc2609",
            "sc2612",
            "sc2703",
            "sc2706",
            "sc2709",
            "lu2412",
            "lu2501",
            "lu2502",
            "lu2503",
            "lu2504",
            "lu2505",
            "lu2506",
            "lu2507",
            "lu2508",
            "lu2509",
            "lu2510",
            "lu2511",
            "fu2412",
            "fu2501",
            "fu2502",
            "fu2503",
            "fu2504",
            "fu2505",
            "fu2506",
            "fu2507",
            "fu2508",
            "fu2509",
            "fu2510",
            "fu2511",
            "bu2412",
            "bu2501",
            "bu2502",
            "bu2503",
            "bu2504",
            "bu2505",
            "bu2506",
            "bu2507",
            "bu2508",
            "bu2509",
            "bu2510",
            "bu2511",
            "bu2512",
            "bu2603",
            "bu2606",
            "bu2609",
            "br2412",
            "br2501",
            "br2502",
            "br2503",
            "br2504",
            "br2505",
            "br2506",
            "br2507",
            "br2508",
            "br2509",
            "br2510",
            "br2511",
            "ru2501",
            "ru2503",
            "ru2504",
            "ru2505",
            "ru2506",
            "ru2507",
            "ru2508",
            "ru2509",
            "ru2510",
            "ru2511",
            "nr2412",
            "nr2501",
            "nr2502",
            "nr2503",
            "nr2504",
            "nr2505",
            "nr2506",
            "nr2507",
            "nr2508",
            "nr2509",
            "nr2510",
            "nr2511",
            "sp2412",
            "sp2501",
            "sp2502",
            "sp2503",
            "sp2504",
            "sp2505",
            "sp2506",
            "sp2507",
            "sp2508",
            "sp2509",
            "sp2510",
            "sp2511",
            "ec2412",
            "ec2502",
            "ec2504",
            "ec2506",
            "ec2508",
            "ec2510",
        };
        this->md_api->SubscribeMarketData(ins_arr, sizeof(ins_arr) / sizeof(ins_arr[0]));
    }
    else
    {
        Log::error("login error :: error message = " + std::string(pRspInfo->ErrorMsg));
    }
}

void CtpMd::OnRspSubMarketData(CThostFtdcSpecificInstrumentField *pSpecificInstrument, CThostFtdcRspInfoField *pRspInfo, int nRequestID, bool bIsLast)
{
    if (!pRspInfo || pRspInfo->ErrorID == 0)
    {
        Log::info("sub market data " + std::string(pSpecificInstrument->InstrumentID) + " success");
    }
    else
    {
        Log::error("sub market data " + std::string(pSpecificInstrument->InstrumentID) + " error, error message = " + std::string(pRspInfo->ErrorMsg));
    }
}

void CtpMd::OnRtnDepthMarketData(CThostFtdcDepthMarketDataField *pDepthMarketData)
{

    std::string redis_message = std::string(pDepthMarketData->TradingDay) + std::string("|") + std::string(pDepthMarketData->ExchangeID) + std::string("|") + std::to_string(pDepthMarketData->LastPrice) + std::string("|") + std::to_string(pDepthMarketData->PreSettlementPrice) + std::string("|") + std::to_string(pDepthMarketData->PreClosePrice) + std::string("|") + std::to_string(pDepthMarketData->PreOpenInterest) + std::string("|") + std::to_string(pDepthMarketData->OpenPrice) + std::string("|") + std::to_string(pDepthMarketData->HighestPrice) + std::string("|") + std::to_string(pDepthMarketData->LowestPrice) + std::string("|") + std::to_string(pDepthMarketData->Volume) + std::string("|") + std::to_string(pDepthMarketData->Turnover) + std::string("|") + std::to_string(pDepthMarketData->OpenInterest) + std::string("|") + std::to_string(pDepthMarketData->ClosePrice) + std::string("|") + std::to_string(pDepthMarketData->SettlementPrice) + std::string("|") + std::to_string(pDepthMarketData->UpperLimitPrice) + std::string("|") + std::to_string(pDepthMarketData->LowerLimitPrice) + std::string("|") + std::string(pDepthMarketData->UpdateTime) + std::string("|") + std::to_string(pDepthMarketData->UpdateMillisec) + std::string("|") + std::to_string(pDepthMarketData->BidPrice1) + std::string("|") + std::to_string(pDepthMarketData->BidVolume1) + std::string("|") + std::to_string(pDepthMarketData->AskPrice1) + std::string("|") + std::to_string(pDepthMarketData->AskVolume1);
    std::cout << redis_message << std::endl;

    this->redis_tool->set(
        pDepthMarketData->InstrumentID,
        redis_message);
}
