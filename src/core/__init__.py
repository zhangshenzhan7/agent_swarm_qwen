"""核心编排层（core）。

本子包包含 Qwen Agent Swarm 系统的核心编排组件，负责任务的接收、
规划、分解、执行协调与质量保障。

子模块：
    - agent_swarm: 系统统一入口类 AgentSwarm 及其配置
    - main_agent: 主智能体 MainAgent，负责任务全生命周期管理与编排协调
    - supervisor: AI 主管 Supervisor，基于 ReAct 架构进行任务规划与执行流程管理
    - task_decomposer: 任务分解器，将复杂任务拆分为可执行的子任务
    - quality_assurance: 质量保障模块，确保任务执行结果的质量
"""

from .task_decomposer import TaskDecomposer
from .quality_assurance import (
    QualityLevel,
    ConflictType,
    QualityReport,
    ConflictReport,
    ReflectionResult,
    QualityAssurance,
)

# 延迟导入 AgentSwarm 以避免循环导入
def __getattr__(name):
    if name == "AgentSwarm":
        from .agent_swarm import AgentSwarm
        return AgentSwarm
    elif name == "AgentSwarmConfig":
        from .agent_swarm import AgentSwarmConfig
        return AgentSwarmConfig
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "AgentSwarm",
    "AgentSwarmConfig",
    "TaskDecomposer",
    "QualityLevel",
    "ConflictType",
    "QualityReport",
    "ConflictReport",
    "ReflectionResult",
    "QualityAssurance",
]
