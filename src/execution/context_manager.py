"""向后兼容模块 - 请使用 src.context_manager 代替。

本模块保留用于向后兼容。
"""

from ..context_manager import (
    ExecutionContextManager,
    ContextNotFoundError,
)

__all__ = [
    "ExecutionContextManager",
    "ContextNotFoundError",
]
