"""Shared Task Board implementation.

Provides the TaskBoard class that manages shared task state,
supporting task publishing, mutual-exclusion claiming via asyncio.Lock,
status management, dependency-based auto-unlocking, timeout reclamation,
and priority/role-based querying.
"""

import asyncio
import time
from collections import deque
from typing import Any, Dict, List, Optional, Set

from .interfaces.task_board import ITaskBoard
from .models.task import SubTask
from .models.team import ClaimResult, TaskBoardEntry, TaskBoardStatus


class DependencyCycleError(Exception):
    """Raised when a circular dependency is detected in the task graph."""

    pass


class TaskBoard(ITaskBoard):
    """共享任务板实现

    维护所有子任务的共享状态，支持自认领和依赖自动解锁。
    使用 asyncio.Lock 确保同一时刻只有一个智能体能成功认领同一任务。

    任务状态机：blocked → pending → claimed → in_progress → completed/failed

    Attributes:
        _entries: task_id → TaskBoardEntry 的映射
        _dependencies: task_id → 该任务依赖的 task_id 集合
        _dependents: task_id → 依赖该任务的 task_id 集合（反向映射）
        _lock: asyncio.Lock，用于认领操作的互斥控制
    """

    def __init__(self) -> None:
        """初始化任务板"""
        self._entries: Dict[str, TaskBoardEntry] = {}
        self._dependencies: Dict[str, Set[str]] = {}
        self._dependents: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()

    def _detect_cycle(self, dependencies: Dict[str, Set[str]]) -> bool:
        """检测依赖图中是否存在循环依赖

        使用 Kahn 算法（拓扑排序）检测循环。
        如果无法完成拓扑排序（即存在剩余节点），则存在循环。

        Args:
            dependencies: 依赖关系图 (task_id → 该任务依赖的 task_id 集合)

        Returns:
            bool: 如果存在循环依赖返回 True，否则返回 False
        """
        # Collect all nodes referenced in the dependency graph
        all_nodes: Set[str] = set()
        for node, deps in dependencies.items():
            all_nodes.add(node)
            all_nodes.update(deps)

        # Build in-degree map
        in_degree: Dict[str, int] = {node: 0 for node in all_nodes}
        # Build adjacency list (from dependency to dependent)
        adj: Dict[str, Set[str]] = {node: set() for node in all_nodes}

        for node, deps in dependencies.items():
            for dep in deps:
                adj[dep].add(node)
                in_degree[node] = in_degree.get(node, 0) + 1

        # Start with nodes that have no dependencies
        queue = deque(node for node, deg in in_degree.items() if deg == 0)
        visited_count = 0

        while queue:
            current = queue.popleft()
            visited_count += 1
            for neighbor in adj.get(current, set()):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return visited_count < len(all_nodes)

    async def publish_tasks(
        self, tasks: List[SubTask], dependencies: Dict[str, Set[str]]
    ) -> None:
        """发布任务到任务板

        将子任务列表及其依赖关系发布到共享任务板。
        无依赖的任务初始状态为 pending，有未完成依赖的任务初始状态为 blocked。

        Args:
            tasks: 要发布的子任务列表
            dependencies: 依赖关系图 (task_id → 该任务依赖的 task_id 集合)

        Raises:
            DependencyCycleError: 如果检测到循环依赖
        """
        # Check for cycles in the dependency graph
        if self._detect_cycle(dependencies):
            raise DependencyCycleError(
                "Circular dependency detected in task graph"
            )

        # Build the reverse dependency mapping (dependents)
        for task in tasks:
            task_id = task.id
            deps = dependencies.get(task_id, set())
            self._dependencies[task_id] = set(deps)

            # Build reverse mapping
            for dep_id in deps:
                if dep_id not in self._dependents:
                    self._dependents[dep_id] = set()
                self._dependents[dep_id].add(task_id)

        # Create TaskBoardEntry for each task
        for task in tasks:
            task_id = task.id
            deps = self._dependencies.get(task_id, set())

            # Determine initial status based on dependencies
            # A task is pending if it has no dependencies or all dependencies
            # are already completed
            has_unmet_deps = False
            for dep_id in deps:
                if dep_id in self._entries:
                    if self._entries[dep_id].status != TaskBoardStatus.COMPLETED:
                        has_unmet_deps = True
                        break
                else:
                    # Dependency not yet on the board — treat as unmet
                    has_unmet_deps = True
                    break

            if deps and has_unmet_deps:
                status = TaskBoardStatus.BLOCKED
            else:
                status = TaskBoardStatus.PENDING

            entry = TaskBoardEntry(
                task_id=task_id,
                subtask=task,
                status=status,
                dependencies=set(deps),
                priority=task.priority,
                role_hint=task.role_hint,
            )
            self._entries[task_id] = entry

    async def claim_task(self, agent_id: str, task_id: str) -> ClaimResult:
        """认领任务（带锁）

        使用 asyncio.Lock 确保同一时刻只有一个智能体能成功认领同一任务。
        仅 pending 状态的任务可被认领。认领成功后任务状态变为 claimed。

        Args:
            agent_id: 认领者智能体 ID
            task_id: 要认领的任务 ID

        Returns:
            ClaimResult: 认领结果，包含是否成功及可能的错误信息
        """
        async with self._lock:
            # Check if task exists
            if task_id not in self._entries:
                return ClaimResult(
                    success=False,
                    task_id=task_id,
                    error="Task not found",
                )

            entry = self._entries[task_id]

            # Check if task is already claimed
            if entry.status == TaskBoardStatus.CLAIMED:
                return ClaimResult(
                    success=False,
                    task_id=task_id,
                    error="Task already claimed",
                )

            # Check if task is in pending state
            if entry.status != TaskBoardStatus.PENDING:
                return ClaimResult(
                    success=False,
                    task_id=task_id,
                    error="Task not in pending state",
                )

            # Claim the task
            entry.status = TaskBoardStatus.CLAIMED
            entry.claimed_by = agent_id
            entry.claimed_at = time.time()

            return ClaimResult(
                success=True,
                task_id=task_id,
            )

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
        available: List[TaskBoardEntry] = []

        for entry in self._entries.values():
            # Only pending tasks are available
            if entry.status != TaskBoardStatus.PENDING:
                continue

            # Apply role filter if specified
            if role_filter is not None and entry.role_hint != role_filter:
                continue

            available.append(entry)

        # Sort by priority descending (higher priority first)
        available.sort(key=lambda e: e.priority, reverse=True)

        return available

    async def update_task_status(
        self, task_id: str, status: TaskBoardStatus, result: Optional[Any] = None
    ) -> None:
        """更新任务状态

        更新指定任务的状态，可选地附带执行结果。
        当状态变为 in_progress 时记录开始时间，
        当状态变为 completed 或 failed 时记录完成时间。

        Args:
            task_id: 任务 ID
            status: 新的任务状态
            result: 可选的执行结果（通常在 completed 或 failed 时提供）
        """
        if task_id not in self._entries:
            return

        entry = self._entries[task_id]
        entry.status = status

        if result is not None:
            entry.result = result

        now = time.time()

        if status == TaskBoardStatus.IN_PROGRESS:
            entry.started_at = now
        elif status in (TaskBoardStatus.COMPLETED, TaskBoardStatus.FAILED):
            entry.completed_at = now

    async def get_task_status(self, task_id: str) -> TaskBoardEntry:
        """查询任务状态

        获取指定任务的完整任务板条目信息。

        Args:
            task_id: 任务 ID

        Returns:
            TaskBoardEntry: 任务板条目，包含任务的完整状态信息

        Raises:
            KeyError: 如果任务不存在
        """
        if task_id not in self._entries:
            raise KeyError(f"Task not found: {task_id}")
        return self._entries[task_id]

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
        unlocked: List[str] = []

        # Get all tasks that depend on the completed task
        dependent_ids = self._dependents.get(task_id, set())

        for dep_id in dependent_ids:
            if dep_id not in self._entries:
                continue

            entry = self._entries[dep_id]

            # Only unlock blocked tasks
            if entry.status != TaskBoardStatus.BLOCKED:
                continue

            # Check if ALL dependencies of this task are now completed
            all_deps_completed = True
            task_deps = self._dependencies.get(dep_id, set())
            for required_dep_id in task_deps:
                if required_dep_id not in self._entries:
                    all_deps_completed = False
                    break
                if self._entries[required_dep_id].status != TaskBoardStatus.COMPLETED:
                    all_deps_completed = False
                    break

            if all_deps_completed:
                entry.status = TaskBoardStatus.PENDING
                unlocked.append(dep_id)

        return unlocked

    async def reclaim_expired_tasks(self, timeout_seconds: float) -> List[str]:
        """回收超时未执行的已认领任务

        检查所有处于 claimed 状态的任务，如果认领时间超过指定超时时间
        且未开始执行（started_at 为 None），则将任务状态回退为 pending
        以供其他智能体认领。

        Args:
            timeout_seconds: 超时时间（秒），超过此时间未执行的已认领任务将被回收

        Returns:
            List[str]: 被回收（从 claimed 回退为 pending）的任务 ID 列表
        """
        reclaimed: List[str] = []
        now = time.time()

        for task_id, entry in self._entries.items():
            if entry.status != TaskBoardStatus.CLAIMED:
                continue

            # Only reclaim if not yet started
            if entry.started_at is not None:
                continue

            # Check if claimed_at is set and has exceeded timeout
            if entry.claimed_at is not None:
                elapsed = now - entry.claimed_at
                if elapsed > timeout_seconds:
                    entry.status = TaskBoardStatus.PENDING
                    entry.claimed_by = None
                    entry.claimed_at = None
                    reclaimed.append(task_id)

        return reclaimed
