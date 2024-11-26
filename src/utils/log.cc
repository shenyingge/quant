#include "log.h"
#include <iostream>
#include <iomanip>
#include <ctime>

void Log::info(const std::string& message) {
    log("INFO", message);
}

void Log::warning(const std::string& message) {
    log("WARNING", message);
}

void Log::error(const std::string& message) {
    log("ERROR", message);
}

void Log::log(const std::string& level, const std::string& message) {
    // 获取当前时间
    std::time_t t = std::time(nullptr);
    std::tm* tm = std::localtime(&t);

    // 打印时间戳、日志级别和消息
    std::cout << std::put_time(tm, "[%Y-%m-%d %H:%M:%S]") << " ";
    std::cout << level << ": " << message << std::endl;
}
