#pragma once

#include <atomic>

class Request {
public:
    // 构造函数，初始化 request_id 为 0
    Request() : req_id(0) {}

    // 获取当前 request_id 值
    int get_req_id();

private:
    std::atomic<int> req_id;  // 原子变量
};
