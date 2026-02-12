"""Wave Executor interface for enhanced wave-based task execution.

Defines the abstract interface for the Wave Executor,
supporting event-driven dynamic wave formation, automatic
dependency unlocking on task completion, failure propagation,
and wave execution statistics recording.

The Wave Executor collaborates with the TaskBoard to manage
task lifecycle and dependency resolution.
"""

from abc import ABC, abstractmethod
from typing import Callable, List

from .task_board import ITaskBoard
from ..models.team import WaveExecutionResult, WaveStats


class IWaveExecutor(ABC):
    """波次执行器接口

    基于事件驱动的动态波次执行引擎，替代静态分层执行。
    不预先计算所有波次，而是事件驱动：任务完成 → 检查解锁 → 立即启动。

    与 TaskBoard 协作：
    - 通过 TaskBoard.get_available_tasks() 获取可执行任务
    - 通过 TaskBoard.on_task_completed() 获取新解锁的任务
    - 任务失败时通过 TaskBoard 标记依赖链为 blocked

    执行流程：
    1. 获取初始可用任务，形成第一波次
    2. 并行启动波次中的所有任务
    3. 任务完成时检查依赖解锁，立即启动新可用任务
    4. 任务失败时传播 blocked 状态到依赖链
    5. 所有非 blocked 任务完成后，汇总统计并报告
    """

    @abstractmethod
    async def execute(
        self, task_board: ITaskBoard, agent_factory: Callable
    ) -> WaveExecutionResult:
        """执行所有任务，动态形成波次

        从 TaskBoard 获取可用任务，动态形成执行波次并并行执行。
        任务完成时自动检查依赖解锁，将新可用任务加入执行。
        任务失败时传播 blocked 状态到所有直接或间接依赖的后续任务。

        Args:
            task_board: 共享任务板实例，用于获取任务和管理状态
            agent_factory: 智能体工厂函数，用于创建执行任务的智能体

        Returns:
            WaveExecutionResult: 波次执行结果，包含总波次数、任务统计和各波次详情
        """
        pass

    @abstractmethod
    async def get_wave_statistics(self) -> List[WaveStats]:
        """获取波次执行统计

        返回每个波次的执行统计信息，包括波次编号、包含的任务数量、
        并行度和执行时间。

        Returns:
            List[WaveStats]: 波次统计列表，每条记录包含波次编号、
                任务数量、并行度、开始/结束时间、完成/失败任务数
        """
        pass
