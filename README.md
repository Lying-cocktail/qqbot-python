# qqbot-python
腾讯QQ的openclaw专用机器人协议的PYTHON实现，让机器人更自由吧

### 本项目是从[qqbot|https://github.com/sliverp/qqbot]进行通讯协议转换而来，感谢sliverp提供的版本


## QQBot Python 客户端

基于 QQ 官方机器人 API 的 Python 客户端实现，支持标准输入输出交互。

## 功能特性

- ✅ WebSocket 连接：实时接收消息事件
- ✅ HTTP API：发送消息、上传媒体
- ✅ 私聊/群聊/频道消息支持
- ✅ 媒体消息收发：图片、语音、视频、文件
- ✅ 标准输入输出交互
- ✅ 自动 Token 管理
- ✅ 断线重连与会话恢复

## 安装

```bash
pip install aiohttp
```

## 快速开始

### 方式一：使用命令行参数

```bash
python qqbot.py <AppID> <ClientSecret>
```

### 方式二：使用内置配置

直接运行，使用代码中的默认配置：

```bash
python qqbot.py
```

### 获取 AppID 和 ClientSecret

1. 访问 [QQ 开放平台](https://q.qq.com/)
2. 创建机器人应用
3. 在应用详情页获取 `AppID` 和 `ClientSecret`

## 使用说明

### 消息格式

#### 收消息
```
[时间][类型]发送者: 内容 [附件路径] [附件路径] ...
```

示例：
```
[14:30:25][私聊]张三: 你好
[14:31:10][群聊]李四: 看这张图 images/abc123.jpg
[14:32:00][私聊]王五: 语音消息 voice/xyz.wav
```

#### 消息类型标识
| 标识 | 说明 |
|------|------|
| `[私聊]` | C2C 私聊消息 |
| `[群聊]` | 群聊 @ 消息 |
| `[频道]` | 频道 @ 消息 |
| `[频道私信]` | 频道私信 |

### 命令列表

| 命令 | 说明 | 示例 |
|------|------|------|
| `/help` | 显示帮助信息 | `/help` |
| `/target <目标>` | 设置发送目标 | `/target c2c:ABC123` |
| `/reply <内容>` | 回复最后收到的消息 | `/reply 收到了` |
| 直接输入 | 发送消息到当前目标 | `你好` |

### 目标格式

| 类型 | 格式 | 示例 |
|------|------|------|
| 私聊 | `c2c:<用户OpenID>` | `c2c:ABC123DEF456` |
| 群聊 | `group:<群OpenID>` | `group:XYZ789` |
| 频道 | `channel:<频道ID>` | `channel:123456` |

### 发送文件

1. 将文件放入 `uploads/` 目录
2. 在消息中使用 `[文件名]` 格式引用

```
看这张图片 [images/photo.jpg]
这是一条语音 [voice/hello.wav]
发送文档 [files/report.pdf]
```

### 特殊字符转义

| 原字符 | 转义写法 | 示例 |
|--------|----------|------|
| 换行 | `\\n` | `第一行\\n第二行` |
| 回车 | `\\r` | `内容\\r换行` |
| 制表符 | `\\t` | `列1\\t列2` |
| 反斜杠 | `\\\\` | `路径\\\\文件夹` |

## 目录结构

```
.
├── qqbot.py           # 主程序
├── downloads/         # 收到的文件保存目录
│   ├── images/        # 图片
│   ├── voice/         # 语音
│   ├── video/         # 视频
│   └── files/         # 其他文件
└── uploads/           # 要发送的文件目录
    ├── images/        # 图片
    ├── voice/         # 语音
    └── files/         # 其他文件
```

## 工作流程

```
┌─────────────────────────────────────────────────────────┐
│                     QQBot Python 客户端                   │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐         ┌──────────────┐              │
│  │   标准输入    │         │  WebSocket   │              │
│  │  (命令/消息)  │         │  (事件接收)   │              │
│  └──────┬───────┘         └──────┬───────┘              │
│         │                        │                       │
│         ▼                        ▼                       │
│  ┌──────────────────────────────────────┐               │
│  │            StdioHandler              │               │
│  │  - 解析命令                           │               │
│  │  - 处理文件引用                       │               │
│  │  - 格式化输出                         │               │
│  └──────────────────┬───────────────────┘               │
│                     │                                    │
│         ┌──────────┴──────────┐                         │
│         ▼                     ▼                         │
│  ┌────────────┐        ┌────────────┐                   │
│  │   QQBot    │        │  MediaDown │                   │
│  │   核心     │        │  loader    │                   │
│  └─────┬──────┘        └─────┬──────┘                   │
│        │                     │                          │
│        ▼                     ▼                          │
│  ┌────────────┐        ┌────────────┐                   │
│  │  HTTP API  │        │  文件系统   │                   │
│  │  (发送)    │        │  (下载)    │                   │
│  └────────────┘        └────────────┘                   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## API 说明

### QQBot 类

```python
from qqbot import QQBot, Message

# 创建机器人
bot = QQBot(
    app_id="YOUR_APP_ID",
    client_secret="YOUR_SECRET",
    download_dir="downloads"  # 可选
)

# 设置消息回调
async def on_message(msg: Message):
    print(f"收到消息: {msg.content}")
    await bot.reply(msg, "收到！")

bot.on_message = on_message

# 运行
bot.run()
```

### Message 类

```python
@dataclass
class Message:
    id: str                    # 消息ID
    content: str               # 消息内容
    timestamp: int             # 时间戳
    author_id: str             # 发送者ID
    author_name: str           # 发送者昵称
    message_type: str          # 类型: c2c/group/channel
    attachments: List[Attachment]  # 附件列表
    
    # 属性
    is_group: bool             # 是否群聊
    is_private: bool           # 是否私聊
    is_channel: bool           # 是否频道
    has_attachments: bool      # 是否有附件
    image_attachments: List    # 图片附件
    voice_attachments: List    # 语音附件
```

### 发送消息

```python
# 私聊
await bot.send_private_message(openid, "消息内容")

# 群聊
await bot.send_group_message(group_openid, "消息内容")

# 频道
await bot.send_channel_message(channel_id, "消息内容")

# 回复消息
await bot.reply(message, "回复内容")

# 发送图片
await bot.send_image(target_id, image_path="uploads/photo.jpg")
```

### 下载附件

```python
# 下载所有附件
paths = await bot.download_attachments(message)

# 只下载图片
images = await bot.download_images(message)

# 下载语音
voice_path = await bot.download_voice(message)
```

## 通讯协议

### WebSocket 操作码

| Opcode | 名称 | 说明 |
|--------|------|------|
| 0 | DISPATCH | 事件分发 |
| 1 | HEARTBEAT | 心跳请求 |
| 2 | IDENTIFY | 身份认证 |
| 6 | RESUME | 恢复会话 |
| 7 | RECONNECT | 要求重连 |
| 9 | INVALID_SESSION | 会话无效 |
| 10 | HELLO | 连接建立 |
| 11 | HEARTBEAT_ACK | 心跳确认 |

### 事件类型

| 事件 | 说明 |
|------|------|
| `READY` | 连接就绪 |
| `C2C_MESSAGE_CREATE` | 私聊消息 |
| `GROUP_AT_MESSAGE_CREATE` | 群聊 @ 消息 |
| `AT_MESSAGE_CREATE` | 频道 @ 消息 |
| `DIRECT_MESSAGE_CREATE` | 频道私信 |

## 错误排查

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `获取Token失败` | AppID 或 ClientSecret 错误 | 检查配置是否正确 |
| `获取Gateway失败` | Token 无效或网络问题 | 检查网络连接 |
| `WebSocket 错误` | 网络断开 | 程序会自动重连 |
| `权限不足` | Intents 配置与后台不匹配 | 检查开放平台权限设置 |

## 注意事项

1. **被动回复限制**：收到消息后 1 小时内最多回复 4 次
2. **主动消息限制**：每月每用户/群限额 4 条
3. **语音格式**：QQ 原生支持 SILK/WAV/MP3 格式
4. **Token 有效期**：约 2 小时，程序会自动刷新

## 许可证

MIT License
