# qqbot-python
腾讯QQ的openclaw专用机器人协议的PYTHON实现，让机器人更自由吧

### 本项目是从[qqbot](https://github.com/sliverp/qqbot)进行通讯协议转换而来，感谢sliverp提供的版本


## QQBot Python 客户端

基于 QQ 官方机器人 API 的 Python 客户端实现，支持标准输入输出交互。

## 功能特性

### 核心功能
- ✅ WebSocket 连接：实时接收消息事件
- ✅ HTTP API：发送消息、上传媒体
- ✅ 私聊/群聊/频道消息支持
- ✅ 媒体消息收发：图片、语音、视频、文件
- ✅ 标准输入输出交互
- ✅ 自动 Token 管理
- ✅ 断线重连与会话恢复

### 高级功能
- ✅ **测试模式**：自动回复相同内容，方便调试
- ✅ **联系人管理**：自动记录所有联系人
- ✅ **聊天记录**：每个联系人独立记录，支持双向消息
- ✅ **自动发送**：监控 uploads 目录，自动发送文本文件

## 安装依赖

```bash
pip install aiohttp
```

## 快速开始

### 方式一：使用命令行参数

```bash
python qqbot.py <AppID> <ClientSecret>
```

### 方式二：使用内置配置

直接运行，使用代码中``自己``修改的默认账号：

```bash
python qqbot.py
```

### 测试模式

启用测试模式，收到什么就回复什么：

```bash
python qqbot.py --test
```

### 食用方法

. 通过管道运行本程序，通过标准输入输出进行收发消息
. 本程序独立运行，定时检查chatlogs目录下的聊天记录文件的修改时间，根据需要在uploads目录下生成文件即可回复客户端




### 获取 AppID 和 ClientSecret

1. 访问 [QQ 开放平台](https://q.qq.com/qqbot/openclaw/) 龙虾专用入口
2. 创建机器人应用
3. 在应用详情页获取 `AppID` 和 `ClientSecret`

## 目录结构

```
.
├── qqbot.py           # 主程序
├── contacts.txt       # 联系人清单（自动生成）
├── chatlogs/          # 聊天记录目录（自动生成）
│   └── <联系人ID>.txt
├── downloads/         # 收到的文件保存目录
│   ├── images/        # 图片
│   ├── voice/         # 语音（WAV格式优先）
│   ├── video/         # 视频
│   └── files/         # 其他文件
└── uploads/           # 要发送的文件目录
    ├── images/        # 图片
    ├── voice/         # 语音
    ├── files/         # 其他文件
    └── *.txt          # 文本文件会自动发送给最近联系人
```

## 使用说明

### 消息格式

#### 收消息
```
[时间][类型]发送者: 内容 [附件路径] [附件路径] ...
```

示例：
```
[14:30:25][私聊]张三: 你好
[14:31:10][群聊]李四: 看这张图 [images/abc123.jpg]
[14:32:00][私聊]王五: 语音消息 [voice/xyz.wav]
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
| `/help` | 显示帮助和最近联系人 | `/help` |
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

#### 方式一：命令行发送

1. 将文件放入 `uploads/` 目录
2. 在消息中使用 `[文件名]` 格式引用

```
看这张图片 [images/photo.jpg]
这是一条语音 [voice/hello.wav]
发送文档 [files/report.pdf]
```

#### 方式二：自动发送

1. 将文本文件直接放入 `uploads/` 目录（不含子目录）
2. 文件内容会自动发送给最近联系人
3. 内容中可包含 `[文件路径]` 来发送媒体文件

示例文本文件内容：
```
你好，这是一条自动发送的消息
[images/logo.png]
请查看上面的图片
```

### 特殊字符转义

| 原字符 | 转义写法 | 示例 |
|--------|----------|------|
| 换行 | `\\n` | `第一行\\n第二行` |
| 回车 | `\\r` | `内容\\r换行` |
| 制表符 | `\\t` | `列1\\t列2` |
| 反斜杠 | `\\\\` | `路径\\\\文件夹` |

## 联系人管理

### contacts.txt 格式

```
# QQBot 联系人清单
# 格式: id|名称|类型|最后消息时间

E94F5326AFB54479C6564BBFF5174BD3|张三|c2c|2026-03-13 21:30:00
ABC123XYZ789|测试群|group|2026-03-13 20:15:30
```

### 联系人类型

| 类型 | 说明 |
|------|------|
| `c2c` | 私聊联系人 |
| `group` | 群聊 |
| `channel` | 频道 |

## 聊天记录

### 文件位置
`chatlogs/<联系人ID>.txt`

### 记录格式

```
<< [2026-03-13 21:31:55] 收到的消息内容
>> [2026-03-13 21:31:55] 发送的消息内容
<< [2026-03-13 21:32:10] 另一条消息 [images/photo.jpg]
>> [2026-03-13 21:32:11] 回复内容
```

- `<<` 表示收到的消息
- `>>` 表示发送的消息
- 每条消息包含时间戳
- 附件路径记录在消息末尾
- 特殊字符自动转义

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
│  │  - 联系人管理                         │               │
│  │  - 聊天记录                           │               │
│  │  - uploads 监控                       │               │
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
await bot.api.send_image(target_id, image_path="uploads/photo.jpg")

# 发送语音
await bot.api.send_voice(target_id, voice_path="uploads/voice.wav")

# 发送文件
await bot.api.send_file(target_id, file_path="uploads/doc.pdf")
```

### 下载附件

```python
# 下载所有附件
paths = await bot.download_attachments(message)

# 只下载图片
images = await bot.download_images(message)

# 下载语音（优先WAV格式）
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
| `上传媒体失败: file data empty` | 文件数据格式错误 | 已修复，使用 Base64 编码 |
| `富媒体文件下载失败` | API 无法访问本地文件 | 已修复，使用 Base64 上传 |

## 注意事项

1. **被动回复限制**：收到消息后 1 小时内最多回复 4 次
2. **主动消息限制**：每月每用户/群限额 4 条
3. **语音格式**：QQ 原生支持 SILK/WAV/MP3 格式，程序优先下载 WAV 格式
4. **Token 有效期**：约 2 小时，程序会自动刷新
5. **测试模式**：自动回复会消耗回复配额，生产环境请谨慎使用
6. **聊天记录**：使用 UTF-8 编码，特殊字符已转义

## 许可证

MIT License
