"""Qwen model client module."""

from .models import QwenModel, QwenConfig, Message, QwenResponse
from .interface import IQwenClient
from .dashscope_client import DashScopeClient, MODEL_CONTEXT_WINDOWS
from .local_client import LocalQwenClient
from .retry import (
    RetryConfig,
    MODEL_FALLBACK_CHAIN,
    RetryableError,
    NonRetryableError,
    is_retryable_error,
    execute_with_retry,
    execute_with_fallback,
    ResilientQwenClient,
)

__all__ = [
    # Models
    "QwenModel",
    "QwenConfig",
    "Message",
    "QwenResponse",
    # Interface
    "IQwenClient",
    # Clients
    "DashScopeClient",
    "LocalQwenClient",
    "ResilientQwenClient",
    # Retry
    "RetryConfig",
    "MODEL_FALLBACK_CHAIN",
    "MODEL_CONTEXT_WINDOWS",
    "RetryableError",
    "NonRetryableError",
    "is_retryable_error",
    "execute_with_retry",
    "execute_with_fallback",
]
