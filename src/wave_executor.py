"""Enhanced Wave Executor implementation.

Provides the WaveExecutor class that implements event-driven dynamic wave
formation, automatic dependency unlocking on task completion, failure
propagation, and wave execution statistics recording.

The WaveExecutor collaborates with the TaskBoard to manage task lifecycle
and dependency resolution, using asyncio for concurrent task execution.
"""

import asyncio
import logging
import time
from collections import deque
from typing import Callable, Dict, List, Set

from .interfaces.task_board import ITaskBoard
from .interfaces.wave_executor import IWaveExecutor
from .models.team import TaskBoardStatus, WaveExecutionResult, WaveStats

logger = logging.getLogger(__name__)


class WaveExecutor(IWaveExecutor):
    """波次执行器实现

    基于事件驱动的动态波次执行引擎。不预先计算所有波次，
    而是事件驱动：任务完成 → 检查解锁 → 立即启动新任务。

    执行流程：
    1. 从 TaskBoard 获取初始可用任务
    2. 对每个可用任务：认领 → 更新为 IN_PROGRESS → 通过 agent_factory 执行
    3. 任务完成时：更新为 COMPLETED → 调用 on_task_completed 获取解锁任务 → 立即启动
    4. 任务失败时：更新为 FAILED → 传播 blocked 状态到依赖链
    5. 记录波次统计
    6. 所有非 blocked 任务完成后，返回 WaveExecutionResult

    Attributes:
        _wave_stats: 波次统计列表
        _current_wave_number: 当前波次编号
    """

    def __init__(self) -> None:
        """初始化波次执行器"""
        self._wave_stats: List[WaveStats] = []
        self._current_wave_number: int = 0

    async def execute(
        self, task_board: ITaskBoard, agent_factory: Callable
    ) -> WaveExecutionResult:
        """执行所有任务，动态形成波次

        从 TaskBoard 获取可用任务，动态形成执行波次并并行执行。
        任务完成时自动检查依赖解锁，将新可用任务加入执行。
        任务失败时传播 blocked 状态到所有直接或间接依赖的后续任务。

        Args:
            task_board: 共享任务板实例
            agent_factory: 智能体工厂函数，接受 SubTask 返回协程

        Returns:
            WaveExecutionResult: 波次执行结果
        """
        self._wave_stats = []
        self._current_wave_number = 0

        execution_start = time.time()

        total_completed = 0
        total_failed = 0
        total_blocked = 0
        total_tasks = len(task_board._entries) if hasattr(task_board, '_entries') else 0

        # Track active tasks (running concurrently)
        active_tasks: Dict[str, asyncio.Task] = {}
        # Event to signal when new tasks become available
        new_tasks_event = asyncio.Event()

        # Track wave membership for statistics
        # Each task is assigned to the wave in which it was started
        task_wave_map: Dict[str, int] = {}
        wave_start_times: Dict[int, float] = {}
        wave_task_counts: Dict[int, int] = {}
        wave_completed: Dict[int, int] = {}
        wave_failed: Dict[int, int] = {}
        wave_parallelism: Dict[int, int] = {}

        def _start_wave(task_ids: List[str]) -> int:
            """Register a new wave and return its number."""
            wave_num = self._current_wave_number
            self._current_wave_number += 1
            now = time.time()
            wave_start_times[wave_num] = now
            wave_task_counts[wave_num] = len(task_ids)
            wave_completed[wave_num] = 0
            wave_failed[wave_num] = 0
            wave_parallelism[wave_num] = len(task_ids)
            for tid in task_ids:
                task_wave_map[tid] = wave_num
            return wave_num

        async def _execute_single_task(task_id: str) -> None:
            """Execute a single task: claim → IN_PROGRESS → run → update status."""
            nonlocal total_completed, total_failed, total_blocked

            try:
                # Check if the task has been cancelled via CancelledError
                if asyncio.current_task().cancelled():
                    return

                # Claim the task
                claim_result = await task_board.claim_task("wave_executor", task_id)
                if not claim_result.success:
                    logger.warning(
                        "Failed to claim task %s: %s", task_id, claim_result.error
                    )
                    return

                # Update to IN_PROGRESS
                await task_board.update_task_status(task_id, TaskBoardStatus.IN_PROGRESS)

                # Get the subtask for the agent_factory
                entry = await task_board.get_task_status(task_id)
                subtask = entry.subtask

                # Execute via agent_factory
                result = await agent_factory(subtask)

                # Task completed successfully
                await task_board.update_task_status(
                    task_id, TaskBoardStatus.COMPLETED, result=result
                )
                total_completed += 1

                # Record wave stats
                wave_num = task_wave_map.get(task_id, 0)
                wave_completed[wave_num] = wave_completed.get(wave_num, 0) + 1

                # Check for newly unlocked tasks
                unlocked_ids = await task_board.on_task_completed(task_id)
                if unlocked_ids:
                    # Start newly unlocked tasks immediately in a new wave
                    _start_new_tasks(unlocked_ids)
                    new_tasks_event.set()

            except Exception as e:
                logger.error("Task %s failed: %s", task_id, str(e))

                # Update task to FAILED
                await task_board.update_task_status(
                    task_id, TaskBoardStatus.FAILED, result=str(e)
                )
                total_failed += 1

                # Record wave stats
                wave_num = task_wave_map.get(task_id, 0)
                wave_failed[wave_num] = wave_failed.get(wave_num, 0) + 1

                # Propagate failure: mark all direct and indirect dependents as BLOCKED
                blocked_count = await self._propagate_failure(task_board, task_id)
                total_blocked += blocked_count

            finally:
                # Remove from active tasks
                active_tasks.pop(task_id, None)
                # Signal that a task finished (might allow completion check)
                new_tasks_event.set()

        def _start_new_tasks(task_ids: List[str]) -> None:
            """Start execution of newly available tasks."""
            if not task_ids:
                return

            # Filter out tasks already active
            new_ids = [tid for tid in task_ids if tid not in active_tasks]
            if not new_ids:
                return

            # Register a new wave for these tasks
            _start_wave(new_ids)

            for tid in new_ids:
                task = asyncio.create_task(_execute_single_task(tid))
                active_tasks[tid] = task

        # Get initial available tasks
        initial_tasks = await task_board.get_available_tasks("wave_executor")
        initial_task_ids = [entry.task_id for entry in initial_tasks]

        if not initial_task_ids:
            # Count blocked tasks
            if hasattr(task_board, '_entries'):
                for entry in task_board._entries.values():
                    if entry.status == TaskBoardStatus.BLOCKED:
                        total_blocked += 1
                total_tasks = len(task_board._entries)

            execution_end = time.time()
            return WaveExecutionResult(
                total_waves=0,
                total_tasks=total_tasks,
                completed_tasks=total_completed,
                failed_tasks=total_failed,
                blocked_tasks=total_blocked,
                wave_stats=[],
                total_execution_time=execution_end - execution_start,
            )

        # Start the first wave
        _start_new_tasks(initial_task_ids)

        # Main loop: wait for all tasks to complete
        reclaim_interval = 10.0
        last_reclaim = time.time()

        while active_tasks:
            new_tasks_event.clear()
            # Wait for any task to complete or new tasks to become available
            # Use a short timeout to periodically check
            try:
                await asyncio.wait_for(new_tasks_event.wait(), timeout=0.1)
            except asyncio.TimeoutError:
                # 定期回收超时的已认领任务
                now = time.time()
                if now - last_reclaim > reclaim_interval:
                    try:
                        reclaimed = await task_board.reclaim_expired_tasks(
                            timeout_seconds=60.0
                        )
                        if reclaimed:
                            logger.info(
                                "Reclaimed %d expired tasks", len(reclaimed)
                            )
                            _start_new_tasks(reclaimed)
                            new_tasks_event.set()
                    except Exception as e:
                        logger.warning("Failed to reclaim tasks: %s", e)
                    last_reclaim = now

        # Count remaining blocked tasks
        if hasattr(task_board, '_entries'):
            total_tasks = len(task_board._entries)
            total_blocked = 0
            for entry in task_board._entries.values():
                if entry.status == TaskBoardStatus.BLOCKED:
                    total_blocked += 1

        execution_end = time.time()

        # Build wave statistics
        self._wave_stats = self._build_wave_stats(
            wave_start_times, wave_task_counts, wave_completed,
            wave_failed, wave_parallelism, execution_end
        )

        return WaveExecutionResult(
            total_waves=len(self._wave_stats),
            total_tasks=total_tasks,
            completed_tasks=total_completed,
            failed_tasks=total_failed,
            blocked_tasks=total_blocked,
            wave_stats=list(self._wave_stats),
            total_execution_time=execution_end - execution_start,
        )

    async def get_wave_statistics(self) -> List[WaveStats]:
        """获取波次执行统计

        Returns:
            List[WaveStats]: 波次统计列表
        """
        return list(self._wave_stats)

    async def _propagate_failure(
        self, task_board: ITaskBoard, failed_task_id: str
    ) -> int:
        """传播失败状态到所有直接或间接依赖的后续任务

        使用 BFS 遍历依赖图，将所有直接或间接依赖于失败任务的
        后续任务标记为 BLOCKED 状态。

        Args:
            task_board: 任务板实例
            failed_task_id: 失败的任务 ID

        Returns:
            int: 被标记为 blocked 的任务数量
        """
        blocked_count = 0

        # Use BFS to find all direct and indirect dependents
        # Access the _dependents mapping from TaskBoard
        if not hasattr(task_board, '_dependents'):
            return blocked_count

        visited: Set[str] = set()
        queue: deque = deque()

        # Start with direct dependents of the failed task
        direct_dependents = task_board._dependents.get(failed_task_id, set())
        for dep_id in direct_dependents:
            if dep_id not in visited:
                queue.append(dep_id)
                visited.add(dep_id)

        while queue:
            current_id = queue.popleft()

            # Get current task status
            try:
                entry = await task_board.get_task_status(current_id)
            except KeyError:
                continue

            # Only block tasks that are not already completed or failed
            if entry.status not in (
                TaskBoardStatus.COMPLETED,
                TaskBoardStatus.FAILED,
            ):
                await task_board.update_task_status(
                    current_id, TaskBoardStatus.BLOCKED
                )
                blocked_count += 1

            # Continue BFS to indirect dependents
            indirect_dependents = task_board._dependents.get(current_id, set())
            for dep_id in indirect_dependents:
                if dep_id not in visited:
                    queue.append(dep_id)
                    visited.add(dep_id)

        return blocked_count

    def _build_wave_stats(
        self,
        wave_start_times: Dict[int, float],
        wave_task_counts: Dict[int, int],
        wave_completed: Dict[int, int],
        wave_failed: Dict[int, int],
        wave_parallelism: Dict[int, int],
        execution_end: float,
    ) -> List[WaveStats]:
        """Build WaveStats list from collected wave data.

        Args:
            wave_start_times: wave_number → start time
            wave_task_counts: wave_number → task count
            wave_completed: wave_number → completed count
            wave_failed: wave_number → failed count
            wave_parallelism: wave_number → parallelism
            execution_end: overall execution end time

        Returns:
            List[WaveStats]: sorted list of wave statistics
        """
        stats: List[WaveStats] = []
        sorted_waves = sorted(wave_start_times.keys())

        for i, wave_num in enumerate(sorted_waves):
            # End time is the start of the next wave, or execution_end for the last
            if i + 1 < len(sorted_waves):
                end_time = wave_start_times[sorted_waves[i + 1]]
            else:
                end_time = execution_end

            stats.append(
                WaveStats(
                    wave_number=wave_num,
                    task_count=wave_task_counts.get(wave_num, 0),
                    parallelism=wave_parallelism.get(wave_num, 0),
                    start_time=wave_start_times[wave_num],
                    end_time=end_time,
                    completed_tasks=wave_completed.get(wave_num, 0),
                    failed_tasks=wave_failed.get(wave_num, 0),
                )
            )

        return stats
