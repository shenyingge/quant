#ifndef REDISTOOL_H
#define REDISTOOL_H

#include <hiredis/hiredis.h>
#include <string>
#include <stdexcept>
#include <iostream>

class RedisTool {
private:
    redisContext* context; // Redis 连接上下文
    std::string host;
    int port;

public:
    // 构造函数
    RedisTool(const std::string& host = "127.0.0.1", int port = 6379)
        : host(host), port(port), context(nullptr) {}

    // 连接到 Redis
    void connect() {
        context = redisConnect(host.c_str(), port);
        if (context == nullptr || context->err) {
            throw std::runtime_error("Failed to connect to Redis: " + std::string(context ? context->errstr : "Unknown error"));
        }
        std::cout << "Connected to Redis at " << host << ":" << port << std::endl;
    }

    // 断开连接
    void disconnect() {
        if (context) {
            redisFree(context);
            context = nullptr;
            std::cout << "Disconnected from Redis." << std::endl;
        }
    }

    // 执行命令并返回结果
    std::string executeCommand(const std::string& command) {
        if (!context) {
            throw std::runtime_error("Redis connection not established.");
        }
        redisReply* reply = (redisReply*)redisCommand(context, command.c_str());
        if (!reply) {
            throw std::runtime_error("Failed to execute command: " + std::string(context->errstr));
        }

        std::string result;
        if (reply->type == REDIS_REPLY_STRING) {
            result = reply->str;
        } else if (reply->type == REDIS_REPLY_INTEGER) {
            result = std::to_string(reply->integer);
        } else if (reply->type == REDIS_REPLY_STATUS) {
            result = reply->str;
        } else if (reply->type == REDIS_REPLY_ERROR) {
            result = reply->str;
        } else if (reply->type == REDIS_REPLY_NIL) {
            result = "nil";
        } else {
            result = "Unknown reply type.";
        }

        freeReplyObject(reply);
        return result;
    }

    // 设置键值对
    void set(const std::string& key, const std::string& value) {
        std::string command = "SET " + key + " " + value;
        std::string reply = executeCommand(command);
        if (reply != "OK") {
            throw std::runtime_error("Failed to set key: " + key);
        }
    }

    // 获取键值
    std::string get(const std::string& key) {
        std::string command = "GET " + key;
        return executeCommand(command);
    }

    // 析构函数
    ~RedisTool() {
        disconnect();
    }
};

#endif // REDISTOOL_H
