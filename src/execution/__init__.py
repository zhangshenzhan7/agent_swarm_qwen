"""执行引擎层（execution）。

本子包包含 Qwen Agent Swarm 系统的执行引擎组件，负责子任务的
实际执行、调度和上下文管理。

子模块：
    - sub_agent: 子智能体执行引擎，负责与 Qwen 模型交互执行具体任务
    - scheduler: AgentScheduler 智能体调度器
    - wave_executor: 波次执行器，支持并行任务执行
    - context_manager: 执行上下文管理器
"""

from .scheduler import AgentScheduler
from .wave_executor import WaveExecutor
from .context_manager import ExecutionContextManager

__all__ = [
    "AgentScheduler",
    "WaveExecutor",
    "ExecutionContextManager",
]
