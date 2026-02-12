"""Qwen model-related data structures."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum


class QwenModel(Enum):
    """Qwen 模型枚举"""
    QWEN_TURBO = "qwen-turbo"
    QWEN_PLUS = "qwen-plus"
    QWEN_MAX = "qwen-max"
    QWEN_MAX_LONGCONTEXT = "qwen-max-longcontext"
    QWEN_LOCAL = "qwen-local"
    # Qwen 2.5 系列
    QWEN2_5_72B = "qwen2.5-72b-instruct"
    QWEN2_5_32B = "qwen2.5-32b-instruct"
    QWEN2_5_14B = "qwen2.5-14b-instruct"
    QWEN2_5_7B = "qwen2.5-7b-instruct"
    # Qwen 3 系列
    QWEN3_MAX = "qwen3-max"
    QWEN3_MAX_PREVIEW = "qwen3-max-preview"
    # Qwen VL 视觉系列
    QWEN_VL_MAX = "qwen-vl-max"
    QWEN_VL_PLUS = "qwen-vl-plus"
    QWEN2_VL_72B = "qwen2-vl-72b-instruct"
    # Qwen OCR 系列
    QWEN_VL_OCR = "qwen-vl-ocr"
    # ===== 第三方模型（百炼平台） =====
    # DeepSeek 系列
    DEEPSEEK_V3 = "deepseek-v3"
    DEEPSEEK_V3_2 = "deepseek-v3.2"
    DEEPSEEK_R1 = "deepseek-r1"
    # GLM 系列（智谱）
    GLM_4_PLUS = "glm-4-plus"
    GLM_4_5 = "glm-4.5"
    GLM_4_7 = "glm-4.7"
    # Kimi 系列（月之暗面）
    KIMI_K2_5 = "kimi-k2.5"

    def is_qwen_native(self) -> bool:
        """是否为 Qwen 原生模型（支持 enable_search/search_strategy/enable_code_interpreter）"""
        return self.value.startswith(("qwen", "qwen2", "qwen3"))

    def supports_thinking(self) -> bool:
        """是否支持 enable_thinking 参数"""
        # Qwen3 系列、DeepSeek R1/V3.2、GLM 4.5/4.6/4.7 支持
        # Kimi 系列目前不支持
        thinking_models = {
            QwenModel.QWEN3_MAX, QwenModel.QWEN3_MAX_PREVIEW,
            QwenModel.DEEPSEEK_V3, QwenModel.DEEPSEEK_V3_2, QwenModel.DEEPSEEK_R1,
            QwenModel.GLM_4_PLUS, QwenModel.GLM_4_5, QwenModel.GLM_4_7,
        }
        return self in thinking_models

    def is_vision_model(self) -> bool:
        """是否为视觉模型（需要使用 MultiModalConversation API）"""
        vision_models = {
            QwenModel.QWEN_VL_MAX, QwenModel.QWEN_VL_PLUS,
            QwenModel.QWEN2_VL_72B, QwenModel.QWEN_VL_OCR,
        }
        return self in vision_models

    def requires_multimodal_api(self) -> bool:
        """是否必须使用 MultiModalConversation API（即使是纯文本调用）
        
        某些第三方模型（如 kimi-k2.5）在 DashScope 原生 SDK 中
        只能通过 MultiModalConversation API 调用，不支持 Generation API。
        """
        return self in {QwenModel.KIMI_K2_5} or self.is_vision_model()


@dataclass
class QwenConfig:
    """Qwen 模型配置"""
    model: QwenModel = QwenModel.QWEN3_MAX  # 默认使用 qwen3-max
    api_key: Optional[str] = None
    base_url: Optional[str] = None  # 用于本地部署
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    timeout: float = 120.0  # 增加超时时间到 120 秒
    retry_attempts: int = 5
    top_p: float = 0.8
    enable_search: bool = True  # 是否启用联网搜索功能
    search_strategy: Optional[str] = None  # 搜索策略: None=普通搜索, "agent_max"=启用网页抽取（需模型支持）
    enable_thinking: bool = True  # 是否启用深度思考功能
    enable_code_interpreter: bool = False  # 是否启用代码解释器（仅支持流式调用，需启用思考模式）
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "model": self.model.value,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "retry_attempts": self.retry_attempts,
            "top_p": self.top_p,
            "enable_search": self.enable_search,
            "search_strategy": self.search_strategy,
            "enable_code_interpreter": self.enable_code_interpreter,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QwenConfig":
        """从字典反序列化"""
        model_value = data.get("model", "qwen-plus")
        # 尝试匹配枚举值
        model = QwenModel.QWEN_PLUS
        for m in QwenModel:
            if m.value == model_value:
                model = m
                break
        
        return cls(
            model=model,
            api_key=data.get("api_key"),
            base_url=data.get("base_url"),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens"),
            timeout=data.get("timeout", 60.0),
            retry_attempts=data.get("retry_attempts", 3),
            top_p=data.get("top_p", 0.8),
            enable_search=data.get("enable_search", True),
            search_strategy=data.get("search_strategy"),
            enable_code_interpreter=data.get("enable_code_interpreter", False),
        )


@dataclass
class Message:
    """消息数据结构 - 支持纯文本和多模态内容"""
    role: str  # "system", "user", "assistant", "tool"
    content: Any  # str 或 list[dict]（多模态：[{"image": url}, {"text": prompt}]）
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为 API 格式"""
        result: Dict[str, Any] = {
            "role": self.role,
            "content": self.content,  # str 或 list 均可直接传递给 DashScope
        }
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """从字典创建"""
        return cls(
            role=data["role"],
            content=data.get("content", ""),
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
        )


@dataclass
class QwenResponse:
    """Qwen 响应数据结构"""
    content: str
    tool_calls: Optional[List[Dict[str, Any]]]
    finish_reason: str
    usage: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "content": self.content,
            "tool_calls": self.tool_calls,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QwenResponse":
        """从字典反序列化"""
        return cls(
            content=data.get("content", ""),
            tool_calls=data.get("tool_calls"),
            finish_reason=data.get("finish_reason", "stop"),
            usage=data.get("usage", {}),
        )
