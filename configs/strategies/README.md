# 策略配置目录

此目录存放各个策略的独立配置文件。

## 使用方法

1. 复制 `.example` 文件并去掉后缀：
   ```bash
   cp t0_601138.yaml.example t0_601138.yaml
   ```

2. 修改 `t0_601138.yaml` 中的参数

3. 启动策略时指定配置文件：
   ```bash
   python main.py t0-daemon --config configs/strategies/t0_601138.yaml
   ```

## 文件说明

- `*.yaml.example` — 配置模板（纳入 git 管理）
- `*.yaml` — 实际使用的配置（不纳入 git，在 .gitignore 中）

## 配置优先级

1. 策略配置文件（`configs/strategies/*.yaml`）
2. 环境变量（`.env`）
3. 代码默认值

## 多策略管理

可以为不同股票创建不同配置：
```
configs/strategies/
├── t0_601138.yaml.example  # 示例配置
├── t0_601138.yaml          # 601138 实盘配置
├── t0_600519.yaml          # 600519 实盘配置
└── t0_000001.yaml          # 000001 实盘配置
```
