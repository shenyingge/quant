# QMT 交易系统测试套件

这个目录包含了QMT交易系统的所有测试文件。

## 📁 测试文件结构

```
tests/
├── __init__.py                 # 测试模块初始化
├── conftest.py                 # pytest 配置和fixtures
├── run_tests.py               # 测试运行器
├── README.md                  # 本文档
├── test_redis_integration.py  # Redis集成测试
├── test_passorder.py          # PassOrder下单功能测试
├── test_concurrent_trading.py # 并发交易测试
├── test_stress_trading.py     # 压力测试
├── test_auto_cancel.py        # 自动撤单测试
├── test_order_timeout.py      # 订单超时测试
├── test_trading_day.py         # 交易日检查测试（完整功能）
├── test_simple_trading_day.py  # 交易日检查测试（简化版）
├── test_trading_day_logic.py   # 交易日逻辑测试（服务集成）
└── test_async_trading.py       # 异步交易架构测试
```

## 🚀 运行测试

### 方法一：使用测试运行器（推荐）

```bash
# 运行所有测试
python tests/run_tests.py

# 运行指定测试
python tests/run_tests.py --test test_redis_integration.py

# 列出所有可用测试
python tests/run_tests.py --list

# 使用pytest运行（如果已安装）
python tests/run_tests.py --pytest
```

### 方法二：直接运行单个测试

```bash
# 直接运行单个测试文件
python tests/test_redis_integration.py
python tests/test_passorder.py
python tests/test_concurrent_trading.py

# 运行交易日检查测试（需要使用uv run）
uv run python tests/test_simple_trading_day.py
uv run python tests/test_trading_day_logic.py
uv run python tests/test_trading_day.py
```

### 方法三：使用pytest（需要安装）

```bash
# 安装pytest
pip install pytest

# 运行所有测试
pytest tests/

# 运行指定测试
pytest tests/test_redis_integration.py

# 详细输出
pytest tests/ -v
```

## 📋 测试说明

### test_redis_integration.py
- **功能**: 测试Redis连接和数据存储
- **依赖**: Redis服务运行
- **安全**: 仅读写测试，不影响生产数据

### test_passorder.py  
- **功能**: 测试QMT的passorder下单功能
- **依赖**: QMT客户端运行并登录
- **⚠️ 警告**: 会执行真实下单操作，请在测试环境使用

### test_concurrent_trading.py
- **功能**: 测试并发交易处理能力
- **场景**: 模拟多个同时到达的交易信号
- **依赖**: QMT客户端

### test_stress_trading.py
- **功能**: 压力测试系统极限
- **场景**: 大量快速交易信号
- **依赖**: QMT客户端
- **⚠️ 警告**: 高强度测试，小心使用

### test_auto_cancel.py
- **功能**: 测试自动撤单功能
- **场景**: 订单超时自动撤销
- **依赖**: QMT客户端

### test_order_timeout.py
- **功能**: 测试订单超时处理
- **场景**: 各种超时情况处理
- **依赖**: QMT客户端

### test_trading_day.py
- **功能**: 测试xtquant交易日检查功能（完整版本）
- **场景**: 交易日历获取、日期验证、多日期检查
- **依赖**: xtquant模块（使用uv run执行）
- **说明**: 包含详细的交易日历功能测试

### test_simple_trading_day.py  
- **功能**: 测试xtquant交易日检查功能（简化版本）
- **场景**: 基本的交易日检查和错误处理
- **依赖**: xtquant模块（使用uv run执行）
- **说明**: 轻量级交易日检查测试

### test_trading_day_logic.py
- **功能**: 测试Windows服务中的交易日检查逻辑
- **场景**: 服务启动逻辑、配置验证、备用方案
- **依赖**: Windows服务配置、xtquant模块
- **说明**: 完整的服务集成测试

### test_async_trading.py
- **功能**: 测试异步交易架构
- **场景**: 线程池、异步下单、回调处理
- **依赖**: QMT Trader模块
- **说明**: 验证异步交易系统架构和组件

## 🔧 测试配置

### 前置条件

1. **QMT客户端**: 确保QMT已启动并成功登录
2. **Redis服务**: Redis服务正常运行（用于相关测试）
3. **网络连接**: 确保网络连接正常
4. **测试环境**: 建议在测试环境而非生产环境运行

### 安全注意事项

- ⚠️ **真实下单**: 部分测试会执行真实的下单操作
- 💰 **资金安全**: 确保测试账户有适当的资金限制
- 📊 **测试数据**: 使用测试专用的股票代码和小额资金
- 🕒 **交易时间**: 在交易时间内运行相关测试

### 环境变量

可以通过环境变量配置测试参数：

```bash
export QMT_SESSION_ID="test_session"
export REDIS_HOST="localhost"
export REDIS_PORT=6379
export TEST_MODE=true
```

## 📊 测试报告

测试运行后会生成详细的测试报告，包括：
- ✅ 通过的测试数量
- ❌ 失败的测试及原因
- 📈 性能统计（如适用）
- 📋 详细的日志输出

## 🐛 故障排除

### 常见问题

1. **QMT连接失败**
   - 检查QMT是否启动并登录
   - 确认session_id配置正确

2. **Redis连接失败**  
   - 检查Redis服务是否运行
   - 确认连接参数正确

3. **导入错误**
   - 确保在项目根目录运行测试
   - 检查Python路径配置

4. **权限错误**
   - 确保有足够的文件读写权限
   - 检查日志目录权限

### 获取帮助

如果遇到问题，请：
1. 查看详细的日志输出
2. 检查相关服务状态
3. 确认测试环境配置
4. 联系系统管理员

## 📝 添加新测试

要添加新的测试文件：

1. 创建 `test_功能名称.py` 文件
2. 使用统一的测试模板
3. 添加必要的文档说明
4. 更新本README文件

### 测试模板

```python
#!/usr/bin/env python
"""
新功能测试模板
"""

import sys
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.your_module import YourClass

def test_your_function():
    """测试你的功能"""
    print("开始测试新功能...")
    
    # 测试代码
    assert True  # 替换为实际测试
    
    print("✅ 测试通过")

if __name__ == "__main__":
    test_your_function()
```