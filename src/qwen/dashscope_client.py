"""DashScope API client for Qwen models."""

import os
import asyncio
import queue
import threading
from typing import List, Dict, Any, Optional, AsyncIterator

from .interface import IQwenClient
from .models import Message, QwenResponse, QwenConfig, QwenModel


# 模型上下文窗口大小映射
MODEL_CONTEXT_WINDOWS = {
    QwenModel.QWEN_TURBO: 8192,
    QwenModel.QWEN_PLUS: 32768,
    QwenModel.QWEN_MAX: 32768,
    QwenModel.QWEN_MAX_LONGCONTEXT: 131072,
    QwenModel.QWEN_LOCAL: 8192,
    QwenModel.QWEN2_5_72B: 131072,
    QwenModel.QWEN2_5_32B: 131072,
    QwenModel.QWEN2_5_14B: 131072,
    QwenModel.QWEN2_5_7B: 131072,
    # Qwen 3 系列
    QwenModel.QWEN3_MAX: 32768,
    QwenModel.QWEN3_MAX_PREVIEW: 32768,
    # ===== 第三方模型 =====
    QwenModel.DEEPSEEK_V3: 131072,
    QwenModel.DEEPSEEK_V3_2: 131072,
    QwenModel.DEEPSEEK_R1: 65536,
    QwenModel.GLM_4_PLUS: 131072,
    QwenModel.GLM_4_5: 131072,
    QwenModel.GLM_4_7: 131072,
    QwenModel.KIMI_K2_5: 131072,
}


def _is_retryable_error(e: Exception) -> bool:
    """判断是否为可重试的瞬态错误（限流、连接重置等）"""
    if isinstance(e, (ConnectionResetError, ConnectionError, asyncio.TimeoutError)):
        return True
    err_str = str(e)
    # DashScope 限流错误
    if "Throttling" in err_str or "RateQuota" in err_str or "rate limit" in err_str.lower():
        return True
    # 连接类错误
    if "Connection" in err_str or "reset" in err_str.lower():
        return True
    # 服务端临时错误
    if "InternalError" in err_str or "ServiceUnavailable" in err_str or "502" in err_str or "503" in err_str:
        return True
    return False


def _retry_wait_time(attempt: int, is_rate_limit: bool = False) -> float:
    """计算重试等待时间（秒），限流错误使用更长的退避"""
    if is_rate_limit:
        # 限流：5s, 15s, 30s, 60s（更长退避，给 API 恢复时间）
        return min(5 * (2 ** attempt), 60)
    # 普通瞬态错误：2s, 4s, 8s
    return min(2 * (2 ** attempt), 16)


def _is_rate_limit_error(e: Exception) -> bool:
    """判断是否为限流错误"""
    err_str = str(e)
    return "Throttling" in err_str or "RateQuota" in err_str or "rate limit" in err_str.lower()


class DashScopeClient(IQwenClient):
    """阿里云 DashScope API 客户端"""
    
    def __init__(self, config: Optional[QwenConfig] = None):
        """
        初始化 DashScope 客户端
        
        Args:
            config: Qwen 配置，如果未提供则使用默认配置
        """
        self._config = config or QwenConfig()
        self._api_key = self._config.api_key or os.environ.get("DASHSCOPE_API_KEY")
        
        if not self._api_key:
            raise ValueError(
                "DashScope API key is required. "
                "Set DASHSCOPE_API_KEY environment variable or pass api_key in config."
            )
    
    async def chat(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        config: Optional[QwenConfig] = None
    ) -> QwenResponse:
        """
        发送聊天请求（带重试机制）
        
        当 enable_search=True 时，自动使用流式模式（Web Extractor 不支持非流式），
        内部收集所有 chunk 后返回统一的 QwenResponse，对调用方透明。
        
        Args:
            messages: 消息历史
            tools: 可用工具定义
            config: 模型配置（覆盖默认配置）
            
        Returns:
            模型响应
        """
        # 延迟导入以避免在未安装时报错
        try:
            from dashscope import Generation
        except ImportError:
            raise ImportError(
                "dashscope package is required. Install with: pip install dashscope"
            )
        
        effective_config = config or self._config
        max_retries = effective_config.retry_attempts
        
        # 构建请求参数
        request_messages = [msg.to_dict() for msg in messages]
        
        kwargs: Dict[str, Any] = {
            "model": effective_config.model.value,
            "messages": request_messages,
            "temperature": effective_config.temperature,
            "top_p": effective_config.top_p,
            "result_format": "message",
        }
        
        if effective_config.max_tokens is not None:
            kwargs["max_tokens"] = effective_config.max_tokens
        
        # 启用联网搜索功能
        # 注意：enable_search 开启时进入 agent 模式，不支持自定义 tools
        # 仅 Qwen 原生模型支持
        if effective_config.enable_search and effective_config.model.is_qwen_native():
            kwargs["enable_search"] = True
            if effective_config.search_strategy:
                kwargs["search_options"] = {"search_strategy": effective_config.search_strategy}
        
        # 深度思考开关：仅对支持的模型传递
        if effective_config.model.supports_thinking():
            kwargs["enable_thinking"] = effective_config.enable_thinking
        
        # 启用代码解释器（仅 Qwen 原生模型，流式调用，需 enable_thinking=True）
        if effective_config.enable_code_interpreter and effective_config.model.is_qwen_native():
            kwargs["enable_code_interpreter"] = True
            kwargs["enable_thinking"] = True
        
        # enable_search 的 agent 模式与自定义 tools 互斥
        if tools and not kwargs.get("enable_search"):
            kwargs["tools"] = tools
        
        # 需要流式模式的场景（仅 Qwen 原生模型有效）：
        # 1. search_strategy 明确设置时（如 "agent_max"），Web Extractor 不支持非流式
        # 2. enable_code_interpreter=True，代码解释器仅支持流式调用
        use_stream = (
            bool(kwargs.get("enable_search") and effective_config.search_strategy)
            or kwargs.get("enable_code_interpreter", False)
        )
        
        # 检测是否需要使用 MultiModalConversation API
        use_multimodal_api = effective_config.model.requires_multimodal_api()
        
        last_error = None
        for attempt in range(max_retries):
            try:
                loop = asyncio.get_event_loop()
                
                if use_stream:
                    # 流式模式：内部收集所有 chunk 后返回完整 QwenResponse
                    response = await self._chat_stream_collect(
                        kwargs, effective_config, loop
                    )
                    return response
                elif use_multimodal_api:
                    # MultiModalConversation API（kimi-k2.5 等模型必须走此路径）
                    response = await self._multimodal_chat(
                        request_messages, effective_config, loop
                    )
                    return response
                else:
                    # 非流式模式：直接调用
                    response = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: Generation.call(api_key=self._api_key, **kwargs)
                        ),
                        timeout=effective_config.timeout
                    )
                    
                    # 解析响应
                    if response.status_code != 200:
                        raise Exception(
                            f"DashScope API error: {response.code} - {response.message}"
                        )
                    
                    output = response.output
                    choice = output.get("choices", [{}])[0]
                    message = choice.get("message", {})
                    
                    return QwenResponse(
                        content=message.get("content", ""),
                        tool_calls=message.get("tool_calls"),
                        finish_reason=choice.get("finish_reason", "stop"),
                        usage=response.usage or {},
                    )
                
            except (ConnectionResetError, ConnectionError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    is_rl = _is_rate_limit_error(e)
                    wait_time = _retry_wait_time(attempt, is_rl)
                    print(f"[DashScope] {'限流' if is_rl else '连接错误'}，{wait_time:.0f}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(wait_time)
                continue
            except Exception as e:
                if _is_retryable_error(e):
                    last_error = e
                    if attempt < max_retries - 1:
                        is_rl = _is_rate_limit_error(e)
                        wait_time = _retry_wait_time(attempt, is_rl)
                        print(f"[DashScope] {'限流' if is_rl else '瞬态错误'}，{wait_time:.0f}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                        await asyncio.sleep(wait_time)
                    continue
                raise
        
        # 所有重试都失败
        raise last_error or Exception("All retry attempts failed")

    async def _multimodal_chat(
        self,
        request_messages: List[Dict[str, Any]],
        effective_config: QwenConfig,
        loop: asyncio.AbstractEventLoop,
    ) -> QwenResponse:
        """
        使用 MultiModalConversation API 调用模型。
        用于 kimi-k2.5 等必须走 MultiModalConversation 路径的模型。
        纯文本消息会自动转换为 [{"text": content}] 格式。
        """
        try:
            from dashscope import MultiModalConversation
        except ImportError:
            raise ImportError(
                "dashscope package is required. Install with: pip install dashscope"
            )

        # 转换消息格式：MultiModalConversation 要求 content 为 list[dict]
        mm_messages = []
        for msg in request_messages:
            content = msg.get("content")
            if isinstance(content, list):
                mm_messages.append({"role": msg["role"], "content": content})
            else:
                mm_messages.append({"role": msg["role"], "content": [{"text": content or ""}]})

        api_key = self._api_key
        model = effective_config.model.value

        def call():
            return MultiModalConversation.call(
                api_key=api_key,
                model=model,
                messages=mm_messages,
            )

        response = await asyncio.wait_for(
            loop.run_in_executor(None, call),
            timeout=effective_config.timeout,
        )

        if response.status_code != 200:
            raise Exception(
                f"DashScope API error: {response.code} - {response.message}"
            )

        output = response.output
        choice = output.get("choices", [{}])[0]
        message_data = choice.get("message", {})
        # MultiModalConversation 返回的 content 可能是 list[dict]
        raw_content = message_data.get("content", "")
        if isinstance(raw_content, list):
            text_parts = [
                item.get("text", "")
                for item in raw_content
                if isinstance(item, dict) and "text" in item
            ]
            content_str = "".join(text_parts)
        else:
            content_str = str(raw_content) if raw_content else ""

        return QwenResponse(
            content=content_str,
            tool_calls=message_data.get("tool_calls"),
            finish_reason=choice.get("finish_reason", "stop"),
            usage=response.usage or {},
        )

    async def _chat_stream_collect(
        self,
        kwargs: Dict[str, Any],
        effective_config: QwenConfig,
        loop: asyncio.AbstractEventLoop,
    ) -> QwenResponse:
        """
        使用流式模式调用 API 并收集所有 chunk 为完整的 QwenResponse。
        用于 enable_search=True 等需要流式模式的场景。
        """
        from dashscope import Generation
        
        stream_kwargs = dict(kwargs)
        stream_kwargs["stream"] = True
        stream_kwargs["incremental_output"] = True
        
        api_key = self._api_key
        
        def stream_call():
            collected_content = []
            last_usage = {}
            last_finish_reason = "stop"
            last_tool_calls = None
            
            responses = Generation.call(api_key=api_key, **stream_kwargs)
            for response in responses:
                if response.status_code != 200:
                    raise Exception(
                        f"DashScope API error: {response.code} - {response.message}"
                    )
                
                output = response.output
                choices = output.get("choices", [])
                if choices:
                    message = choices[0].get("message", {})
                    content = message.get("content", "")
                    if content:
                        collected_content.append(content)
                    tool_calls = message.get("tool_calls")
                    if tool_calls:
                        last_tool_calls = tool_calls
                    finish_reason = choices[0].get("finish_reason")
                    if finish_reason and finish_reason != "null":
                        last_finish_reason = finish_reason
                
                if response.usage:
                    last_usage = response.usage
            
            return {
                "content": "".join(collected_content),
                "tool_calls": last_tool_calls,
                "finish_reason": last_finish_reason,
                "usage": last_usage,
            }
        
        result = await asyncio.wait_for(
            loop.run_in_executor(None, stream_call),
            timeout=effective_config.timeout
        )
        
        return QwenResponse(
            content=result["content"],
            tool_calls=result["tool_calls"],
            finish_reason=result["finish_reason"],
            usage=result["usage"],
        )
    
    async def _vision_chat_stream(
        self,
        request_messages: List[Dict[str, Any]],
        effective_config: "QwenConfig",
    ) -> AsyncIterator[str]:
        """视觉模型流式调用 — 使用 MultiModalConversation API"""
        try:
            from dashscope import MultiModalConversation
        except ImportError:
            raise ImportError(
                "dashscope package is required. Install with: pip install dashscope"
            )

        max_retries = effective_config.retry_attempts
        api_key = self._api_key

        # MultiModalConversation 的消息格式：content 为 [{"image": url}, {"text": "..."}]
        # 与 OpenAI 兼容格式不同，不需要 type 字段
        vl_messages = []
        for msg in request_messages:
            content = msg.get("content")
            if isinstance(content, list):
                # 已经是多模态格式，直接使用
                vl_messages.append({"role": msg["role"], "content": content})
            else:
                # 纯文本消息
                vl_messages.append({"role": msg["role"], "content": [{"text": content}]})

        last_error = None
        for attempt in range(max_retries):
            try:
                chunk_queue: queue.Queue = queue.Queue()
                error_holder = [None]

                def stream_worker():
                    try:
                        responses = MultiModalConversation.call(
                            api_key=api_key,
                            model=effective_config.model.value,
                            messages=vl_messages,
                            stream=True,
                            incremental_output=True,
                        )
                        for response in responses:
                            if response.status_code == 200:
                                output = response.output
                                choices = output.get("choices", [])
                                if choices:
                                    message_data = choices[0].get("message", {})
                                    # VL 模型返回的 content 可能是 list
                                    raw_content = message_data.get("content", "")
                                    if isinstance(raw_content, list):
                                        text_parts = [
                                            item.get("text", "")
                                            for item in raw_content
                                            if isinstance(item, dict) and "text" in item
                                        ]
                                        text = "".join(text_parts)
                                    else:
                                        text = str(raw_content) if raw_content else ""
                                    if text:
                                        chunk_queue.put(("chunk", text))
                            else:
                                error_holder[0] = Exception(
                                    f"DashScope API error: {response.code} - {response.message}"
                                )
                                break
                    except Exception as e:
                        error_holder[0] = e
                    finally:
                        chunk_queue.put(("done", None))

                thread = threading.Thread(target=stream_worker, daemon=True)
                thread.start()

                loop = asyncio.get_event_loop()
                has_output = False
                while True:
                    try:
                        item = await loop.run_in_executor(
                            None, lambda: chunk_queue.get(timeout=0.1)
                        )
                        msg_type, content = item
                        if msg_type == "done":
                            if error_holder[0]:
                                raise error_holder[0]
                            break
                        elif msg_type == "chunk":
                            has_output = True
                            yield content
                    except queue.Empty:
                        await asyncio.sleep(0.01)
                        continue

                if has_output:
                    return

            except (ConnectionResetError, ConnectionError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    is_rl = _is_rate_limit_error(e)
                    wait_time = _retry_wait_time(attempt, is_rl)
                    print(f"[DashScope VL Stream] {'限流' if is_rl else '连接错误'}，{wait_time:.0f}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(wait_time)
                continue
            except Exception as e:
                if _is_retryable_error(e):
                    last_error = e
                    if attempt < max_retries - 1:
                        is_rl = _is_rate_limit_error(e)
                        wait_time = _retry_wait_time(attempt, is_rl)
                        print(f"[DashScope VL Stream] {'限流' if is_rl else '瞬态错误'}，{wait_time:.0f}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                        await asyncio.sleep(wait_time)
                    continue
                raise

        if last_error:
            raise last_error

    async def chat_stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        config: Optional[QwenConfig] = None
    ) -> AsyncIterator[str]:
        """
        流式聊天请求（带重试机制）
        
        Args:
            messages: 消息历史
            tools: 可用工具定义
            config: 模型配置（覆盖默认配置）
            
        Yields:
            流式响应内容片段
        """
        try:
            from dashscope import Generation
        except ImportError:
            raise ImportError(
                "dashscope package is required. Install with: pip install dashscope"
            )
        
        effective_config = config or self._config
        max_retries = effective_config.retry_attempts
        request_messages = [msg.to_dict() for msg in messages]

        # 检测是否为视觉模型 + 多模态内容（content 为 list 格式）
        is_vision_call = effective_config.model.is_vision_model() and any(
            isinstance(msg.get("content"), list) for msg in request_messages
        )

        # 需要走 MultiModalConversation API 的模型（如 kimi-k2.5），即使是纯文本
        use_multimodal_api = effective_config.model.requires_multimodal_api()

        if is_vision_call or use_multimodal_api:
            # ========== MultiModalConversation API ==========
            # 对纯文本消息，需要将 content 转换为 [{"text": content}] 格式
            mm_messages = []
            for msg in request_messages:
                content = msg.get("content")
                if isinstance(content, list):
                    mm_messages.append({"role": msg["role"], "content": content})
                else:
                    mm_messages.append({"role": msg["role"], "content": [{"text": content or ""}]})
            async for chunk in self._vision_chat_stream(mm_messages, effective_config):
                yield chunk
            return
        
        kwargs: Dict[str, Any] = {
            "model": effective_config.model.value,
            "messages": request_messages,
            "temperature": effective_config.temperature,
            "top_p": effective_config.top_p,
            "result_format": "message",
            "stream": True,
            "incremental_output": True,
        }
        
        if effective_config.max_tokens is not None:
            kwargs["max_tokens"] = effective_config.max_tokens
        
        # 启用联网搜索功能
        # 注意：enable_search 开启时进入 agent 模式，不支持自定义 tools
        # 仅 Qwen 原生模型支持
        if effective_config.enable_search and effective_config.model.is_qwen_native():
            kwargs["enable_search"] = True
            if effective_config.search_strategy:
                kwargs["search_options"] = {"search_strategy": effective_config.search_strategy}
        
        # 深度思考开关：仅对支持的模型传递
        if effective_config.model.supports_thinking():
            kwargs["enable_thinking"] = effective_config.enable_thinking
        
        # 启用代码解释器（仅 Qwen 原生模型，流式调用，需 enable_thinking=True）
        if effective_config.enable_code_interpreter and effective_config.model.is_qwen_native():
            kwargs["enable_code_interpreter"] = True
            kwargs["enable_thinking"] = True
        
        # enable_search 的 agent 模式与自定义 tools 互斥
        if tools and not kwargs.get("enable_search"):
            kwargs["tools"] = tools
        
        last_error = None
        for attempt in range(max_retries):
            try:
                # 使用队列实现真正的异步流式输出
                chunk_queue: queue.Queue = queue.Queue()
                error_holder = [None]  # 用于存储错误
                
                def stream_worker():
                    """在后台线程中执行流式调用"""
                    try:
                        responses = Generation.call(api_key=self._api_key, **kwargs)
                        for response in responses:
                            if response.status_code == 200:
                                output = response.output
                                choices = output.get("choices", [])
                                if choices:
                                    message = choices[0].get("message", {})
                                    # 获取 thinking 内容（深度思考过程）
                                    reasoning_content = message.get("reasoning_content", "")
                                    if reasoning_content:
                                        chunk_queue.put(("thinking", reasoning_content))
                                    # 获取正常内容
                                    content = message.get("content", "")
                                    if content:
                                        chunk_queue.put(("chunk", content))
                            else:
                                error_holder[0] = Exception(
                                    f"DashScope API error: {response.code} - {response.message}"
                                )
                                break
                    except Exception as e:
                        error_holder[0] = e
                    finally:
                        chunk_queue.put(("done", None))
                
                # 启动后台线程
                thread = threading.Thread(target=stream_worker, daemon=True)
                thread.start()
                
                # 异步读取队列
                loop = asyncio.get_event_loop()
                has_output = False
                while True:
                    # 非阻塞方式从队列获取数据
                    try:
                        item = await loop.run_in_executor(None, lambda: chunk_queue.get(timeout=0.1))
                        msg_type, content = item
                        
                        if msg_type == "done":
                            if error_holder[0]:
                                raise error_holder[0]
                            break
                        elif msg_type == "thinking":
                            # 输出 thinking 内容，带特殊标记
                            # 注意：incremental_output=True 时每个 chunk 是增量内容
                            # 直接拼接即可，不需要每个 chunk 都包裹标签
                            has_output = True
                            yield f"[THINKING]{content}[/THINKING]"
                        elif msg_type == "chunk":
                            has_output = True
                            yield content
                    except queue.Empty:
                        # 队列为空，继续等待
                        await asyncio.sleep(0.01)
                        continue
                
                # 成功完成，退出重试循环
                if has_output:
                    return
                    
            except (ConnectionResetError, ConnectionError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    is_rl = _is_rate_limit_error(e)
                    wait_time = _retry_wait_time(attempt, is_rl)
                    print(f"[DashScope Stream] {'限流' if is_rl else '连接错误'}，{wait_time:.0f}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(wait_time)
                continue
            except Exception as e:
                if _is_retryable_error(e):
                    last_error = e
                    if attempt < max_retries - 1:
                        is_rl = _is_rate_limit_error(e)
                        wait_time = _retry_wait_time(attempt, is_rl)
                        print(f"[DashScope Stream] {'限流' if is_rl else '瞬态错误'}，{wait_time:.0f}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                        await asyncio.sleep(wait_time)
                    continue
                raise
        
        # 所有重试都失败
        if last_error:
            raise last_error
    
    async def health_check(self) -> bool:
        """
        检查模型服务健康状态
        
        Returns:
            服务是否健康
        """
        try:
            # 发送一个简单的测试请求
            test_messages = [Message(role="user", content="Hi")]
            test_config = QwenConfig(
                model=self._config.model,
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
        
        使用简单的启发式方法：
        - 中文字符约 1.5 token/字
        - 英文单词约 1 token/词
        - 标点符号约 1 token
        
        Args:
            text: 待估算的文本
            
        Returns:
            估算的 token 数量
        """
        if not text:
            return 0
        
        # 尝试使用 tiktoken（如果可用）
        try:
            import tiktoken
            # 使用 cl100k_base 编码器作为近似
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except ImportError:
            pass
        
        # 回退到启发式方法
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        
        # 中文字符约 1.5 token，其他字符约 0.25 token（4字符/token）
        estimated = int(chinese_chars * 1.5 + other_chars * 0.25)
        return max(1, estimated)
    
    def get_context_window(self) -> int:
        """
        获取当前模型的上下文窗口大小
        
        Returns:
            上下文窗口大小（token 数）
        """
        return MODEL_CONTEXT_WINDOWS.get(self._config.model, 8192)
    
    # ==================== 多模态生成 API ====================
    
    async def text_to_image(
        self,
        prompt: str,
        model: str = "wanx2.1-t2i-turbo",
        size: str = "1024*1024",
        n: int = 1,
        negative_prompt: str = "",
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        文生图 - 使用通义万相模型根据文字描述生成图像
        
        Args:
            prompt: 图像描述提示词
            model: 模型名称，默认 wanx2.1-t2i-turbo
            size: 图像尺寸，如 "1024*1024", "1280*720"
            n: 生成图像数量
            negative_prompt: 负面提示词（不希望出现的内容）
            seed: 随机种子（用于复现结果）
            
        Returns:
            包含图像URL的结果字典
        """
        try:
            from dashscope import ImageSynthesis
        except ImportError:
            raise ImportError(
                "dashscope package is required. Install with: pip install dashscope"
            )
        
        # 构建请求参数
        kwargs = {
            "api_key": self._api_key,
            "model": model,
            "prompt": prompt,
            "n": n,
            "size": size,
        }
        
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt
        if seed is not None:
            kwargs["seed"] = seed
        
        try:
            loop = asyncio.get_event_loop()
            max_retries = self._config.retry_attempts
            last_error = None

            for attempt in range(max_retries):
                try:
                    response = await loop.run_in_executor(
                        None,
                        lambda: ImageSynthesis.call(**kwargs)
                    )
                    
                    if response.status_code == 200:
                        results = response.output.get("results", [])
                        return {
                            "success": True,
                            "images": [{"url": r.get("url")} for r in results],
                            "task_id": response.output.get("task_id"),
                            "usage": response.usage,
                        }
                    else:
                        err = Exception(f"{response.code}: {response.message}")
                        if _is_retryable_error(err) and attempt < max_retries - 1:
                            is_rl = _is_rate_limit_error(err)
                            wait_time = _retry_wait_time(attempt, is_rl)
                            print(f"[DashScope 文生图] {'限流' if is_rl else '瞬态错误'}，{wait_time:.0f}秒后重试 ({attempt + 1}/{max_retries}): {err}")
                            await asyncio.sleep(wait_time)
                            last_error = err
                            continue
                        return {
                            "success": False,
                            "error": f"{response.code}: {response.message}",
                        }
                except Exception as e:
                    if _is_retryable_error(e) and attempt < max_retries - 1:
                        is_rl = _is_rate_limit_error(e)
                        wait_time = _retry_wait_time(attempt, is_rl)
                        print(f"[DashScope 文生图] {'限流' if is_rl else '瞬态错误'}，{wait_time:.0f}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                        await asyncio.sleep(wait_time)
                        last_error = e
                        continue
                    return {
                        "success": False,
                        "error": str(e),
                    }

            return {
                "success": False,
                "error": f"重试 {max_retries} 次后仍失败: {last_error}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    async def text_to_video(
        self,
        prompt: str,
        model: str = "wanx2.1-t2v-turbo",
        size: str = "1280*720",
        duration: int = 5,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        文生视频 - 使用通义万相模型根据文字描述生成视频
        
        Args:
            prompt: 视频描述提示词
            model: 模型名称，默认 wanx2.1-t2v-turbo
            size: 视频尺寸，如 "1280*720"
            duration: 视频时长（秒）
            seed: 随机种子
            
        Returns:
            包含视频URL的结果字典（异步任务）
        """
        try:
            from dashscope import VideoSynthesis
        except ImportError:
            raise ImportError(
                "dashscope package is required. Install with: pip install dashscope"
            )
        
        kwargs = {
            "api_key": self._api_key,
            "model": model,
            "prompt": prompt,
            "size": size,
            "duration": duration,
        }
        
        if seed is not None:
            kwargs["seed"] = seed
        
        try:
            loop = asyncio.get_event_loop()
            max_retries = self._config.retry_attempts
            last_error = None

            for attempt in range(max_retries):
                try:
                    # 提交异步任务
                    response = await loop.run_in_executor(
                        None,
                        lambda: VideoSynthesis.async_call(**kwargs)
                    )
                    
                    if response.status_code == 200:
                        task_id = response.output.get("task_id")
                        return {
                            "success": True,
                            "task_id": task_id,
                            "status": "processing",
                            "message": "视频生成任务已提交，请使用 task_id 查询结果",
                        }
                    else:
                        err = Exception(f"{response.code}: {response.message}")
                        if _is_retryable_error(err) and attempt < max_retries - 1:
                            is_rl = _is_rate_limit_error(err)
                            wait_time = _retry_wait_time(attempt, is_rl)
                            print(f"[DashScope 文生视频] {'限流' if is_rl else '瞬态错误'}，{wait_time:.0f}秒后重试 ({attempt + 1}/{max_retries}): {err}")
                            await asyncio.sleep(wait_time)
                            last_error = err
                            continue
                        return {
                            "success": False,
                            "error": f"{response.code}: {response.message}",
                        }
                except Exception as e:
                    if _is_retryable_error(e) and attempt < max_retries - 1:
                        is_rl = _is_rate_limit_error(e)
                        wait_time = _retry_wait_time(attempt, is_rl)
                        print(f"[DashScope 文生视频] {'限流' if is_rl else '瞬态错误'}，{wait_time:.0f}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                        await asyncio.sleep(wait_time)
                        last_error = e
                        continue
                    return {
                        "success": False,
                        "error": str(e),
                    }

            return {
                "success": False,
                "error": f"重试 {max_retries} 次后仍失败: {last_error}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    async def image_to_video(
        self,
        image_url: str,
        prompt: str = "",
        model: str = "wanx2.1-i2v-turbo",
        duration: int = 5,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        图生视频 - 使用通义万相模型将静态图片转换为动态视频
        
        Args:
            image_url: 输入图片的URL
            prompt: 动作描述提示词（可选）
            model: 模型名称，默认 wanx2.1-i2v-turbo
            duration: 视频时长（秒）
            seed: 随机种子
            
        Returns:
            包含视频URL的结果字典（异步任务）
        """
        try:
            from dashscope import VideoSynthesis
        except ImportError:
            raise ImportError(
                "dashscope package is required. Install with: pip install dashscope"
            )
        
        kwargs = {
            "api_key": self._api_key,
            "model": model,
            "image_url": image_url,
            "duration": duration,
        }
        
        if prompt:
            kwargs["prompt"] = prompt
        if seed is not None:
            kwargs["seed"] = seed
        
        try:
            loop = asyncio.get_event_loop()
            max_retries = self._config.retry_attempts
            last_error = None

            for attempt in range(max_retries):
                try:
                    response = await loop.run_in_executor(
                        None,
                        lambda: VideoSynthesis.async_call(**kwargs)
                    )
                    
                    if response.status_code == 200:
                        task_id = response.output.get("task_id")
                        return {
                            "success": True,
                            "task_id": task_id,
                            "status": "processing",
                            "message": "图生视频任务已提交，请使用 task_id 查询结果",
                        }
                    else:
                        err = Exception(f"{response.code}: {response.message}")
                        if _is_retryable_error(err) and attempt < max_retries - 1:
                            is_rl = _is_rate_limit_error(err)
                            wait_time = _retry_wait_time(attempt, is_rl)
                            print(f"[DashScope 图生视频] {'限流' if is_rl else '瞬态错误'}，{wait_time:.0f}秒后重试 ({attempt + 1}/{max_retries}): {err}")
                            await asyncio.sleep(wait_time)
                            last_error = err
                            continue
                        return {
                            "success": False,
                            "error": f"{response.code}: {response.message}",
                        }
                except Exception as e:
                    if _is_retryable_error(e) and attempt < max_retries - 1:
                        is_rl = _is_rate_limit_error(e)
                        wait_time = _retry_wait_time(attempt, is_rl)
                        print(f"[DashScope 图生视频] {'限流' if is_rl else '瞬态错误'}，{wait_time:.0f}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                        await asyncio.sleep(wait_time)
                        last_error = e
                        continue
                    return {
                        "success": False,
                        "error": str(e),
                    }

            return {
                "success": False,
                "error": f"重试 {max_retries} 次后仍失败: {last_error}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    async def get_video_task_result(self, task_id: str) -> Dict[str, Any]:
        """
        查询视频生成任务结果
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务结果
        """
        try:
            from dashscope import VideoSynthesis
        except ImportError:
            raise ImportError(
                "dashscope package is required. Install with: pip install dashscope"
            )
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: VideoSynthesis.fetch(api_key=self._api_key, task=task_id)
            )
            
            if response.status_code == 200:
                output = response.output
                status = output.get("task_status", "UNKNOWN")
                
                if status == "SUCCEEDED":
                    video_url = output.get("video_url")
                    return {
                        "success": True,
                        "status": "completed",
                        "video_url": video_url,
                    }
                elif status == "FAILED":
                    return {
                        "success": False,
                        "status": "failed",
                        "error": output.get("message", "任务失败"),
                    }
                else:
                    return {
                        "success": True,
                        "status": "processing",
                        "message": f"任务状态: {status}",
                    }
            else:
                return {
                    "success": False,
                    "error": f"{response.code}: {response.message}",
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    async def text_to_speech(
        self,
        text: str,
        model: str = "cosyvoice-v1",
        voice: str = "longxiaochun",
        format: str = "mp3",
    ) -> Dict[str, Any]:
        """
        文字转语音 - 使用 CosyVoice 模型合成语音
        
        Args:
            text: 要转换的文本
            model: 模型名称，默认 cosyvoice-v1
            voice: 音色，如 longxiaochun, longxiaoxia, longshuo, longyuan
            format: 输出格式，如 mp3, wav
            
        Returns:
            包含音频数据的结果字典
        """
        try:
            from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat
        except ImportError:
            raise ImportError(
                "dashscope package is required. Install with: pip install dashscope"
            )
        
        # 将字符串格式映射到 AudioFormat 枚举
        format_map = {
            "mp3": AudioFormat.MP3_22050HZ_MONO_256KBPS,
            "wav": AudioFormat.WAV_22050HZ_MONO_16BIT,
            "pcm": AudioFormat.PCM_22050HZ_MONO_16BIT,
        }
        audio_format = format_map.get(format.lower(), AudioFormat.MP3_22050HZ_MONO_256KBPS)
        
        try:
            loop = asyncio.get_event_loop()
            
            def synthesize():
                synthesizer = SpeechSynthesizer(
                    model=model,
                    voice=voice,
                    format=audio_format,
                )
                audio = synthesizer.call(text)
                return audio
            
            audio_data = await loop.run_in_executor(None, synthesize)
            
            if audio_data:
                return {
                    "success": True,
                    "audio_data": audio_data,
                    "format": format,
                }
            else:
                return {
                    "success": False,
                    "error": "语音合成失败",
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
