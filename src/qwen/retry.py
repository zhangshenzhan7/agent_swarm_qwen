"""Retry and fallback mechanisms for Qwen clients."""

import asyncio
import random
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from .interface import IQwenClient
from .models import Message, QwenResponse, QwenConfig, QwenModel


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    initial_delay: float = 1.0  # 秒
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True
    
    def get_delay(self, attempt: int) -> float:
        """
        计算重试延迟（指数退避）
        
        Args:
            attempt: 当前尝试次数（从 0 开始）
            
        Returns:
            延迟时间（秒）
        """
        delay = min(
            self.initial_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        if self.jitter:
            # 添加 ±50% 的随机抖动
            delay *= (0.5 + random.random())
        return delay


# 模型降级链
MODEL_FALLBACK_CHAIN: Dict[QwenModel, List[QwenModel]] = {
    QwenModel.QWEN_MAX: [QwenModel.QWEN_PLUS, QwenModel.QWEN_TURBO],
    QwenModel.QWEN_MAX_LONGCONTEXT: [QwenModel.QWEN_MAX, QwenModel.QWEN_PLUS],
    QwenModel.QWEN_PLUS: [QwenModel.QWEN_TURBO],
    QwenModel.QWEN_TURBO: [],  # 无降级选项
    QwenModel.QWEN_LOCAL: [],  # 本地模型无降级
    QwenModel.QWEN2_5_72B: [QwenModel.QWEN2_5_32B, QwenModel.QWEN2_5_14B],
    QwenModel.QWEN2_5_32B: [QwenModel.QWEN2_5_14B, QwenModel.QWEN2_5_7B],
    QwenModel.QWEN2_5_14B: [QwenModel.QWEN2_5_7B],
    QwenModel.QWEN2_5_7B: [],
}


class RetryableError(Exception):
    """可重试的错误"""
    pass


class NonRetryableError(Exception):
    """不可重试的错误"""
    pass


def is_retryable_error(error: Exception) -> bool:
    """
    判断错误是否可重试
    
    Args:
        error: 异常对象
        
    Returns:
        是否可重试
    """
    # 超时错误可重试
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        return True
    
    # 连接错误可重试
    error_str = str(error).lower()
    retryable_patterns = [
        "timeout",
        "connection",
        "network",
        "rate limit",
        "too many requests",
        "503",
        "502",
        "504",
        "429",
    ]
    
    for pattern in retryable_patterns:
        if pattern in error_str:
            return True
    
    return False


async def execute_with_retry(
    client: IQwenClient,
    messages: List[Message],
    tools: Optional[List[Dict[str, Any]]] = None,
    config: Optional[QwenConfig] = None,
    retry_config: Optional[RetryConfig] = None,
) -> QwenResponse:
    """
    带重试的模型调用
    
    Args:
        client: Qwen 客户端
        messages: 消息列表
        tools: 工具定义
        config: 模型配置
        retry_config: 重试配置
        
    Returns:
        模型响应
        
    Raises:
        Exception: 所有重试都失败后抛出最后一个异常
    """
    retry_cfg = retry_config or RetryConfig()
    last_error: Optional[Exception] = None
    
    for attempt in range(retry_cfg.max_attempts):
        try:
            return await client.chat(messages, tools=tools, config=config)
        except Exception as e:
            last_error = e
            
            if not is_retryable_error(e):
                raise
            
            if attempt < retry_cfg.max_attempts - 1:
                delay = retry_cfg.get_delay(attempt)
                await asyncio.sleep(delay)
    
    raise last_error or Exception("All retry attempts failed")


async def execute_with_fallback(
    client: IQwenClient,
    messages: List[Message],
    tools: Optional[List[Dict[str, Any]]] = None,
    config: Optional[QwenConfig] = None,
    retry_config: Optional[RetryConfig] = None,
) -> QwenResponse:
    """
    带降级的模型调用
    
    当主模型调用失败时，自动尝试降级到更小的模型。
    
    Args:
        client: Qwen 客户端
        messages: 消息列表
        tools: 工具定义
        config: 模型配置
        retry_config: 重试配置
        
    Returns:
        模型响应
        
    Raises:
        Exception: 所有模型都失败后抛出异常
    """
    effective_config = config or QwenConfig()
    retry_cfg = retry_config or RetryConfig()
    
    # 构建要尝试的模型列表
    models_to_try = [effective_config.model]
    models_to_try.extend(MODEL_FALLBACK_CHAIN.get(effective_config.model, []))
    
    last_error: Optional[Exception] = None
    
    for model in models_to_try:
        # 创建当前模型的配置
        current_config = QwenConfig(
            model=model,
            api_key=effective_config.api_key,
            base_url=effective_config.base_url,
            temperature=effective_config.temperature,
            max_tokens=effective_config.max_tokens,
            timeout=effective_config.timeout,
            retry_attempts=effective_config.retry_attempts,
            top_p=effective_config.top_p,
        )
        
        # 尝试使用当前模型
        for attempt in range(retry_cfg.max_attempts):
            try:
                return await client.chat(messages, tools=tools, config=current_config)
            except Exception as e:
                last_error = e
                
                if not is_retryable_error(e):
                    # 不可重试的错误，尝试下一个模型
                    break
                
                if attempt < retry_cfg.max_attempts - 1:
                    delay = retry_cfg.get_delay(attempt)
                    await asyncio.sleep(delay)
    
    raise Exception(
        f"All models failed. Last error: {last_error}"
    ) from last_error


class ResilientQwenClient(IQwenClient):
    """
    带弹性机制的 Qwen 客户端包装器
    
    自动处理重试和模型降级。
    """
    
    def __init__(
        self,
        client: IQwenClient,
        retry_config: Optional[RetryConfig] = None,
        enable_fallback: bool = True,
    ):
        """
        初始化弹性客户端
        
        Args:
            client: 底层 Qwen 客户端
            retry_config: 重试配置
            enable_fallback: 是否启用模型降级
        """
        self._client = client
        self._retry_config = retry_config or RetryConfig()
        self._enable_fallback = enable_fallback
    
    async def chat(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        config: Optional[QwenConfig] = None
    ) -> QwenResponse:
        """发送聊天请求（带重试和降级）"""
        if self._enable_fallback:
            return await execute_with_fallback(
                self._client,
                messages,
                tools=tools,
                config=config,
                retry_config=self._retry_config,
            )
        else:
            return await execute_with_retry(
                self._client,
                messages,
                tools=tools,
                config=config,
                retry_config=self._retry_config,
            )
    
    async def chat_stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        config: Optional[QwenConfig] = None
    ):
        """流式聊天请求（直接转发，不支持重试）"""
        async for chunk in self._client.chat_stream(messages, tools=tools, config=config):
            yield chunk
    
    async def health_check(self) -> bool:
        """检查服务健康状态"""
        return await self._client.health_check()
    
    def get_token_count(self, text: str) -> int:
        """估算 token 数量"""
        return self._client.get_token_count(text)
    
    def get_context_window(self) -> int:
        """获取上下文窗口大小"""
        return self._client.get_context_window()
