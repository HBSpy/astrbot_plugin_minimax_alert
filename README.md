# MiniMax Token Plan 用量查询插件

专为 AstrBot 开发的 MiniMax API Token Plan 用量查询插件，支持 QQ 私聊和群聊场景。

## 功能特性

| 特性       | 说明                             |
| -------- | ------------------------------ |
| 📊 用量查询  | 查询 MiniMax API Token Plan 剩余额度 |
| 🔄 双周期统计 | 5小时滚动周期 + 本周周期双重统计             |
| 🌍 多版本支持 | 支持国内版和国际版 API                  |
| ⏰ 重置提醒   | 显示距离下次额度重置的剩余时间                |
| ⚡ 异步查询   | 使用 aiohttp 异步请求，高效稳定           |

***

## 快速开始

### 1. 获取 MiniMax API Key

1. 访问 [MiniMax 开放平台](https://www.minimaxi.com/) 注册账号
2. 登录后在开发者中心获取 Coding Plan API Key
3. 国内版直接使用，国际版需额外获取 GroupId

### 2. 安装插件

将 `astrbot_plugin_minimax_alert` 目录复制到 AstrBot 的 `data/plugins/` 目录

***

## 配置说明

### MiniMax 相关配置

| 参数       | 默认值 | 说明                                       |
| -------- | --- | ---------------------------------------- |
| API Key  | 空   | **必填** MiniMax API 访问密钥                  |
| API 版本   | 国内  | 国内版=minimaxi.com，国际版=platform.minimax.io |
| Group ID | 空   | 仅国际版需要                                   |

***

## 指令列表

### 用户指令

| 指令    | 说明                 | 示例    |
| ----- | ------------------ | ----- |
| `/用量` | 查询当前 Token Plan 用量 | `/用量` |

***

## 用量说明

### 5小时滚动周期

- 每5小时自动重置的用量配额
- 显示：已用/总量 及 剩余百分比
- 显示距离下次重置的剩余时间

### 本周周期

- 每周一 00:00 重置的用量配额
- 显示：已用/总量 及 剩余百分比
- 方便追踪周度使用趋势

***

## 项目结构

```
astrbot_plugin_minimax_alert/
├── main.py              # 插件主类、指令处理
├── _conf_schema.json    # 配置参数定义
├── metadata.yaml        # 插件元信息
├── requirements.txt     # Python依赖
└── README.md           # 项目文档
```

***

## 依赖

- aiohttp >= 3.9.0

***

## License

MIT
