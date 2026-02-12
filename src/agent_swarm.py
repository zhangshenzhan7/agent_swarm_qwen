"""向后兼容模块 - 请使用 src.core.agent_swarm 代替。

本模块保留用于向后兼容，所有类和函数已迁移到 src.core.agent_swarm。
建议直接从新位置导入：

    from src.core.agent_swarm import AgentSwarm, AgentSwarmConfig
"""

# 从新位置重导出所有公共 API
from .core.agent_swarm import (
    AgentSwarm,
    AgentSwarmConfig,
)

__all__ = [
    "AgentSwarm",
    "AgentSwarmConfig",
]
