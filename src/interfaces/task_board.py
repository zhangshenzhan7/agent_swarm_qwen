"""Task Board interface for shared task management.

Defines the abstract interface for the shared Task Board,
supporting task publishing, claiming with mutual exclusion,
status management, dependency-based auto-unlocking,
timeout reclamation, and priority/role-based querying.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set

from ..models.task import SubTask
from ..models.team import ClaimResult, TaskBoardEntry, TaskBoardStatus


class ITaskBoard(ABC):
    """共享任务板接口

    维护所有子任务的共享状态，支持自认领和依赖自动解锁。
    使用互斥锁确保同一时刻只有一个智能体能成功认领同一任务。

    任务状态机：blocked → pending → claimed → in_progress → completed/failed
    """

    @abstractmethod
    async def publish_tasks(
        self, tasks: List[SubTask], dependencies: Dict[str, Set[str]]
    ) -> None:
        """发布任务到任务板

        将子任务列表及其依赖关系发布到共享任务板。
        无依赖的任务初始状态为 pending，有未完成依赖的任务初始状态为 blocked。

        Args:
            tasks: 要发布的子任务列表
            dependencies: 依赖关系图 (task_id -> 该任务依赖的 task_id 集合)

        Raises:
            DependencyCycleError: 如果检测到循环依赖
        """
        pass

    @abstractmethod
    async def claim_task(self, agent_id: str, task_id: str) -> ClaimResult:
        """认领任务（带锁）

        使用互斥锁确保同一时刻只有一个智能体能成功认领同一任务。
        仅 pending 状态的任务可被认领。认领成功后任务状态变为 claimed。

        Args:
            agent_id: 认领者智能体 ID
            task_id: 要认领的任务 ID

        Returns:
            ClaimResult: 认领结果，包含是否成功及可能的错误信息
        """
        pass

    @abstractmethod
    async def get_available_tasks(
        self, agent_id: str, role_filter: Optional[str] = None
    ) -> List[TaskBoardEntry]:
        """查询可认领的任务列表

        返回当前处于 pending 状态的任务，支持按角色过滤，
        结果按优先级降序排列。

        Args:
            agent_id: 查询者智能体 ID
            role_filter: 可选的角色过滤条件，仅返回匹配角色的任务

        Returns:
            List[TaskBoardEntry]: 可认领的任务列表，按优先级降序排列
        """
        pass

    @abstractmethod
    async def update_task_status(
        self, task_id: str, status: TaskBoardStatus, result: Optional[Any] = None
    ) -> None:
        """更新任务状态

        更新指定任务的状态，可选地附带执行结果。

        Args:
            task_id: 任务 ID
            status: 新的任务状态
            result: 可选的执行结果（通常在 completed 或 failed 时提供）
        """
        pass

    @abstractmethod
    async def get_task_status(self, task_id: str) -> TaskBoardEntry:
        """查询任务状态

        获取指定任务的完整任务板条目信息。

        Args:
            task_id: 任务 ID

        Returns:
            TaskBoardEntry: 任务板条目，包含任务的完整状态信息
        """
        pass

    @abstractmethod
    async def on_task_completed(self, task_id: str) -> List[str]:
        """任务完成时触发依赖检查，返回新解锁的任务 ID 列表

        当一个任务完成时，检查所有依赖于该任务的后续任务。
        如果某个后续任务的所有前置依赖均已完成，则将其状态
        从 blocked 自动转换为 pending。

        Args:
            task_id: 已完成的任务 ID

        Returns:
            List[str]: 新解锁（从 blocked 变为 pending）的任务 ID 列表
        """
        pass

    @abstractmethod
    async def reclaim_expired_tasks(self, timeout_seconds: float) -> List[str]:
        """回收超时未执行的已认领任务

        检查所有处于 claimed 状态的任务，如果认领时间超过指定超时时间
        且未开始执行，则将任务状态回退为 pending 以供其他智能体认领。

        Args:
            timeout_seconds: 超时时间（秒），超过此时间未执行的已认领任务将被回收

        Returns:
            List[str]: 被回收（从 claimed 回退为 pending）的任务 ID 列表
        """
        pass
