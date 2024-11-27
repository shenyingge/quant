#include <iostream>
#include "log.h"
#include "md.h"
#include "ThostFtdcUserApiStruct.h"
#include "ThostFtdcMdApi.h"
#include <cstring>
#include <yaml-cpp/yaml.h>
#include "redis.h"

int main(){

    try {
        YAML::Node config = YAML::LoadFile("../config.yml");
        CThostFtdcReqUserLoginField *md_login_field = new CThostFtdcReqUserLoginField();

        std::strcpy(md_login_field->BrokerID, config["broker_id"].as<std::string>().c_str());
        std::strcpy(md_login_field->UserID, config["user_id"].as<std::string>().c_str());

        CThostFtdcMdApi *md_api = CThostFtdcMdApi::CreateFtdcMdApi();
        if (!md_api){
            Log::info("create md api failed");
            return -1;
        }

        RedisTool *redis_tool = new RedisTool();
        redis_tool->connect();

        CThostFtdcMdSpi *md_spi = new CtpMd(md_api, md_login_field, redis_tool);
        md_api->RegisterSpi(md_spi);

        const std::string md_addr_str = config["md_addr"].as<std::string>();
        char md_addr[md_addr_str.size() + 1];
        std::strcpy(md_addr, md_addr_str.c_str());
        md_api->RegisterFront(md_addr);
        md_api->Init();

        md_api->Join();

    } catch (const YAML::Exception& e) {
        std::cerr << "Error parsing YAML: " << e.what() << std::endl;
    }
    return 0;
}
