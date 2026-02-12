"""Pydantic 数据模型"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel


class TaskCreate(BaseModel):
    content: str
    output_type: str = "auto"
    metadata: Optional[Dict[str, Any]] = None


class TaskCreateWithFiles(BaseModel):
    """支持文件的任务创建"""
    content: str
    files: Optional[List[Dict[str, Any]]] = None
    output_type: str = "auto"
    metadata: Optional[Dict[str, Any]] = None


class ApiKeyUpdate(BaseModel):
    api_key: str


class AgentCreate(BaseModel):
    """创建智能体请求"""
    name: str
    role_key: str
    description: str
    agent_type: str
    capabilities: List[str]
    model_id: str
    system_prompt: str
    avatar: str = "🤖"
    available_tools: List[str] = []
    temperature: float = 0.7
    priority: int = 5
    tags: List[str] = []


class AgentUpdate(BaseModel):
    """更新智能体请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    avatar: Optional[str] = None
    available_tools: Optional[List[str]] = None
    is_enabled: Optional[bool] = None
    priority: Optional[int] = None
    tags: Optional[List[str]] = None
    model_id: Optional[str] = None
    temperature: Optional[float] = None


class TextToImageRequest(BaseModel):
    """文生图请求"""
    prompt: str
    model: str = "wanx2.1-t2i-turbo"
    size: str = "1024*1024"
    n: int = 1
    negative_prompt: str = ""
    seed: Optional[int] = None


class TextToVideoRequest(BaseModel):
    """文生视频请求"""
    prompt: str
    model: str = "wanx2.1-t2v-turbo"
    size: str = "1280*720"
    duration: int = 5
    seed: Optional[int] = None


class ImageToVideoRequest(BaseModel):
    """图生视频请求"""
    image_url: str
    prompt: str = ""
    model: str = "wanx2.1-i2v-turbo"
    duration: int = 5
    seed: Optional[int] = None


class TextToSpeechRequest(BaseModel):
    """文字转语音请求"""
    text: str
    model: str = "cosyvoice-v1"
    voice: str = "longxiaochun"
    format: str = "mp3"


class ExecutionModeUpdate(BaseModel):
    """执行模式更新请求"""
    mode: str  # 'scheduler' 或 'team'


class SandboxConfigUpdate(BaseModel):
    """沙箱代码解释器配置更新"""
    sandbox_account_id: Optional[str] = None  # 阿里云主账号 ID
    sandbox_access_key_id: Optional[str] = None  # 阿里云 AK
    sandbox_access_key_secret: Optional[str] = None  # 阿里云 SK
    sandbox_region_id: str = "cn-hangzhou"
    sandbox_template_name: str = "python-sandbox"
    sandbox_idle_timeout: int = 3600
