"""向后兼容模块 - 请使用 src.core.quality_assurance 代替。

本模块保留用于向后兼容，所有类和函数已迁移到 src.core.quality_assurance。
建议直接从新位置导入：

    from src.core.quality_assurance import QualityAssurance
"""

# 从新位置重导出所有公共 API
from .core.quality_assurance import (
    QualityLevel,
    ConflictType,
    QualityReport,
    ConflictReport,
    ReflectionResult,
    QualityAssurance,
)

__all__ = [
    "QualityLevel",
    "ConflictType",
    "QualityReport",
    "ConflictReport",
    "ReflectionResult",
    "QualityAssurance",
]
