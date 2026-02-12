"""向后兼容模块 - 请使用 src.core.task_decomposer 代替。

本模块保留用于向后兼容，所有类和函数已迁移到 src.core.task_decomposer。
建议直接从新位置导入：

    from src.core.task_decomposer import TaskDecomposer
"""

# 从新位置重导出所有公共 API
from .core.task_decomposer import (
    TaskDecomposer,
    COMPLEXITY_KEYWORDS,
    ROLE_KEYWORDS,
)

__all__ = [
    "TaskDecomposer",
    "COMPLEXITY_KEYWORDS",
    "ROLE_KEYWORDS",
]
