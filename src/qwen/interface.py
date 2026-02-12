"""Qwen client interface."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncIterator

from .models import Message, QwenResponse, QwenConfig


class IQwenClient(ABC):
    """Qwen 模型客户端接口"""
    
    @abstractmethod
    async def chat(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        config: Optional[QwenConfig] = None
    ) -> QwenResponse:
        """
        发送聊天请求
        
        Args:
            messages: 消息历史
            tools: 可用工具定义
            config: 模型配置（覆盖默认配置）
            
        Returns:
            模型响应
        """
        pass
    
    @abstractmethod
    async def chat_stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        config: Optional[QwenConfig] = None
    ) -> AsyncIterator[str]:
        """
        流式聊天请求
        
        Args:
            messages: 消息历史
            tools: 可用工具定义
            config: 模型配置（覆盖默认配置）
            
        Yields:
            流式响应内容片段
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        检查模型服务健康状态
        
        Returns:
            服务是否健康
        """
        pass
    
    @abstractmethod
    def get_token_count(self, text: str) -> int:
        """
        估算文本的 token 数量
        
        Args:
            text: 待估算的文本
            
        Returns:
            估算的 token 数量
        """
        pass
    
    @abstractmethod
    def get_context_window(self) -> int:
        """
        获取当前模型的上下文窗口大小
        
        Returns:
            上下文窗口大小（token 数）
        """
        pass
