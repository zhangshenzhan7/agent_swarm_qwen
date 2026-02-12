"""主智能体子包（MainAgent）。

本子包包含 MainAgent 的拆分模块，负责任务的全生命周期管理与编排协调。
MainAgent 通过组合模式将职责委托给以下内部模块：

子模块：
    - agent: MainAgent 核心类，处理任务提交与状态管理
    - executor: TaskExecutor 任务执行协调逻辑
    - monitor: TaskMonitor 进度监控与超时管理
    - planner: TaskPlanner 计划管理（规划、确认执行、修订计划）
"""

from .agent import (
    MainAgent,
    MainAgentConfig,
    MainAgentError,
    TaskParsingError,
)
from .executor import (
    TaskExecutor,
    TaskExecutionError,
    DelegateModeForbiddenError,
)
from .monitor import (
    TaskMonitor,
    TaskNotFoundError,
)
from .planner import TaskPlanner

__all__ = [
    # 核心类
    "MainAgent",
    "MainAgentConfig",
    # 异常类
    "MainAgentError",
    "TaskParsingError",
    "TaskNotFoundError",
    "TaskExecutionError",
    "DelegateModeForbiddenError",
    # 内部模块类
    "TaskExecutor",
    "TaskMonitor",
    "TaskPlanner",
]
