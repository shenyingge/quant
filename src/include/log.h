#pragma once

#if !defined(LOG_H)
#define LOG_H

#include <string>
#include <iostream>

class Log {
public:
    static void info(const std::string& message);
    static void warning(const std::string& message);
    static void error(const std::string& message);
private:
    static void log(const std::string& level, const std::string& message);
};

#endif
