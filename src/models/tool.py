"""Tool-related data models."""

from dataclasses import dataclass, field
from typing import Callable, Awaitable, Any, Dict, Optional


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    parameters_schema: Dict[str, Any]
    handler: Callable[..., Awaitable[Any]]
    timeout: float = 30.0
    retry_on_failure: bool = True


@dataclass
class ToolCallRecord:
    """工具调用记录"""
    id: str
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    success: bool
    error: Optional[str]
    start_time: float
    end_time: float
    agent_id: str
