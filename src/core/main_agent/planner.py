"""任务计划管理模块。

本模块包含 TaskPlanner 类，负责任务的规划、确认执行和计划修订。
支持两阶段执行模式：先生成执行计划，再确认后执行。

主要职责：
    - 生成执行计划（plan）
    - 确认并执行计划（confirm_and_execute）
    - 修订计划（revise_plan）
"""

import time
from typing import TYPE_CHECKING, Dict, Any, Optional, List

from ...models.task import Task, TaskDecomposition, SubTask
from ...models.result import TaskResult, SubTaskResult
from ...models.enums import TaskStatus
from ...models.team import ExecutionPlan, PlanStatus

if TYPE_CHECKING:
    from ...interfaces.task_decomposer import ITaskDecomposer
    from ...interfaces.agent_scheduler import IAgentScheduler
    from ...interfaces.result_aggregator import IResultAggregator
    from ...interfaces.context_manager import IExecutionContextManager
    from .agent import MainAgentConfig


class TaskPlanner:
    """任务计划管理器。
    
    负责任务的规划和两阶段执行流程管理。
    
    Attributes:
        _task_decomposer: 任务分解器
        _agent_scheduler: 智能体调度器
        _result_aggregator: 结果聚合器
        _context_manager: 执行上下文管理器
        _config: 主智能体配置
        _tasks: 任务存储引用
        _task_decompositions: 任务分解存储引用
        _task_results: 任务结果存储引用
    """
    
    def __init__(
        self,
        task_decomposer: "ITaskDecomposer",
        agent_scheduler: "IAgentScheduler",
        result_aggregator: "IResultAggregator",
        context_manager: "IExecutionContextManager",
        config: "MainAgentConfig",
        # 共享状态引用
        tasks: Optional[Dict[str, Task]] = None,
        task_decompositions: Optional[Dict[str, TaskDecomposition]] = None,
        task_results: Optional[Dict[str, TaskResult]] = None,
    ):
        """
        初始化任务计划管理器。
        
        Args:
            task_decomposer: 任务分解器
            agent_scheduler: 智能体调度器
            result_aggregator: 结果聚合器
            context_manager: 执行上下文管理器
            config: 主智能体配置
            tasks: 共享的任务存储
            task_decompositions: 共享的任务分解存储
            task_results: 共享的任务结果存储
        """
        self._task_decomposer = task_decomposer
        self._agent_scheduler = agent_scheduler
        self._result_aggregator = result_aggregator
        self._context_manager = context_manager
        self._config = config
        self._tasks = tasks if tasks is not None else {}
        self._task_decompositions = task_decompositions if task_decompositions is not None else {}
        self._task_results = task_results if task_results is not None else {}
    
    async def plan(self, task: Task) -> ExecutionPlan:
        """
        阶段一：生成执行计划（只读，不执行）。
        
        使用任务分解器分析任务并生成包含子任务列表、依赖关系、
        角色分配和资源估算的执行计划。此方法不执行任何子任务。
        
        Args:
            task: 要规划的任务
            
        Returns:
            执行计划
        """
        # 存储任务（如果尚未存储）
        if task.id not in self._tasks:
            self._tasks[task.id] = task
        
        # 分析复杂度（如果尚未分析）
        if task.complexity_score == 0.0:
            task.complexity_score = await self._task_decomposer.analyze_complexity(task)
        
        # 分解任务
        decomposition = await self._task_decomposer.decompose(task)
        self._task_decompositions[task.id] = decomposition
        
        # 构建依赖图
        dependency_graph: Dict[str, set] = {}
        for subtask in decomposition.subtasks:
            dependency_graph[subtask.id] = set(subtask.dependencies)
        
        # 构建角色分配
        agent_assignments: Dict[str, str] = {}
        for subtask in decomposition.subtasks:
            agent_assignments[subtask.id] = subtask.role_hint or "general"
        
        # 估算资源消耗
        estimated_token_usage = self._estimate_token_usage(decomposition)
        estimated_execution_time = decomposition.total_estimated_time
        
        # 构建波次预览（基于 execution_order）
        wave_preview = decomposition.execution_order
        
        # 创建执行计划
        plan = ExecutionPlan(
            task_id=task.id,
            subtasks=decomposition.subtasks,
            dependency_graph=dependency_graph,
            agent_assignments=agent_assignments,
            estimated_token_usage=estimated_token_usage,
            estimated_execution_time=estimated_execution_time,
            wave_preview=wave_preview,
            created_at=time.time(),
            status=PlanStatus.DRAFT,
        )
        
        return plan
    
    async def confirm_and_execute(self, task: Task, plan: ExecutionPlan) -> TaskResult:
        """
        阶段二：确认计划后执行。
        
        将计划状态设置为 CONFIRMED，然后通过调度器执行所有子任务。
        执行完成后生成包含实际资源消耗与预估对比的执行报告。
        
        Args:
            task: 要执行的任务
            plan: 已确认的执行计划
            
        Returns:
            任务执行结果
        """
        from ...interfaces.result_aggregator import ConflictResolution
        
        start_time = time.time()
        
        # 确认计划
        plan.status = PlanStatus.CONFIRMED
        
        # 存储任务（如果尚未存储）
        if task.id not in self._tasks:
            self._tasks[task.id] = task
        
        try:
            # 更新任务状态为执行中
            task.status = TaskStatus.EXECUTING
            await self._context_manager.update_status(task.id, TaskStatus.EXECUTING)
            
            # 获取或重建分解结果
            decomposition = self._task_decompositions.get(task.id)
            if decomposition is None:
                decomposition = TaskDecomposition(
                    original_task_id=task.id,
                    subtasks=plan.subtasks,
                    execution_order=plan.wave_preview,
                    total_estimated_time=plan.estimated_execution_time,
                )
                self._task_decompositions[task.id] = decomposition
            
            # 调度执行
            sub_results = await self._agent_scheduler.schedule_execution(decomposition)
            
            # 聚合结果
            task.status = TaskStatus.AGGREGATING
            await self._context_manager.update_status(task.id, TaskStatus.AGGREGATING)
            
            aggregation_result = await self._result_aggregator.aggregate(
                sub_results,
                decomposition,
                ConflictResolution.MAJORITY_VOTE,
            )
            
            execution_time = time.time() - start_time
            
            # 构建执行报告（包含实际 vs 预估资源对比）
            actual_token_usage = sum(
                sum(sr.token_usage.values()) for sr in sub_results if sr.token_usage
            )
            
            report = {
                "estimated_token_usage": plan.estimated_token_usage,
                "actual_token_usage": actual_token_usage,
                "estimated_execution_time": plan.estimated_execution_time,
                "actual_execution_time": execution_time,
            }
            
            result = TaskResult(
                task_id=task.id,
                success=aggregation_result.success,
                output=aggregation_result.final_output,
                error=None if aggregation_result.success else self._extract_error(sub_results),
                execution_time=execution_time,
                sub_results=sub_results,
            )
            
            # 将报告附加到结果的元数据中（通过 task metadata）
            task.metadata["execution_report"] = report
            
            # 更新任务状态
            task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
            await self._context_manager.update_status(task.id, task.status)
            
            self._task_results[task.id] = result
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            task.status = TaskStatus.FAILED
            await self._context_manager.update_status(task.id, TaskStatus.FAILED)
            
            result = TaskResult(
                task_id=task.id,
                success=False,
                output=None,
                error=str(e),
                execution_time=execution_time,
                sub_results=[],
            )
            
            self._task_results[task.id] = result
            return result
    
    async def revise_plan(self, task: Task, plan: ExecutionPlan, feedback: str) -> ExecutionPlan:
        """
        修改计划：根据反馈重新生成执行计划。
        
        将当前计划状态设置为 REJECTED，然后将反馈注入任务元数据，
        重新进入 Plan_Phase 生成新的执行计划。
        
        Args:
            task: 要重新规划的任务
            plan: 被拒绝的执行计划
            feedback: 调用方的修改意见
            
        Returns:
            修改后的新执行计划
        """
        # 标记旧计划为已拒绝
        plan.status = PlanStatus.REJECTED
        
        # 将反馈注入任务元数据，以便分解器可以参考
        task.metadata["plan_feedback"] = feedback
        task.metadata["revision_count"] = task.metadata.get("revision_count", 0) + 1
        
        # 重新生成计划
        new_plan = await self.plan(task)
        
        # 标记新计划为修订版
        new_plan.status = PlanStatus.REVISED
        
        return new_plan
    
    def _estimate_token_usage(self, decomposition: TaskDecomposition) -> int:
        """
        估算任务的 token 用量。
        
        基于子任务数量和复杂度进行粗略估算。
        
        Args:
            decomposition: 任务分解结果
            
        Returns:
            预估 token 用量
        """
        base_tokens_per_subtask = 500  # 每个子任务的基础 token 消耗
        total = 0
        for subtask in decomposition.subtasks:
            # 根据复杂度调整估算
            complexity_multiplier = max(1.0, subtask.estimated_complexity)
            total += int(base_tokens_per_subtask * complexity_multiplier)
        return total
    
    def _extract_error(self, sub_results: List[SubTaskResult]) -> Optional[str]:
        """
        从子结果中提取错误信息。
        
        Args:
            sub_results: 子任务结果列表
            
        Returns:
            错误信息字符串，如果没有错误则返回 None
        """
        errors = []
        for result in sub_results:
            if not result.success and result.error:
                errors.append(f"[{result.subtask_id}] {result.error}")
        
        if errors:
            return "; ".join(errors[:5])  # 最多返回5个错误
        return None
