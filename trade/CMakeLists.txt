cmake_minimum_required(VERSION 3.6)
project(quant)

# 设置 C++ 标准
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

link_directories(
    ${PROJECT_SOURCE_DIR}/src/api/ctp
)
# 包含头文件目录
include_directories(
    ${PROJECT_SOURCE_DIR}/src/api/ctp
    ${PROJECT_SOURCE_DIR}/src/include
)
SET(CMAKE_LIBRARY_PATH ${CMAKE_LIBRARY_PATH}
    ${PROJECT_SOURCE_DIR}/src/api/ctp
)

find_package(yaml-cpp REQUIRED)
find_library(HIREDIS_LIB hiredis REQUIRED)

# 设置源文件列表
set(SRC_FILES
    main.cc
    src/broker/ctp/md.cc
    src/broker/ctp/trader.cc
    src/utils/log.cc
    src/utils/request.cc
)

# 添加可执行文件
add_executable(${PROJECT_NAME} ${SRC_FILES})

# 链接库文件，使用完整路径
target_link_libraries(${PROJECT_NAME}
    yaml-cpp::yaml-cpp
    ${HIREDIS_LIB}
    libthostmduserapi_se.so
    libthosttraderapi_se.so
)
