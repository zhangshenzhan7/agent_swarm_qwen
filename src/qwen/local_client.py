"""Local Qwen model client using OpenAI-compatible API."""

import os
from typing import List, Dict, Any, Optional, AsyncIterator

from .interface import IQwenClient
from .models import Message, QwenResponse, QwenConfig, QwenModel
from .dashscope_client import MODEL_CONTEXT_WINDOWS


class LocalQwenClient(IQwenClient):
    """本地 Qwen 模型客户端（兼容 OpenAI API 格式）"""
    
    def __init__(self, config: Optional[QwenConfig] = None):
        """
        初始化本地 Qwen 客户端
        
        Args:
            config: Qwen 配置，如果未提供则使用默认配置
        """
        self._config = config or QwenConfig(model=QwenModel.QWEN_LOCAL)
        self._base_url = self._config.base_url or os.environ.get(
            "QWEN_LOCAL_BASE_URL", "http://localhost:8000/v1"
        )
        self._api_key = self._config.api_key or os.environ.get(
            "QWEN_LOCAL_API_KEY", "not-needed"
        )
        self._client = None
    
    def _get_client(self):
        """获取或创建 OpenAI 客户端"""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError(
                    "openai package is required. Install with: pip install openai"
                )
            
            self._client = AsyncOpenAI(
                base_url=self._base_url,
                api_key=self._api_key,
            )
        return self._client
    
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
        import asyncio
        
        client = self._get_client()
        effective_config = config or self._config
        
        # 构建请求参数
        request_messages = [msg.to_dict() for msg in messages]
        
        kwargs: Dict[str, Any] = {
            "model": effective_config.model.value,
            "messages": request_messages,
            "temperature": effective_config.temperature,
            "top_p": effective_config.top_p,
        }
        
        if effective_config.max_tokens is not None:
            kwargs["max_tokens"] = effective_config.max_tokens
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(**kwargs),
                timeout=effective_config.timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Request timed out after {effective_config.timeout}s"
            )
        
        # 解析响应
        choice = response.choices[0]
        message = choice.message
        
        tool_calls = None
        if message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in message.tool_calls
            ]
        
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        
        return QwenResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
        )
    
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
        client = self._get_client()
        effective_config = config or self._config
        
        request_messages = [msg.to_dict() for msg in messages]
        
        kwargs: Dict[str, Any] = {
            "model": effective_config.model.value,
            "messages": request_messages,
            "temperature": effective_config.temperature,
            "top_p": effective_config.top_p,
            "stream": True,
        }
        
        if effective_config.max_tokens is not None:
            kwargs["max_tokens"] = effective_config.max_tokens
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        stream = await client.chat.completions.create(**kwargs)
        
        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
    
    async def health_check(self) -> bool:
        """
        检查模型服务健康状态
        
        Returns:
            服务是否健康
        """
        try:
            test_messages = [Message(role="user", content="Hi")]
            test_config = QwenConfig(
                model=self._config.model,
                base_url=self._base_url,
                api_key=self._api_key,
                max_tokens=10,
                timeout=10.0,
            )
            await self.chat(test_messages, config=test_config)
            return True
        except Exception:
            return False
    
    def get_token_count(self, text: str) -> int:
        """
        估算文本的 token 数量
        
        Args:
            text: 待估算的文本
            
        Returns:
            估算的 token 数量
        """
        if not text:
            return 0
        
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except ImportError:
            pass
        
        # 启发式方法
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        estimated = int(chinese_chars * 1.5 + other_chars * 0.25)
        return max(1, estimated)
    
    def get_context_window(self) -> int:
        """
        获取当前模型的上下文窗口大小
        
        Returns:
            上下文窗口大小（token 数）
        """
        return MODEL_CONTEXT_WINDOWS.get(self._config.model, 8192)
