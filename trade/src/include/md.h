#pragma once

#include "ThostFtdcMdApi.h"
#include "ThostFtdcUserApiStruct.h"
#include "request.h"
#include "redis.h"

class CtpMd : public CThostFtdcMdSpi
{
private:
    CThostFtdcMdApi *md_api = nullptr;
    CThostFtdcReqUserLoginField *md_login_field = nullptr;
    Request *request_handler = new Request();
    RedisTool *redis_tool = nullptr;

public:
    CtpMd(CThostFtdcMdApi *md_api, CThostFtdcReqUserLoginField *md_login_field, RedisTool *redis_tool) : md_api(md_api), md_login_field(md_login_field), redis_tool(redis_tool) {};

    /// 当客户端与交易后台建立起通信连接时（还未登录前），该方法被调用。
    void OnFrontConnected();

    /// 登录请求响应
    void OnRspUserLogin(CThostFtdcRspUserLoginField *pRspUserLogin, CThostFtdcRspInfoField *pRspInfo, int nRequestID, bool bIsLast);

    /// 错误应答
    // void OnRspError(CThostFtdcRspInfoField *pRspInfo, int nRequestID, bool bIsLast);

    // /// 订阅行情应答
    void OnRspSubMarketData(CThostFtdcSpecificInstrumentField *pSpecificInstrument, CThostFtdcRspInfoField *pRspInfo, int nRequestID, bool bIsLast);

    // /// 取消订阅行情应答
    // void OnRspUnSubMarketData(CThostFtdcSpecificInstrumentField *pSpecificInstrument, CThostFtdcRspInfoField *pRspInfo, int nRequestID, bool bIsLast);

    // /// 深度行情通知
    void OnRtnDepthMarketData(CThostFtdcDepthMarketDataField *pDepthMarketData);

    ~CtpMd(){};
};
