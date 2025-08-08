# QMT自动交易服务

基于QMT（迅投量化交易系统）的自动交易服务，通过Redis监听交易信号并自动执行订单。

## 功能特性

- 🔄 **实时监听**: 监听Redis频道接收交易信号
- 📈 **自动交易**: 接收信号后自动执行买卖操作  
- 💾 **数据记录**: 将交易信号和订单信息存储到本地数据库
- 📱 **飞书通知**: 实时推送交易状态到飞书群聊
- ⏰ **计划任务**: 支持通过Windows任务计划程序自动运行
- 📊 **订单监控**: 实时监控订单状态和成交情况
- 🔧 **自动备份**: 每日自动备份交易数据

## 系统要求

- Python 3.11+
- Windows 10/11 或 Windows Server 2016+
- QMT客户端（国金证券版本）
- Redis服务器
- MSYS2/MINGW64环境（推荐）

## 项目结构

```
quant/
├── main.py                # 主程序入口
├── pyproject.toml         # 项目配置和依赖（使用uv管理）
├── .env                   # 环境配置文件
├── src/                   # 核心源代码
│   ├── config.py          # 配置管理
│   ├── database.py        # 数据库模型（SQLAlchemy）
│   ├── logger_config.py   # 统一日志配置
│   ├── redis_listener.py  # Redis信号监听器
│   ├── redis_client.py    # Redis客户端管理
│   ├── trader.py          # QMT交易执行器
│   ├── notifications.py   # 飞书通知服务
│   ├── trading_service.py # 核心交易服务
│   ├── backup_service.py  # 数据备份服务
│   └── stock_info.py      # 股票信息缓存
├── scripts/               # 脚本文件
│   ├── task_runner.sh     # 主任务运行器（MINGW64）
│   ├── setup_task.bat     # 设置计划任务
│   ├── run_console.bat    # 控制台运行脚本
│   ├── load_env.sh        # 环境变量加载
│   └── auto_detect_session.py # 自动检测QMT会话
├── logs/                  # 日志文件目录
│   ├── task_execution.log # 任务执行日志
│   └── trading_service.log # 交易服务日志
├── backups/               # 数据备份目录
├── tests/                 # 测试文件
│   └── test_*.py          # 各种测试脚本
└── xtquant/               # QMT官方SDK（不要修改）
```

## 快速开始

### 1. 安装依赖

项目使用 [uv](https://github.com/astral-sh/uv) 管理依赖：

```bash
# 安装uv（如果未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 同步项目依赖
uv sync
```

### 2. 配置环境变量

创建并编辑 `.env` 文件：

```env
# Redis配置
REDIS_HOST=10.0.12.2
REDIS_PORT=30102
REDIS_SIGNAL_CHANNEL=trading_signals

# QMT配置
QMT_SESSION_ID=666  # 会话ID（自动检测可用）
QMT_PATH=C:/国金QMT交易端模拟/userdata_mini
QMT_ACCOUNT_ID=39266820

# 飞书通知配置
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook
FEISHU_SECRET=your-secret-key

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=logs/trading_service.log

# 备份配置
BACKUP_ENABLED=true
BACKUP_TIME=15:05
BACKUP_DIR=backups
```

### 3. 测试系统连接

```bash
# 测试所有组件连接
uv run python main.py test
```

### 4. 运行服务

#### 方式一：控制台模式（手动运行）

```bash
# 直接运行
uv run python main.py

# 或使用脚本
scripts\run_console.bat
```

#### 方式二：计划任务（自动化）

以管理员身份运行：

```batch
# 设置每日自动运行的计划任务
scripts\setup_task.bat
```

这会创建一个Windows计划任务：
- 每天8:00自动启动交易服务
- 使用MINGW64环境运行
- 自动检测QMT会话ID
- 日志输出到 `logs/task_execution.log`

## 交易信号格式

向Redis频道发送JSON格式的交易信号：

```json
{
    "signal_id": "SIGNAL_20250809_001",
    "stock_code": "000001",
    "direction": "BUY",
    "volume": 100,
    "price": 10.50,
    "order_type": 23
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| signal_id | string | 是 | 唯一信号标识符 |
| stock_code | string | 是 | 股票代码（6位） |
| direction | string | 是 | 交易方向：BUY（买入）或 SELL（卖出） |
| volume | integer | 是 | 交易数量（股） |
| price | float | 否 | 交易价格（不填为市价单） |
| order_type | integer | 否 | 订单类型（默认23为限价单） |

## 命令行使用

```bash
# 运行交易服务
uv run python main.py

# 测试系统连接
uv run python main.py test

# 手动备份数据
uv run python main.py backup

# 查看备份配置
uv run python main.py backup-config

# 管理股票信息缓存
uv run python main.py stock-info
```

## 监控和维护

### 日志文件

- `logs/task_execution.log` - 任务执行日志（包含启动、停止、错误信息）
- `logs/trading_service.log` - 交易服务详细日志
- `logs/task_debug.log` - 调试日志（如有）

### 数据备份

系统支持自动备份交易数据：

- 默认每日15:05自动备份
- 备份文件保存在 `backups/` 目录
- 格式：`trading_backup_YYYYMMDD_HHMMSS.json.gz`

### 飞书通知

系统会在以下情况发送飞书通知：

- ✅ 服务启动/停止
- 📈 收到交易信号
- 💰 订单成交
- ❌ 订单失败或错误
- ⚠️ 系统异常

## 故障排查

### 常见问题

1. **QMT连接失败**
   - 确保QMT客户端已启动并登录
   - 检查Session ID是否正确
   - 尝试重新启动QMT客户端

2. **Redis连接失败**
   - 检查Redis服务是否运行
   - 验证Redis配置（主机、端口）
   - 检查网络连接

3. **中文日志乱码**
   - 确保使用MINGW64环境运行
   - 检查环境变量 `PYTHONIOENCODING=utf-8`

4. **计划任务不执行**
   - 检查Windows任务计划程序中的任务状态
   - 查看 `logs/task_execution.log` 中的错误信息
   - 确保以管理员权限创建任务

## 开发和测试

### 运行测试

```bash
# 运行所有测试
uv run pytest tests/

# 运行特定测试
uv run python tests/test_redis_integration.py
uv run python tests/test_passorder.py
```

### 代码结构

- 使用SQLAlchemy ORM管理数据库
- 使用loguru进行统一日志管理
- 使用redis-py作为Redis客户端
- 使用xtquant SDK与QMT交互

## 安全提示

⚠️ **重要安全提醒**：

1. **不要**将 `.env` 文件提交到版本控制
2. **定期**更换飞书webhook密钥
3. **限制**Redis访问权限
4. **使用**测试账户进行开发测试
5. **备份**重要的交易数据

## 许可证

本项目仅供学习和研究使用，请遵守相关法律法规。使用本系统进行实际交易产生的任何损失，作者不承担责任。

## 联系方式

如有问题或建议，请提交Issue或联系开发者。