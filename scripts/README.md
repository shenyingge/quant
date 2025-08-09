# Scripts 目录说明

本目录包含用于运行和管理 QMT 自动交易服务的脚本。

## 脚本文件列表

```
scripts/
├── setup_task_simple.bat   # ⭐ 创建定时任务（推荐）
├── run_console.bat         # 手动运行服务
├── task_runner.sh          # 定时任务执行脚本
└── load_env.sh            # 环境变量加载辅助脚本
```

## 核心脚本说明

### 1. `setup_task_simple.bat` ⭐ 推荐使用
- **用途**：创建 Windows 计划任务
- **使用方法**：右键"以管理员身份运行"
- **功能**：
  - 自动检测 MSYS2 安装路径
  - 创建 task_wrapper.bat 避免引号问题
  - 创建每日 8:00 AM 启动任务
  - 创建每日 9:00 PM 停止任务
  - 任务名称：QMT_Trading_Service

### 2. `run_console.bat`
- **用途**：手动在控制台运行交易服务
- **使用场景**：开发测试、手动交易
- **运行方式**：双击运行或命令行执行
- **功能**：
  - 检查 .env 配置文件
  - 优先使用 uv 运行服务
  - 按 Ctrl+C 停止服务

### 3. `task_runner.sh`
- **用途**：定时任务的实际执行脚本
- **运行环境**：MINGW64/MSYS2
- **功能**：
  - 加载 .env 环境变量
  - 检查 QMT 是否运行
  - 检查是否为交易日
  - 同步依赖包
  - 运行交易服务
  - 记录日志到 `logs/task_execution.log`

### 4. `load_env.sh`
- **用途**：辅助脚本，加载环境变量
- **调用者**：task_runner.sh
- **功能**：解析 .env 文件并导出环境变量

## 快速开始

### 设置定时任务（一次性设置）

1. **确保环境准备就绪**
   - MSYS2 已安装（通常在 C:\msys64）
   - .env 文件已配置
   - QMT 客户端已安装

2. **创建定时任务**
   ```cmd
   # 右键 setup_task_simple.bat，选择"以管理员身份运行"
   ```

3. **验证任务创建成功**
   ```cmd
   # 打开任务计划程序查看
   taskschd.msc
   ```

### 手动运行服务

```cmd
# 方式1：使用批处理脚本
scripts\run_console.bat

# 方式2：直接运行
uv run python main.py run

# 方式3：强制运行（忽略交易日检查）
set TRADING_DAY_CHECK_ENABLED=false
uv run python main.py run
```

### 测试定时任务

```cmd
# 手动触发任务
schtasks /run /tn "QMT_Trading_Service"

# 查看执行日志
type logs\task_execution.log

# 查看服务日志
type logs\trading_service.log
```

## 任务管理命令

```cmd
# 启用任务
schtasks /change /tn "QMT_Trading_Service" /enable

# 禁用任务
schtasks /change /tn "QMT_Trading_Service" /disable

# 删除任务
schtasks /delete /tn "QMT_Trading_Service" /f
schtasks /delete /tn "QMT_Trading_Service_Stop" /f

# 查询任务状态
schtasks /query /tn "QMT_Trading_Service" /v
```

## 日志文件

| 日志文件 | 说明 |
|---------|------|
| `logs/task_execution.log` | 定时任务执行日志（脚本级别） |
| `logs/trading_service.log` | 交易服务运行日志（应用级别） |
| `trading.db` | SQLite 数据库（交易记录） |

## 常见问题

### 1. 定时任务不执行
- 检查 MSYS2 是否安装在 C:\msys64 或 C:\msys2
- 确认任务是否启用（在任务计划程序中查看）
- 查看 Windows 事件查看器中的错误

### 2. 服务启动后立即退出
- 检查是否为交易日（周末和节假日会自动退出）
- 查看 logs/task_execution.log 中的错误信息
- 确认 QMT 客户端是否已启动并登录

### 3. 无法连接 QMT
- 确认 QMT 客户端已启动并登录
- 检查 .env 中的 QMT_SESSION_ID 是否正确
- 确认 QMT_PATH 路径是否正确

### 4. 强制在非交易日运行
在 .env 文件中设置：
```
TRADING_DAY_CHECK_ENABLED=false
```

## 注意事项

1. **管理员权限**：创建定时任务需要管理员权限
2. **QMT 依赖**：服务运行前必须启动 QMT 客户端
3. **交易日检查**：使用 akshare 获取准确的交易日历
4. **自动停止**：每晚 9:00 PM 自动停止所有 Python 进程（包括交易服务）
5. **日志轮转**：建议定期清理或归档日志文件