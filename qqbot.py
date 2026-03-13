#!/usr/bin/env python3
"""
QQBot Python Implementation
基于 QQ 官方机器人 API 的 Python 客户端实现

通讯协议：
- WebSocket: 接收事件（消息、通知等）
- HTTP API: 发送消息、上传媒体

使用方法：
    bot = QQBot(app_id="your_app_id", client_secret="your_secret")
    bot.on_message = lambda msg: print(f"收到消息: {msg}")
    bot.run()
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Union
from urllib.parse import urljoin

import aiohttp

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("QQBot")


# ============== 常量定义 ==============

class OpCode(IntEnum):
    """WebSocket 操作码"""
    DISPATCH = 0           # 事件分发
    HEARTBEAT = 1          # 心跳请求
    IDENTIFY = 2           # 身份认证
    RESUME = 6             # 恢复会话
    RECONNECT = 7          # 要求重连
    INVALID_SESSION = 9    # 会话无效
    HELLO = 10             # 连接建立
    HEARTBEAT_ACK = 11     # 心跳确认


class Intent(IntEnum):
    """WebSocket 权限位"""
    GUILDS = 1 << 0                    # 频道相关
    GUILD_MEMBERS = 1 << 1             # 频道成员
    GUILD_MESSAGES = 1 << 9            # 频道消息
    GUILD_MESSAGE_REACTIONS = 1 << 10  # 频道消息表情
    DIRECT_MESSAGE = 1 << 12           # 频道私信
    OPEN_FORUMS_EVENT = 1 << 18        # 开放论坛
    AUDIO_OR_LIVE_CHANNEL = 1 << 21    # 音视频直播
    INTERACTION = 1 << 26              # 互动事件
    MESSAGE_AUDIT = 1 << 27            # 消息审核
    FORUM_EVENT = 1 << 28              # 论坛事件
    AT_MESSAGE = 1 << 30               # @消息
    GROUP_AND_C2C = 1 << 25            # 群聊和私聊


class MessageType(IntEnum):
    """消息类型"""
    TEXT = 0       # 文本消息
    MARKDOWN = 2   # Markdown消息
    ARK = 3        # Ark消息
    EMBED = 4      # Embed消息
    MEDIA = 7      # 媒体消息
    INPUT_NOTIFY = 6  # 输入状态


class MediaFileType(IntEnum):
    """媒体文件类型"""
    IMAGE = 1      # 图片
    VIDEO = 2      # 视频
    VOICE = 3      # 语音
    FILE = 4       # 文件


class EventType:
    """事件类型常量"""
    READY = "READY"
    RESUMED = "RESUMED"
    C2C_MESSAGE_CREATE = "C2C_MESSAGE_CREATE"          # 私聊消息
    GROUP_AT_MESSAGE_CREATE = "GROUP_AT_MESSAGE_CREATE"  # 群@消息
    AT_MESSAGE_CREATE = "AT_MESSAGE_CREATE"            # 频道@消息
    DIRECT_MESSAGE_CREATE = "DIRECT_MESSAGE_CREATE"    # 频道私信


# API 端点
API_BASE_URL = "https://api.sgroup.qq.com"
TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
GATEWAY_URL = f"{API_BASE_URL}/gateway"


# ============== 数据类定义 ==============

@dataclass
class BotConfig:
    """机器人配置"""
    app_id: str
    client_secret: str
    name: str = "QQBot"
    intents: Optional[int] = None
    markdown_support: bool = True
    image_server_base_url: Optional[str] = None
    
    def __post_init__(self):
        if self.intents is None:
            # 默认权限：频道@消息 + 私信 + 群聊私聊
            self.intents = Intent.AT_MESSAGE | Intent.DIRECT_MESSAGE | Intent.GROUP_AND_C2C


@dataclass
class WSPayload:
    """WebSocket 消息载荷"""
    op: int                    # 操作码
    d: Optional[Any] = None    # 数据
    s: Optional[int] = None    # 序列号
    t: Optional[str] = None    # 事件类型
    
    def to_dict(self) -> dict:
        result = {"op": self.op}
        if self.d is not None:
            result["d"] = self.d
        if self.s is not None:
            result["s"] = self.s
        if self.t is not None:
            result["t"] = self.t
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> 'WSPayload':
        return cls(
            op=data.get("op", 0),
            d=data.get("d"),
            s=data.get("s"),
            t=data.get("t")
        )


@dataclass
class Attachment:
    """消息附件"""
    content_type: str              # MIME类型，如 "image/png", "audio/silk"
    url: str                       # 文件URL
    filename: Optional[str] = None # 文件名
    size: Optional[int] = None     # 文件大小
    width: Optional[int] = None    # 图片宽度
    height: Optional[int] = None   # 图片高度
    voice_wav_url: Optional[str] = None  # 语音WAV格式直链（QQ提供）
    
    # 下载后的本地路径
    local_path: Optional[str] = None
    
    @property
    def is_image(self) -> bool:
        """判断是否为图片附件"""
        # 首先检查 content_type
        if self.content_type.startswith("image/"):
            return True
        # 后备检查：文件名或URL扩展名
        image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.ico']
        check_names = [self.filename, self.url] if self.filename else [self.url]
        for name in check_names:
            if name:
                ext = os.path.splitext(name.split('?')[0])[1].lower()
                if ext in image_exts:
                    return True
        return False
    
    @property
    def is_voice(self) -> bool:
        """判断是否为语音附件"""
        # 首先检查 content_type
        if self.content_type.startswith("audio/"):
            return True
        if "silk" in self.content_type.lower() or "amr" in self.content_type.lower():
            return True
        # 后备检查：文件名扩展名
        voice_exts = ['.silk', '.slk', '.amr', '.wav', '.mp3', '.ogg', '.m4a', '.voice']
        check_names = [self.filename, self.url] if self.filename else [self.url]
        for name in check_names:
            if name:
                ext = os.path.splitext(name.split('?')[0])[1].lower()
                if ext in voice_exts:
                    return True
        return False
    
    @property
    def is_video(self) -> bool:
        """判断是否为视频附件"""
        if self.content_type.startswith("video/"):
            return True
        video_exts = ['.mp4', '.webm', '.mov', '.avi', '.mkv', '.flv']
        check_names = [self.filename, self.url] if self.filename else [self.url]
        for name in check_names:
            if name:
                ext = os.path.splitext(name.split('?')[0])[1].lower()
                if ext in video_exts:
                    return True
        return False


@dataclass
class Message:
    """消息对象"""
    id: str                               # 消息ID
    content: str                          # 消息内容
    timestamp: int                        # 时间戳
    author_id: str                        # 发送者ID
    author_name: Optional[str] = None     # 发送者昵称
    guild_id: Optional[str] = None        # 频道ID
    channel_id: Optional[str] = None      # 子频道ID
    group_id: Optional[str] = None        # 群ID
    group_openid: Optional[str] = None    # 群OpenID
    attachments: List[Attachment] = field(default_factory=list)  # 附件列表
    message_type: str = "c2c"             # 消息类型: c2c/group/channel
    raw_data: dict = field(default_factory=dict)  # 原始数据
    
    @property
    def is_group(self) -> bool:
        return self.message_type == "group"
    
    @property
    def is_private(self) -> bool:
        return self.message_type == "c2c"
    
    @property
    def is_channel(self) -> bool:
        return self.message_type == "channel"
    
    @property
    def has_attachments(self) -> bool:
        return len(self.attachments) > 0
    
    @property
    def image_attachments(self) -> List[Attachment]:
        return [a for a in self.attachments if a.is_image]
    
    @property
    def voice_attachments(self) -> List[Attachment]:
        return [a for a in self.attachments if a.is_voice]
    
    @property
    def video_attachments(self) -> List[Attachment]:
        return [a for a in self.attachments if a.is_video]


@dataclass
class SessionState:
    """会话状态（用于 Resume）"""
    session_id: Optional[str] = None
    last_seq: Optional[int] = None
    last_connected_at: float = 0
    intent_level_index: int = 0
    app_id: Optional[str] = None
    saved_at: float = 0


# ============== 媒体下载器 ==============

class MediaDownloader:
    """媒体文件下载器"""
    
    def __init__(self, download_dir: str = ".qqbot/downloads"):
        """
        初始化下载器
        
        Args:
            download_dir: 下载文件保存目录
        """
        self.download_dir = download_dir
        self._session: Optional[aiohttp.ClientSession] = None
        self._ensure_dir()
    
    def _ensure_dir(self):
        """确保下载目录存在"""
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir, exist_ok=True)
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 HTTP Session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def download_file(
        self,
        url: str,
        filename: Optional[str] = None,
        subdir: Optional[str] = None
    ) -> Optional[str]:
        """
        下载文件到本地
        
        Args:
            url: 文件URL（支持 // 开头的URL，会自动添加 https:）
            filename: 自定义文件名（不含路径）
            subdir: 子目录名
            
        Returns:
            本地文件路径，失败返回 None
        """
        # 修复 QQ 返回的 // 前缀 URL
        if url.startswith("//"):
            url = f"https:{url}"
        
        try:
            session = await self._get_session()
            
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"下载失败: HTTP {response.status}")
                    return None
                
                # 确定保存目录
                save_dir = self.download_dir
                if subdir:
                    save_dir = os.path.join(self.download_dir, subdir)
                    os.makedirs(save_dir, exist_ok=True)
                
                # 确定文件名
                if not filename:
                    # 从URL或Content-Type推断文件名
                    content_type = response.headers.get("Content-Type", "")
                    ext = self._get_extension(content_type, url)
                    timestamp = int(time.time() * 1000)
                    filename = f"download_{timestamp}{ext}"
                
                filepath = os.path.join(save_dir, filename)
                
                # 写入文件
                content = await response.read()
                with open(filepath, "wb") as f:
                    f.write(content)
                
                logger.info(f"文件已下载: {filepath} ({len(content)} bytes)")
                return filepath
                
        except Exception as e:
            logger.error(f"下载文件失败: {e}")
            return None
    
    def _get_extension(self, content_type: str, url: str) -> str:
        """根据Content-Type或URL推断扩展名"""
        # 从Content-Type推断
        type_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "audio/silk": ".silk",
            "audio/amr": ".amr",
            "audio/wav": ".wav",
            "audio/mp3": ".mp3",
            "audio/mpeg": ".mp3",
            "audio/ogg": ".ogg",
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "application/pdf": ".pdf",
        }
        
        content_type_lower = content_type.lower().split(";")[0].strip()
        if content_type_lower in type_map:
            return type_map[content_type_lower]
        
        # 从URL推断
        if "." in url.split("?")[0]:
            ext = "." + url.split("?")[0].split(".")[-1].lower()
            if len(ext) <= 5:  # 合理的扩展名长度
                return ext
        
        return ".bin"
    
    async def download_attachment(
        self,
        attachment: Attachment,
        prefer_wav: bool = True
    ) -> Optional[str]:
        """
        下载消息附件
        
        Args:
            attachment: 附件对象
            prefer_wav: 对于语音，优先下载WAV格式（使用voice_wav_url）
            
        Returns:
            本地文件路径
        """
        # 语音附件：优先下载WAV格式
        if attachment.is_voice and prefer_wav and attachment.voice_wav_url:
            wav_url = attachment.voice_wav_url
            if wav_url.startswith("//"):
                wav_url = f"https:{wav_url}"
            
            local_path = await self.download_file(
                wav_url,
                filename=f"{attachment.filename or 'voice'}.wav" if attachment.filename else None,
                subdir="voice"
            )
            if local_path:
                attachment.local_path = local_path
                logger.info(f"语音已下载(WAV格式): {local_path}")
                return local_path
            else:
                logger.warning("WAV下载失败，尝试原始格式")
        
        # 下载原始文件
        subdir = None
        if attachment.is_image:
            subdir = "images"
        elif attachment.is_voice:
            subdir = "voice"
        elif attachment.is_video:
            subdir = "video"
        else:
            subdir = "files"
        
        local_path = await self.download_file(
            attachment.url,
            filename=attachment.filename,
            subdir=subdir
        )
        
        if local_path:
            attachment.local_path = local_path
        
        return local_path
    
    async def download_all_attachments(
        self,
        attachments: List[Attachment]
    ) -> List[str]:
        """
        下载所有附件
        
        Args:
            attachments: 附件列表
            
        Returns:
            成功下载的本地路径列表
        """
        paths = []
        for att in attachments:
            path = await self.download_attachment(att)
            if path:
                paths.append(path)
        return paths
    
    async def close(self):
        """关闭连接"""
        if self._session and not self._session.closed:
            await self._session.close()


# ============== Token 管理器 ==============

class TokenManager:
    """Access Token 管理器"""
    
    def __init__(self, app_id: str, client_secret: str):
        self.app_id = app_id
        self.client_secret = client_secret
        self._token: Optional[str] = None
        self._expires_at: float = 0
        self._lock = asyncio.Lock()
        self._refresh_task: Optional[asyncio.Task] = None
    
    async def get_token(self) -> str:
        """获取有效的 Token（自动刷新）"""
        async with self._lock:
            # 提前5分钟刷新
            if self._token and time.time() < self._expires_at - 300:
                return self._token
            
            return await self._fetch_token()
    
    async def _fetch_token(self) -> str:
        """从服务器获取新 Token"""
        async with aiohttp.ClientSession() as session:
            payload = {
                "appId": self.app_id,
                "clientSecret": self.client_secret
            }
            async with session.post(TOKEN_URL, json=payload) as resp:
                data = await resp.json()
                # 检查 access_token 是否存在
                access_token = data.get("access_token")
                if not access_token:
                    raise Exception(f"获取Token失败: {data}")
                
                self._token = access_token
                self._expires_at = time.time() + int(data.get("expires_in", 7200))
                logger.info(f"Token已获取，有效期至 {self._expires_at}")
                return self._token
    
    def start_background_refresh(self):
        """启动后台自动刷新"""
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._refresh_loop())
    
    async def _refresh_loop(self):
        """后台刷新循环"""
        while True:
            try:
                await asyncio.sleep(600)  # 每10分钟检查一次
                if self._token and time.time() > self._expires_at - 600:
                    async with self._lock:
                        await self._fetch_token()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"后台刷新Token失败: {e}")
    
    def stop_background_refresh(self):
        """停止后台刷新"""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()


# ============== HTTP API 客户端 ==============

class QQBotAPI:
    """QQBot HTTP API 客户端"""
    
    def __init__(self, token_manager: TokenManager):
        self.token_manager = token_manager
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 HTTP Session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def _headers(self) -> dict:
        """构建请求头"""
        token = await self.token_manager.get_token()
        return {
            "Authorization": f"QQBot {token}",
            "Content-Type": "application/json",
            "X-Union-Appid": self.token_manager.app_id
        }
    
    async def get_gateway_url(self) -> str:
        """获取 WebSocket Gateway URL"""
        session = await self._get_session()
        headers = await self._headers()
        
        async with session.get(GATEWAY_URL, headers=headers) as resp:
            data = await resp.json()
            url = data.get("url")
            if not url:
                raise Exception(f"获取Gateway失败: {data}")
            logger.info(f"Gateway URL: {url}")
            return url
    
    async def send_c2c_message(
        self,
        openid: str,
        content: str,
        msg_id: Optional[str] = None,
        msg_seq: Optional[int] = None
    ) -> dict:
        """发送私聊消息"""
        session = await self._get_session()
        headers = await self._headers()
        
        payload = {
            "content": content,
            "msg_type": MessageType.TEXT,
            "msg_seq": msg_seq or int(time.time() * 1000) % 100000000
        }
        
        if msg_id:
            payload["msg_id"] = msg_id
        
        url = f"{API_BASE_URL}/v2/users/{openid}/messages"
        async with session.post(url, headers=headers, json=payload) as resp:
            data = await resp.json()
            if resp.status != 200:
                logger.error(f"发送私聊消息失败: {data}")
            return data
    
    async def send_group_message(
        self,
        group_openid: str,
        content: str,
        msg_id: Optional[str] = None,
        msg_seq: Optional[int] = None
    ) -> dict:
        """发送群聊消息"""
        session = await self._get_session()
        headers = await self._headers()
        
        payload = {
            "content": content,
            "msg_type": MessageType.TEXT,
            "msg_seq": msg_seq or int(time.time() * 1000) % 100000000
        }
        
        if msg_id:
            payload["msg_id"] = msg_id
        
        url = f"{API_BASE_URL}/v2/groups/{group_openid}/messages"
        async with session.post(url, headers=headers, json=payload) as resp:
            data = await resp.json()
            if resp.status != 200:
                logger.error(f"发送群消息失败: {data}")
            return data
    
    async def send_channel_message(
        self,
        channel_id: str,
        content: str,
        msg_id: Optional[str] = None
    ) -> dict:
        """发送频道消息"""
        session = await self._get_session()
        headers = await self._headers()
        
        payload = {"content": content}
        if msg_id:
            payload["msg_id"] = msg_id
        
        url = f"{API_BASE_URL}/channels/{channel_id}/messages"
        async with session.post(url, headers=headers, json=payload) as resp:
            data = await resp.json()
            if resp.status != 200:
                logger.error(f"发送频道消息失败: {data}")
            return data
    
    async def upload_media(
        self,
        target_id: str,
        file_type: MediaFileType,
        url: Optional[str] = None,
        file_data: Optional[bytes] = None,
        is_group: bool = False,
        srv_send_msg: bool = False
    ) -> dict:
        """上传媒体文件
        
        Args:
            target_id: 目标ID (openid 或 group_openid)
            file_type: 媒体类型
            url: 文件URL (公网可访问)
            file_data: 文件二进制数据 (会自动转为Base64)
            is_group: 是否为群聊
            srv_send_msg: 是否由服务器发送消息
        """
        session = await self._get_session()
        headers = await self._headers()
        
        # 构建请求体 (JSON格式)
        body: Dict[str, Any] = {
            "file_type": file_type.value,
            "srv_send_msg": srv_send_msg
        }
        
        if url:
            body["url"] = url
        elif file_data:
            # 重要：file_data 必须是 Base64 编码的字符串
            import base64
            body["file_data"] = base64.b64encode(file_data).decode("utf-8")
        else:
            raise ValueError("必须提供 url 或 file_data")
        
        # 选择端点
        if is_group:
            api_url = f"{API_BASE_URL}/v2/groups/{target_id}/files"
        else:
            api_url = f"{API_BASE_URL}/v2/users/{target_id}/files"
        
        async with session.post(api_url, headers=headers, json=body) as resp:
            data = await resp.json()
            if resp.status != 200:
                logger.error(f"上传媒体失败: {data}")
            return data
    
    async def send_media_message(
        self,
        target_id: str,
        file_info: str,
        msg_type: MessageType = MessageType.MEDIA,
        msg_id: Optional[str] = None,
        content: Optional[str] = None,
        is_group: bool = False
    ) -> dict:
        """发送媒体消息"""
        session = await self._get_session()
        headers = await self._headers()
        
        payload = {
            "msg_type": msg_type,
            "media": {"file_info": file_info},
            "msg_seq": int(time.time() * 1000) % 100000000
        }
        
        if msg_id:
            payload["msg_id"] = msg_id
        if content:
            payload["content"] = content
        
        if is_group:
            url = f"{API_BASE_URL}/v2/groups/{target_id}/messages"
        else:
            url = f"{API_BASE_URL}/v2/users/{target_id}/messages"
        
        async with session.post(url, headers=headers, json=payload) as resp:
            data = await resp.json()
            if resp.status != 200:
                logger.error(f"发送媒体消息失败: {data}")
            return data
    
    async def send_image(
        self,
        target_id: str,
        image_url: Optional[str] = None,
        image_data: Optional[bytes] = None,
        image_path: Optional[str] = None,
        msg_id: Optional[str] = None,
        content: Optional[str] = None,
        is_group: bool = False
    ) -> dict:
        """发送图片消息（上传+发送）"""
        # 支持本地文件路径
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                image_data = f.read()
        
        upload_result = await self.upload_media(
            target_id, MediaFileType.IMAGE,
            url=image_url, file_data=image_data, is_group=is_group
        )
        
        file_info = upload_result.get("file_info")
        if not file_info:
            raise Exception(f"上传图片失败: {upload_result}")
        
        return await self.send_media_message(
            target_id, file_info, msg_id=msg_id, content=content, is_group=is_group
        )
    
    async def send_voice(
        self,
        target_id: str,
        voice_url: Optional[str] = None,
        voice_data: Optional[bytes] = None,
        voice_path: Optional[str] = None,
        msg_id: Optional[str] = None,
        is_group: bool = False
    ) -> dict:
        """发送语音消息
        
        Args:
            target_id: 目标ID
            voice_url: 语音URL
            voice_data: 语音二进制数据
            voice_path: 本地语音文件路径
            msg_id: 回复的消息ID
            is_group: 是否为群聊
        """
        if voice_path and os.path.exists(voice_path):
            with open(voice_path, "rb") as f:
                voice_data = f.read()
        
        upload_result = await self.upload_media(
            target_id, MediaFileType.VOICE,
            url=voice_url, file_data=voice_data, is_group=is_group
        )
        
        file_info = upload_result.get("file_info")
        if not file_info:
            raise Exception(f"上传语音失败: {upload_result}")
        
        return await self.send_media_message(
            target_id, file_info, 
            msg_type=MessageType.MEDIA,
            msg_id=msg_id, 
            is_group=is_group
        )
    
    async def send_file(
        self,
        target_id: str,
        file_url: Optional[str] = None,
        file_data: Optional[bytes] = None,
        file_path: Optional[str] = None,
        msg_id: Optional[str] = None,
        is_group: bool = False
    ) -> dict:
        """发送文件消息
        
        Args:
            target_id: 目标ID
            file_url: 文件URL
            file_data: 文件二进制数据
            file_path: 本地文件路径
            msg_id: 回复的消息ID
            is_group: 是否为群聊
        """
        if file_path and os.path.exists(file_path):
            with open(file_path, "rb") as f:
                file_data = f.read()
        
        upload_result = await self.upload_media(
            target_id, MediaFileType.FILE,
            url=file_url, file_data=file_data, is_group=is_group
        )
        
        file_info = upload_result.get("file_info")
        if not file_info:
            raise Exception(f"上传文件失败: {upload_result}")
        
        return await self.send_media_message(
            target_id, file_info, 
            msg_type=MessageType.MEDIA,
            msg_id=msg_id, 
            is_group=is_group
        )
    
    async def close(self):
        """关闭连接"""
        if self._session and not self._session.closed:
            await self._session.close()


# ============== WebSocket Gateway ==============

class QQBotGateway:
    """QQBot WebSocket Gateway"""
    
    # 重连延迟序列（秒）
    RECONNECT_DELAYS = [1, 2, 5, 10, 30, 60]
    SESSION_EXPIRE_TIME = 5 * 60  # 5分钟
    
    def __init__(
        self,
        api: QQBotAPI,
        config: BotConfig,
        on_message: Optional[Callable[[Message], None]] = None
    ):
        self.api = api
        self.config = config
        self.on_message = on_message
        
        # WebSocket 状态
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
        
        # 连接信息
        self._gateway_url: Optional[str] = None
        self._session_id: Optional[str] = None
        self._last_seq: Optional[int] = None
        self._heartbeat_interval: int = 30
        self._connected = False
        self._should_reconnect = True
        self._reconnect_count = 0
        
        # 会话状态（用于 Resume）
        self._session_state = SessionState()
        
        # 消息序号
        self._msg_seq = 0
    
    async def connect(self):
        """连接 WebSocket Gateway"""
        self._should_reconnect = True
        
        while self._should_reconnect:
            try:
                await self._connect_once()
            except Exception as e:
                logger.error(f"连接失败: {e}")
            
            if self._should_reconnect:
                delay = self.RECONNECT_DELAYS[
                    min(self._reconnect_count, len(self.RECONNECT_DELAYS) - 1)
                ]
                logger.info(f"{delay}秒后重连...")
                await asyncio.sleep(delay)
                self._reconnect_count += 1
    
    async def _connect_once(self):
        """单次连接"""
        try:
            # 获取 Gateway URL
            self._gateway_url = await self.api.get_gateway_url()
            
            # 创建 WebSocket 连接
            self._session = aiohttp.ClientSession()
            self._ws = await self._session.ws_connect(
                self._gateway_url,
                heartbeat=30,
                compress=0
            )
            
            logger.info("WebSocket 已连接")
            self._connected = True
            self._reconnect_count = 0
            
            # 接收消息循环
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket 错误: {self._ws.exception()}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.info("WebSocket 已关闭")
                    break
            
        except Exception as e:
            logger.error(f"连接异常: {e}")
        finally:
            await self._cleanup()
    
    async def _handle_message(self, data: str):
        """处理 WebSocket 消息"""
        try:
            payload = WSPayload.from_dict(json.loads(data))
            
            # 更新序列号
            if payload.s is not None:
                self._last_seq = payload.s
            
            # 根据操作码处理
            if payload.op == OpCode.HELLO:
                await self._on_hello(payload.d)
            elif payload.op == OpCode.DISPATCH:
                await self._on_dispatch(payload)
            elif payload.op == OpCode.HEARTBEAT_ACK:
                logger.debug("收到心跳确认")
            elif payload.op == OpCode.RECONNECT:
                logger.warning("服务器要求重连")
                await self._reconnect()
            elif payload.op == OpCode.INVALID_SESSION:
                logger.warning("会话无效，重新认证")
                self._session_id = None
                await self._identify()
            
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
    
    async def _on_hello(self, data: dict):
        """处理 Hello 事件"""
        self._heartbeat_interval = data.get("heartbeat_interval", 30000) // 1000
        logger.info(f"心跳间隔: {self._heartbeat_interval}秒")
        
        # 启动心跳
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        # 尝试 Resume 或 Identify
        if self._can_resume():
            await self._resume()
        else:
            await self._identify()
    
    async def _on_dispatch(self, payload: WSPayload):
        """处理事件分发"""
        event_type = payload.t
        data = payload.d or {}
        
        if event_type == EventType.READY:
            await self._on_ready(data)
        elif event_type == EventType.RESUMED:
            logger.info("会话恢复成功")
        elif event_type in [
            EventType.C2C_MESSAGE_CREATE,
            EventType.GROUP_AT_MESSAGE_CREATE,
            EventType.AT_MESSAGE_CREATE,
            EventType.DIRECT_MESSAGE_CREATE
        ]:
            await self._on_message_event(event_type, data)
        else:
            logger.debug(f"收到事件: {event_type}")
    
    async def _on_ready(self, data: dict):
        """处理 Ready 事件"""
        self._session_id = data.get("session_id")
        user = data.get("user", {})
        logger.info(f"机器人已就绪: {user.get('username', 'Unknown')}")
        logger.info(f"Session ID: {self._session_id}")
        
        # 保存会话状态
        self._session_state.session_id = self._session_id
        self._session_state.last_seq = self._last_seq
        self._session_state.last_connected_at = time.time()
        self._session_state.saved_at = time.time()
    
    async def _on_message_event(self, event_type: str, data: dict):
        """处理消息事件"""
        try:
            # 解析消息
            msg = self._parse_message(event_type, data)
            
            # 回调处理
            if self.on_message:
                await self._safe_callback(self.on_message, msg)
                
        except Exception as e:
            logger.error(f"处理消息事件失败: {e}")
    
    def _parse_message(self, event_type: str, data: dict) -> Message:
        """解析消息对象"""
        author = data.get("author", {})
        raw_attachments = data.get("attachments", [])
        
        # 解析附件为 Attachment 对象
        attachments = []
        for att in raw_attachments:
            # 修复 // 前缀的URL
            url = att.get("url", "")
            if url.startswith("//"):
                url = f"https:{url}"
            
            voice_wav_url = att.get("voice_wav_url")
            if voice_wav_url and voice_wav_url.startswith("//"):
                voice_wav_url = f"https:{voice_wav_url}"
            
            attachment = Attachment(
                content_type=att.get("content_type", "application/octet-stream"),
                url=url,
                filename=att.get("filename"),
                size=att.get("size"),
                width=att.get("width"),
                height=att.get("height"),
                voice_wav_url=voice_wav_url
            )
            attachments.append(attachment)
        
        # 根据事件类型确定消息类型和目标
        if event_type == EventType.C2C_MESSAGE_CREATE:
            message_type = "c2c"
            author_id = author.get("id", data.get("openid", ""))
            group_id = None
            group_openid = None
            guild_id = None
            channel_id = None
        elif event_type == EventType.GROUP_AT_MESSAGE_CREATE:
            message_type = "group"
            author_id = author.get("id", data.get("author", {}).get("member_openid", ""))
            group_id = data.get("group_id")
            group_openid = data.get("group_openid")
            guild_id = None
            channel_id = None
        elif event_type == EventType.AT_MESSAGE_CREATE:
            message_type = "channel"
            author_id = author.get("id", "")
            guild_id = data.get("guild_id")
            channel_id = data.get("channel_id")
            group_id = None
            group_openid = None
        elif event_type == EventType.DIRECT_MESSAGE_CREATE:
            message_type = "channel_dm"
            author_id = author.get("id", "")
            guild_id = data.get("guild_id")
            channel_id = data.get("channel_id")
            group_id = None
            group_openid = None
        else:
            message_type = "unknown"
            author_id = author.get("id", "")
            guild_id = data.get("guild_id")
            channel_id = data.get("channel_id")
            group_id = None
            group_openid = None
        
        return Message(
            id=data.get("id", ""),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", int(time.time())),
            author_id=author_id,
            author_name=author.get("username") or author.get("nick", ""),
            guild_id=guild_id,
            channel_id=channel_id,
            group_id=group_id,
            group_openid=group_openid,
            attachments=attachments,
            message_type=message_type,
            raw_data=data
        )
    
    async def _safe_callback(self, callback: Callable, *args):
        """安全调用回调函数"""
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"回调执行失败: {e}")
    
    def _can_resume(self) -> bool:
        """检查是否可以 Resume"""
        if not self._session_state.session_id:
            return False
        
        # 检查会话是否过期
        elapsed = time.time() - self._session_state.saved_at
        return elapsed < self.SESSION_EXPIRE_TIME
    
    async def _identify(self):
        """发送认证请求"""
        payload = WSPayload(
            op=OpCode.IDENTIFY,
            d={
                "token": f"QQBot {await self.api.token_manager.get_token()}",
                "intents": self.config.intents,
                "shard": [0, 1],
                "properties": {
                    "$os": "python",
                    "$browser": "qqbot-python",
                    "$device": "qqbot-python"
                }
            }
        )
        await self._send(payload)
        logger.info("已发送认证请求")
    
    async def _resume(self):
        """发送恢复会话请求"""
        payload = WSPayload(
            op=OpCode.RESUME,
            d={
                "token": f"QQBot {await self.api.token_manager.get_token()}",
                "session_id": self._session_state.session_id,
                "seq": self._session_state.last_seq
            }
        )
        await self._send(payload)
        logger.info("已发送会话恢复请求")
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        while self._connected:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                if self._connected and self._ws:
                    payload = WSPayload(op=OpCode.HEARTBEAT, d=self._last_seq)
                    await self._send(payload)
                    logger.debug("发送心跳")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳失败: {e}")
                break
    
    async def _send(self, payload: WSPayload):
        """发送 WebSocket 消息"""
        if self._ws and not self._ws.closed:
            await self._ws.send_json(payload.to_dict())
    
    async def _reconnect(self):
        """主动重连"""
        await self._cleanup()
        self._should_reconnect = True
    
    async def _cleanup(self):
        """清理连接"""
        self._connected = False
        
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        
        if self._ws and not self._ws.closed:
            await self._ws.close()
        
        if self._session and not self._session.closed:
            await self._session.close()
        
        self._ws = None
        self._session = None
    
    async def close(self):
        """关闭连接"""
        self._should_reconnect = False
        await self._cleanup()
        logger.info("Gateway 已关闭")


# ============== QQBot 主类 ==============

class QQBot:
    """QQBot 主类"""
    
    def __init__(
        self,
        app_id: str,
        client_secret: str,
        name: str = "QQBot",
        intents: Optional[int] = None,
        download_dir: str = ".qqbot/downloads"
    ):
        """初始化 QQBot
        
        Args:
            app_id: 机器人 AppID
            client_secret: 机器人 ClientSecret
            name: 机器人名称
            intents: 权限位（默认使用完整权限）
            download_dir: 媒体文件下载目录
        """
        self.config = BotConfig(
            app_id=app_id,
            client_secret=client_secret,
            name=name,
            intents=intents
        )
        
        # 初始化组件
        self.token_manager = TokenManager(app_id, client_secret)
        self.api = QQBotAPI(self.token_manager)
        self.gateway = QQBotGateway(self.api, self.config)
        self.media_downloader = MediaDownloader(download_dir)
        
        # 回调函数
        self._on_message: Optional[Callable[[Message], None]] = None
        self._on_ready: Optional[Callable[[], None]] = None
    
    @property
    def on_message(self) -> Optional[Callable[[Message], None]]:
        """消息回调"""
        return self._on_message
    
    @on_message.setter
    def on_message(self, callback: Callable[[Message], None]):
        """设置消息回调"""
        self._on_message = callback
        self.gateway.on_message = callback
    
    @property
    def on_ready(self) -> Optional[Callable[[], None]]:
        """就绪回调"""
        return self._on_ready
    
    @on_ready.setter
    def on_ready(self, callback: Callable[[], None]):
        self._on_ready = callback
    
    def run(self):
        """运行机器人（阻塞）"""
        asyncio.run(self.start())
    
    async def start(self):
        """启动机器人"""
        logger.info(f"启动机器人: {self.config.name}")
        
        # 启动后台 Token 刷新
        self.token_manager.start_background_refresh()
        
        try:
            # 连接 Gateway
            await self.gateway.connect()
        finally:
            await self.stop()
    
    async def stop(self):
        """停止机器人"""
        logger.info("停止机器人...")
        self.token_manager.stop_background_refresh()
        await self.gateway.close()
        await self.api.close()
        await self.media_downloader.close()
    
    # ============== 消息发送接口 ==============
    
    async def send_private_message(
        self,
        openid: str,
        content: str,
        reply_to: Optional[str] = None
    ) -> dict:
        """发送私聊消息
        
        Args:
            openid: 用户 OpenID
            content: 消息内容
            reply_to: 回复的消息ID（被动回复）
        """
        return await self.api.send_c2c_message(openid, content, msg_id=reply_to)
    
    async def send_group_message(
        self,
        group_openid: str,
        content: str,
        reply_to: Optional[str] = None
    ) -> dict:
        """发送群聊消息
        
        Args:
            group_openid: 群 OpenID
            content: 消息内容
            reply_to: 回复的消息ID（被动回复）
        """
        return await self.api.send_group_message(group_openid, content, msg_id=reply_to)
    
    async def send_channel_message(
        self,
        channel_id: str,
        content: str,
        reply_to: Optional[str] = None
    ) -> dict:
        """发送频道消息
        
        Args:
            channel_id: 频道 ID
            content: 消息内容
            reply_to: 回复的消息ID
        """
        return await self.api.send_channel_message(channel_id, content, msg_id=reply_to)
    
    async def send_image(
        self,
        target_id: str,
        image_url: Optional[str] = None,
        image_path: Optional[str] = None,
        is_group: bool = False,
        content: Optional[str] = None,
        reply_to: Optional[str] = None
    ) -> dict:
        """发送图片消息
        
        Args:
            target_id: 目标ID (openid 或 group_openid)
            image_url: 图片URL
            image_path: 本地图片路径
            is_group: 是否为群聊
            content: 附加文本
            reply_to: 回复的消息ID
        """
        image_data = None
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                image_data = f.read()
        
        return await self.api.send_image(
            target_id,
            image_url=image_url,
            image_data=image_data,
            msg_id=reply_to,
            content=content,
            is_group=is_group
        )
    
    async def reply(self, message: Message, content: str) -> dict:
        """回复消息（便捷方法）
        
        Args:
            message: 原消息
            content: 回复内容
        """
        if message.is_private:
            return await self.send_private_message(message.author_id, content, reply_to=message.id)
        elif message.is_group:
            return await self.send_group_message(message.group_openid, content, reply_to=message.id)
        elif message.is_channel:
            return await self.send_channel_message(message.channel_id, content, reply_to=message.id)
        else:
            raise ValueError(f"未知消息类型: {message.message_type}")
    
    # ============== 媒体下载接口 ==============
    
    async def download_attachments(self, message: Message) -> List[str]:
        """下载消息中的所有附件
        
        Args:
            message: 消息对象
            
        Returns:
            成功下载的本地路径列表
        """
        return await self.media_downloader.download_all_attachments(message.attachments)
    
    async def download_images(self, message: Message) -> List[str]:
        """下载消息中的所有图片
        
        Args:
            message: 消息对象
            
        Returns:
            成功下载的本地路径列表
        """
        paths = []
        for att in message.image_attachments:
            path = await self.media_downloader.download_attachment(att)
            if path:
                paths.append(path)
        return paths
    
    async def download_voice(self, message: Message, prefer_wav: bool = True) -> Optional[str]:
        """下载消息中的语音（如果有）
        
        Args:
            message: 消息对象
            prefer_wav: 是否优先下载WAV格式
            
        Returns:
            本地文件路径，没有语音返回None
        """
        voice_attachments = message.voice_attachments
        if not voice_attachments:
            return None
        
        # 下载第一个语音
        return await self.media_downloader.download_attachment(
            voice_attachments[0], 
            prefer_wav=prefer_wav
        )


# ============== 标准输入输出处理器 ==============

class StdioHandler:
    """标准输入输出处理器"""
    
    def __init__(
        self,
        bot: 'QQBot',
        download_dir: str = "downloads",
        upload_dir: str = "uploads",
        test_mode: bool = False
    ):
        self.bot = bot
        self.download_dir = download_dir
        self.upload_dir = upload_dir
        self.test_mode = test_mode  # 测试模式：自动回复相同内容
        self._current_target: Optional[str] = None  # 当前回复目标
        self._last_message: Optional[Message] = None  # 最后收到的消息
        self._input_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        
        # 确保目录存在
        os.makedirs(download_dir, exist_ok=True)
        os.makedirs(upload_dir, exist_ok=True)
    
    def escape_content(self, text: str) -> str:
        """转义内容中的特殊字符"""
        # 转义规则：\n -> \\n, \t -> \\t, \r -> \\r, \\ -> \\\\
        text = text.replace("\\", "\\\\")
        text = text.replace("\n", "\\n")
        text = text.replace("\r", "\\r")
        text = text.replace("\t", "\\t")
        return text
    
    def unescape_content(self, text: str) -> str:
        """反转义内容"""
        text = text.replace("\\n", "\n")
        text = text.replace("\\r", "\r")
        text = text.replace("\\t", "\t")
        text = text.replace("\\\\", "\\")
        return text
    
    async def format_incoming_message(self, msg: Message) -> str:
        """格式化收到的消息"""
        parts = []
        
        # 消息头：类型和时间戳
        type_map = {
            "c2c": "私聊",
            "group": "群聊",
            "channel": "频道",
            "channel_dm": "频道私信"
        }
        msg_type = type_map.get(msg.message_type, msg.message_type)
        # timestamp可能是ISO格式字符串、时间戳字符串或整数
        ts = msg.timestamp
        if isinstance(ts, str):
            # ISO格式: 2026-03-13T20:41:52+08:00
            if "T" in ts:
                # 提取时间部分 HH:MM:SS
                time_part = ts.split("T")[1].split("+")[0].split("-")[0][:8]
                timestamp = time_part
            else:
                try:
                    ts = int(ts)
                    timestamp = time.strftime("%H:%M:%S", time.localtime(ts))
                except ValueError:
                    timestamp = str(ts)
        else:
            timestamp = time.strftime("%H:%M:%S", time.localtime(ts))
        
        # 显示发送者信息
        author_info = msg.author_name if msg.author_name else msg.author_id
        header = f"[{timestamp}][{msg_type}]{author_info}:"
        
        # 消息内容（转义处理）
        content_parts = []
        if msg.content:
            content_parts.append(self.escape_content(msg.content))
        
        # 处理附件：下载并以[相对路径]格式显示
        if msg.attachments:
            for att in msg.attachments:
                # 下载附件
                local_path = await self.bot.media_downloader.download_attachment(att)
                if local_path:
                    # 计算相对路径
                    rel_path = os.path.relpath(local_path, self.download_dir)
                    content_parts.append(f"[{rel_path}]")
                else:
                    # 下载失败，显示类型
                    att_type = "图片" if att.is_image else "语音" if att.is_voice else "视频" if att.is_video else "文件"
                    content_parts.append(f"[{att_type}下载失败]")
        
        # 组合输出：始终显示头部，即使内容为空
        if content_parts:
            return f"{header} {' '.join(content_parts)}"
        else:
            return f"{header} [空消息]"
    
    def parse_outgoing_message(self, text: str) -> dict:
        """解析要发送的消息，提取文本和文件路径"""
        # 匹配 [路径] 格式
        import re
        pattern = r'\[([^\]]+)\]'
        
        text_parts = []
        media_files = []
        last_end = 0
        
        for match in re.finditer(pattern, text):
            # 添加路径前的文本
            if match.start() > last_end:
                text_parts.append(text[last_end:match.start()])
            
            path = match.group(1)
            # 检查uploads目录中是否存在该文件
            full_path = os.path.join(self.upload_dir, path)
            if os.path.exists(full_path):
                media_files.append(full_path)
            else:
                # 不是文件路径，保留原样
                text_parts.append(f"[{path}]")
            
            last_end = match.end()
        
        # 添加剩余文本
        if last_end < len(text):
            text_parts.append(text[last_end:])
        
        # 合并文本并反转义
        content = self.unescape_content("".join(text_parts).strip())
        
        return {
            "content": content,
            "media_files": media_files
        }
    
    def get_media_type(self, filepath: str) -> str:
        """根据文件扩展名判断媒体类型"""
        ext = os.path.splitext(filepath)[1].lower()
        
        image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
        voice_exts = ['.silk', '.slk', '.amr', '.wav', '.mp3', '.ogg', '.m4a']
        video_exts = ['.mp4', '.webm', '.mov', '.avi']
        
        if ext in image_exts:
            return "image"
        elif ext in voice_exts:
            return "voice"
        elif ext in video_exts:
            return "video"
        else:
            return "file"
    
    async def send_message(self, target: str, content: str, media_files: List[str]):
        """发送消息到指定目标"""
        try:
            # 解析目标
            if target.startswith("c2c:"):
                openid = target[4:]
                # 发送文本
                if content:
                    await self.bot.send_private_message(openid, content)
                # 发送媒体
                for filepath in media_files:
                    media_type = self.get_media_type(filepath)
                    print(f"[发送{media_type}] {filepath}", flush=True)
                    try:
                        if media_type == "image":
                            await self.bot.api.send_image(openid, image_path=filepath)
                        elif media_type == "voice":
                            await self.bot.api.send_voice(openid, voice_path=filepath)
                        elif media_type == "video":
                            # 视频暂时作为文件发送
                            await self.bot.api.send_file(openid, file_path=filepath)
                        else:
                            await self.bot.api.send_file(openid, file_path=filepath)
                        print(f"[发送成功]", flush=True)
                    except Exception as e:
                        print(f"[发送失败] {e}", flush=True)
                    await asyncio.sleep(0.5)  # 避免发送太快
                    
            elif target.startswith("group:"):
                group_openid = target[6:]
                if content:
                    await self.bot.send_group_message(group_openid, content)
                for filepath in media_files:
                    media_type = self.get_media_type(filepath)
                    print(f"[发送{media_type}] {filepath}", flush=True)
                    try:
                        if media_type == "image":
                            await self.bot.api.send_image(group_openid, image_path=filepath, is_group=True)
                        elif media_type == "voice":
                            await self.bot.api.send_voice(group_openid, voice_path=filepath, is_group=True)
                        elif media_type == "video":
                            await self.bot.api.send_file(group_openid, file_path=filepath, is_group=True)
                        else:
                            await self.bot.api.send_file(group_openid, file_path=filepath, is_group=True)
                        print(f"[发送成功]", flush=True)
                    except Exception as e:
                        print(f"[发送失败] {e}", flush=True)
                    await asyncio.sleep(0.5)
                    
            elif target.startswith("channel:"):
                channel_id = target[8:]
                if content:
                    await self.bot.send_channel_message(channel_id, content)
                    
        except Exception as e:
            print(f"[发送失败] {e}", flush=True)
    
    async def handle_message(self, msg: Message):
        """处理收到的消息"""
        # 保存最后收到的消息，用于回复
        self._last_message = msg
        
        # 设置当前回复目标
        if msg.is_private:
            self._current_target = f"c2c:{msg.author_id}"
        elif msg.is_group:
            self._current_target = f"group:{msg.group_openid}"
        elif msg.is_channel:
            self._current_target = f"channel:{msg.channel_id}"
        
        # 格式化并输出
        formatted = await self.format_incoming_message(msg)
        print(formatted, flush=True)
        
        # 测试模式：自动回复相同内容
        if self.test_mode:
            await self._test_mode_reply(msg)
    
    async def _test_mode_reply(self, msg: Message):
        """测试模式：回复相同内容"""
        try:
            # 回复文本内容
            if msg.content:
                await self.bot.reply(msg, msg.content)
                print(f"[测试模式] 已回复: {msg.content[:50]}...", flush=True)
            
            # 回复附件（下载后重新发送）
            for att in msg.attachments:
                local_path = await self.bot.media_downloader.download_attachment(att)
                if local_path:
                    is_group = msg.is_group
                    target_id = msg.group_openid if is_group else msg.author_id
                    
                    if att.is_image:
                        await self.bot.api.send_image(target_id, image_path=local_path, is_group=is_group)
                        print(f"[测试模式] 已回复图片", flush=True)
                    elif att.is_voice:
                        await self.bot.api.send_voice(target_id, voice_path=local_path, is_group=is_group)
                        print(f"[测试模式] 已回复语音", flush=True)
                    else:
                        await self.bot.api.send_file(target_id, file_path=local_path, is_group=is_group)
                        print(f"[测试模式] 已回复文件", flush=True)
                    
                    await asyncio.sleep(0.5)
                    
        except Exception as e:
            print(f"[测试模式回复失败] {e}", flush=True)
    
    async def reply_last(self, content: str, media_files: List[str]):
        """回复最后收到的消息"""
        if not self._last_message:
            print("[错误] 没有可回复的消息", flush=True)
            return
        
        try:
            # 发送文本
            if content:
                await self.bot.reply(self._last_message, content)
            
            # 发送媒体文件
            for filepath in media_files:
                media_type = self.get_media_type(filepath)
                is_group = self._last_message.is_group
                target_id = self._last_message.group_openid if is_group else self._last_message.author_id
                
                print(f"[发送{media_type}] {filepath}", flush=True)
                
                try:
                    if media_type == "image":
                        await self.bot.api.send_image(target_id, image_path=filepath, is_group=is_group)
                    elif media_type == "voice":
                        await self.bot.api.send_voice(target_id, voice_path=filepath, is_group=is_group)
                    elif media_type == "video":
                        await self.bot.api.send_file(target_id, file_path=filepath, is_group=is_group)
                    else:
                        await self.bot.api.send_file(target_id, file_path=filepath, is_group=is_group)
                    print(f"[发送成功]", flush=True)
                except Exception as e:
                    print(f"[发送失败] {e}", flush=True)
                
                await asyncio.sleep(0.5)
                
        except Exception as e:
            print(f"[回复失败] {e}", flush=True)
    
    async def process_command(self, line: str):
        """处理输入命令"""
        line = line.strip()
        if not line:
            return
        
        # 命令解析
        # 格式1: /target <目标>  - 设置回复目标
        # 格式2: /reply <内容>   - 回复最后收到的消息
        # 其他: 当作消息发送到当前目标
        
        if line.startswith("/target "):
            self._current_target = line[8:].strip()
            print(f"[目标已设置] {self._current_target}", flush=True)
            
        elif line.startswith("/reply "):
            if not self._last_message:
                print("[错误] 没有可回复的消息", flush=True)
                return
            content_part = line[7:]
            parsed = self.parse_outgoing_message(content_part)
            await self.reply_last(parsed["content"], parsed["media_files"])
            
        elif line.startswith("/help"):
            print("[帮助]", flush=True)
            print("  /target <目标>  - 设置发送目标 (如: c2c:xxx, group:xxx)", flush=True)
            print("  /reply <内容>   - 回复最后收到的消息", flush=True)
            print("  直接输入内容    - 发送到当前目标", flush=True)
            print("  [文件名]        - 发送uploads目录中的文件", flush=True)
            
        else:
            # 当作消息发送
            if not self._current_target:
                print("[错误] 未设置发送目标，使用 /target 设置", flush=True)
                return
            
            parsed = self.parse_outgoing_message(line)
            await self.send_message(
                self._current_target,
                parsed["content"],
                parsed["media_files"]
            )
    
    async def stdin_reader(self):
        """异步读取标准输入"""
        loop = asyncio.get_event_loop()
        
        while self._running:
            try:
                # 使用线程读取stdin，避免阻塞
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:  # EOF
                    break
                line = line.rstrip('\n\r')
                if line:
                    await self.process_command(line)
            except Exception as e:
                logger.error(f"读取输入失败: {e}")
                break
    
    async def start(self):
        """启动处理器"""
        self._running = True
        
        # 设置消息回调
        self.bot.on_message = self.handle_message
        
        # 在后台运行stdin读取
        stdin_task = asyncio.create_task(self.stdin_reader())
        
        # 运行机器人（会阻塞）
        try:
            await self.bot.start()
        finally:
            self._running = False
            stdin_task.cancel()


# ============== 主程序入口 ==============

import sys
import argparse

def main():
    """主程序入口"""
    # 默认配置（内置参数）
    DEFAULT_APP_ID = "APPID"
    DEFAULT_CLIENT_SECRET = "SECRET"
    DOWNLOAD_DIR = "downloads"
    UPLOAD_DIR = "uploads"
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='QQBot Python实现')
    parser.add_argument('appid', nargs='?', help='AppID')
    parser.add_argument('secret', nargs='?', help='ClientSecret')
    parser.add_argument('--test', action='store_true', help='测试模式：收到什么回复什么')
    args = parser.parse_args()
    
    # 确定使用的配置
    if args.appid and args.secret:
        APP_ID = args.appid
        CLIENT_SECRET = args.secret
        print(f"[使用命令行参数] AppID: {APP_ID}", flush=True)
    elif args.appid or args.secret:
        print("[错误] 请同时提供 AppID 和 ClientSecret", flush=True)
        print("用法: python qqbot.py <AppID> <ClientSecret> [--test]", flush=True)
        sys.exit(1)
    else:
        APP_ID = DEFAULT_APP_ID
        CLIENT_SECRET = DEFAULT_CLIENT_SECRET
        print("[使用内置配置启动]", flush=True)
    
    if args.test:
        print("[测试模式] 已启用，将自动回复相同内容", flush=True)
    
    # 创建机器人
    bot = QQBot(
        app_id=APP_ID,
        client_secret=CLIENT_SECRET,
        name="PythonBot",
        download_dir=DOWNLOAD_DIR
    )
    
    # 创建标准IO处理器
    handler = StdioHandler(
        bot,
        download_dir=DOWNLOAD_DIR,
        upload_dir=UPLOAD_DIR,
        test_mode=args.test
    )
    
    # 输出启动信息
    print("[QQBot已启动]", flush=True)
    print(f"[下载目录] {DOWNLOAD_DIR}/", flush=True)
    print(f"[上传目录] {UPLOAD_DIR}/", flush=True)
    if args.test:
        print("[测试模式] 自动回复已开启", flush=True)
    print("[输入 /help 查看命令]", flush=True)
    
    try:
        asyncio.run(handler.start())
    except KeyboardInterrupt:
        print("\n[QQBot已停止]", flush=True)


if __name__ == "__main__":
    main()
