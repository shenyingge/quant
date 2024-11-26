#include "md.h"
#include "log.h"
#include <iostream>
#include <string>

void CtpMd::OnFrontConnected(){

    int ret = this->md_api->ReqUserLogin(this->md_login_field, this->request_handler->get_req_id());
    if (ret != 0){
        std::string message = "front connected !!!";
        Log::error(message);
    }
    else{
        Log::info("connect success !!!");
    }

}

void CtpMd::OnRspUserLogin(CThostFtdcRspUserLoginField *pRspUserLogin, CThostFtdcRspInfoField *pRspInfo, int nRequestID, bool bIsLast){

    if (!pRspInfo || pRspInfo->ErrorID == 0){
        Log::info("login success");
    }
    else{
        Log::error("login error :: error message = " + std::string(pRspInfo->ErrorMsg));
    }

}
