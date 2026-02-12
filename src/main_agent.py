"""向后兼容模块 - 请使用 src.core.main_agent 代替。

本模块保留用于向后兼容，所有类和函数已迁移到 src.core.main_agent 子包。
建议直接从新位置导入：

    from src.core.main_agent import MainAgent, MainAgentConfig
"""

# 从新位置重导出所有公共 API
from .core.main_agent import (
    MainAgent,
    MainAgentConfig,
    MainAgentError,
    TaskParsingError,
    TaskNotFoundError,
    TaskExecutionError,
    DelegateModeForbiddenError,
    TaskExecutor,
    TaskMonitor,
    TaskPlanner,
)

__all__ = [
    "MainAgent",
    "MainAgentConfig",
    "MainAgentError",
    "TaskParsingError",
    "TaskNotFoundError",
    "TaskExecutionError",
    "DelegateModeForbiddenError",
    "TaskExecutor",
    "TaskMonitor",
    "TaskPlanner",
]
