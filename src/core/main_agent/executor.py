"""任务执行协调模块。

本模块包含 TaskExecutor 类，负责任务执行的协调逻辑，
包括团队模式执行和调度器模式执行两种执行策略。
"""

import asyncio
import logging
import time
import uuid
from typing import TYPE_CHECKING, Callable, Awaitable, Dict, Any, Optional, List, Set, Tuple

from ...models.agent import AgentRole, get_role_by_hint
from ...models.task import Task, TaskDecomposition, SubTask
from ...models.result import TaskResult, SubTaskResult
from ...models.enums import TaskStatus
from ...models.team import TeamState
from ...qwen.models import QwenConfig, QwenModel
from ...sub_agent import SubAgentImpl
from ...core.supervisor.flow import ExecutionFlow, ExecutionStep, TaskPlan

if TYPE_CHECKING:
    from ...interfaces.task_decomposer import ITaskDecomposer
    from ...interfaces.agent_scheduler import IAgentScheduler
    from ...interfaces.result_aggregator import IResultAggregator
    from ...interfaces.context_manager import IExecutionContextManager
    from ...interfaces.team_lifecycle import ITeamLifecycleManager
    from ...interfaces.wave_executor import IWaveExecutor
    from .agent import MainAgentConfig
    from ...supervisor import Supervisor

# 流式回调类型
StreamCallback = Callable[[str], Awaitable[None]]

logger = logging.getLogger(__name__)


class TaskExecutionError(Exception):
    """任务执行错误"""
    pass


class DelegateModeForbiddenError(Exception):
    """委派模式下禁止直接执行子任务"""
    pass


class TaskExecutor:
    """任务执行协调器，支持团队模式和调度器模式两种执行策略。"""
    
    def __init__(
        self,
        task_decomposer: "ITaskDecomposer",
        agent_scheduler: "IAgentScheduler",
        result_aggregator: "IResultAggregator",
        context_manager: "IExecutionContextManager",
        config: "MainAgentConfig",
        team_lifecycle_manager: Optional["ITeamLifecycleManager"] = None,
        wave_executor: Optional["IWaveExecutor"] = None,
        tasks: Optional[Dict[str, Task]] = None,
        task_decompositions: Optional[Dict[str, TaskDecomposition]] = None,
        task_results: Optional[Dict[str, TaskResult]] = None,
        cancelled_tasks: Optional[set] = None,
        timeout_warning_callbacks: Optional[List[callable]] = None,
    ):
        """初始化任务执行器。"""
        self._task_decomposer = task_decomposer
        self._agent_scheduler = agent_scheduler
        self._result_aggregator = result_aggregator
        self._context_manager = context_manager
        self._config = config
        self._team_lifecycle_manager = team_lifecycle_manager
        self._wave_executor = wave_executor
        self._tasks = tasks or {}
        self._task_decompositions = task_decompositions or {}
        self._task_results = task_results or {}
        self._cancelled_tasks = cancelled_tasks if cancelled_tasks is not None else set()
        self._timeout_warning_callbacks = timeout_warning_callbacks or []
    
    async def execute(self, task: Task) -> TaskResult:
        """执行任务（包含分解、调度、聚合全流程）。"""
        if self._config.delegate_mode:
            raise DelegateModeForbiddenError(
                "In delegate mode, MainAgent cannot directly execute tasks. "
                "Use plan_task() to generate an execution plan, then "
                "confirm_and_execute() to execute via SubAgents."
            )
        if (self._config.use_team_mode and self._team_lifecycle_manager 
                and self._wave_executor):
            return await self._execute_with_team(task)
        return await self._execute_with_scheduler(task)
    def _convert_steps_to_subtasks(
        self,
        execution_flow: ExecutionFlow,
        parent_task_id: str,
    ) -> Tuple[List[SubTask], Dict[str, Set[str]]]:
        """将 ExecutionFlow 中的 ExecutionStep 转换为 SubTask 对象。

        Args:
            execution_flow: 执行流程对象，包含步骤和依赖关系
            parent_task_id: 父任务 ID

        Returns:
            (subtasks, dependency_map) 元组
        """
        subtasks = []
        dependency_map = {}
        for step in execution_flow.steps.values():
            subtask = SubTask(
                id=step.step_id,
                parent_task_id=parent_task_id,
                content=step.description,
                role_hint=step.agent_type,
                dependencies=set(step.dependencies),
                priority=step.step_number,
                estimated_complexity=1.0,
            )
            subtasks.append(subtask)
            dependency_map[step.step_id] = set(step.dependencies)
        return subtasks, dependency_map

    async def execute_with_plan(
        self,
        task: Task,
        plan: TaskPlan,
        supervisor: Optional["Supervisor"] = None,
        stream_callback: Optional[StreamCallback] = None,
    ) -> TaskResult:
        """使用 Supervisor 规划数据执行任务，跳过 TaskDecomposer 分解阶段。

        将 TaskPlan 中的 ExecutionFlow 步骤转换为 SubTask，通过 TaskBoard
        发布并使用 WaveExecutor 执行，同时支持可选的质量门控。

        Args:
            task: 任务对象（content 应已设为 refined_task）
            plan: Supervisor 生成的 TaskPlan
            supervisor: 可选的 Supervisor 实例，用于质量门控
            stream_callback: 可选的流式回调

        Returns:
            TaskResult: 执行结果
        """
        from ...models.team import TeamConfig

        start_time = time.time()
        team = None
        subtask_outputs: Dict[str, SubTaskResult] = {}

        try:
            # 获取 execution_flow，如果不存在则回退到原有流程
            execution_flow = plan.execution_flow
            if not execution_flow or not execution_flow.steps:
                logger.warning("TaskPlan 中无有效 execution_flow，回退到 TaskDecomposer")
                return await self.execute(task)

            # 确保 team 模式可用
            if not self._team_lifecycle_manager or not self._wave_executor:
                logger.warning("团队模式不可用，回退到调度器模式")
                return await self._execute_with_scheduler(task)

            # 转换 ExecutionStep 为 SubTask
            subtasks, dependency_map = self._convert_steps_to_subtasks(
                execution_flow, task.id
            )

            if not subtasks:
                logger.warning("转换后无有效子任务，回退到 TaskDecomposer")
                return await self.execute(task)

            # 应用 suggested_agents 到 role_hint
            if plan.suggested_agents:
                subtask_list = list(subtasks)
                for i, subtask in enumerate(subtask_list):
                    if i < len(plan.suggested_agents):
                        subtask.role_hint = plan.suggested_agents[i]

            # 创建团队
            task.status = TaskStatus.EXECUTING
            await self._context_manager.update_status(task.id, TaskStatus.EXECUTING)

            if task.id in self._cancelled_tasks:
                return self._create_cancelled_result(task, start_time)

            team = await self._team_lifecycle_manager.create_team(task, TeamConfig())
            agent_roles, seen_roles = [], set()
            for st in subtasks:
                hint = st.role_hint or "researcher"
                if hint not in seen_roles:
                    seen_roles.add(hint)
                    agent_roles.append(get_role_by_hint(hint))
            await self._team_lifecycle_manager.setup_team(team.id, agent_roles)
            self._team_lifecycle_manager.set_team_state(team.id, TeamState.EXECUTING)

            # 发布任务到 TaskBoard
            task_board = self._team_lifecycle_manager.get_task_board(team.id)
            if task_board is None:
                raise TaskExecutionError(f"TaskBoard not found for team {team.id}")
            await task_board.publish_tasks(subtasks, dependency_map)

            # 准备执行
            message_bus = self._team_lifecycle_manager.get_message_bus(team.id)
            subtask_map = {st.id: st for st in subtasks}

            # 质量门控：跟踪每个子任务的重试次数
            retry_counts: Dict[str, int] = {}

            async def agent_factory(subtask: SubTask):
                return await self._run_subtask_with_quality_gate(
                    task=task,
                    subtask=subtask,
                    subtask_map=subtask_map,
                    subtask_outputs=subtask_outputs,
                    message_bus=message_bus,
                    execution_flow=execution_flow,
                    supervisor=supervisor,
                    stream_callback=stream_callback,
                    retry_counts=retry_counts,
                    task_board=task_board,
                    dependency_map=dependency_map,
                )

            timeout_task = asyncio.create_task(
                self._monitor_timeout(task.id, start_time)
            )
            try:
                wave_result = await self._wave_executor.execute(
                    task_board, agent_factory
                )
            finally:
                timeout_task.cancel()
                try:
                    await timeout_task
                except asyncio.CancelledError:
                    pass

            # 完成和清理
            self._team_lifecycle_manager.set_team_state(
                team.id, TeamState.COMPLETED
            )
            await self._team_lifecycle_manager.disband_team(team.id)

            # 构建结果
            execution_time = time.time() - start_time
            success = (
                wave_result.failed_tasks == 0 and wave_result.completed_tasks > 0
            )
            task.metadata["wave_execution_result"] = wave_result.to_dict()

            sub_results = list(subtask_outputs.values())
            output_parts = [
                sr.output
                for st in subtasks
                if (sr := subtask_outputs.get(st.id)) and sr.success and sr.output
            ]

            if output_parts:
                aggregated_output = (
                    output_parts[0]
                    if len(output_parts) == 1
                    else "\n\n---\n\n".join(output_parts)
                )
            else:
                aggregated_output = (
                    f"Completed {wave_result.completed_tasks}/"
                    f"{wave_result.total_tasks} tasks in "
                    f"{wave_result.total_waves} waves"
                )

            result = TaskResult(
                task_id=task.id,
                success=success,
                output=aggregated_output,
                error=None if success else f"{wave_result.failed_tasks} tasks failed",
                execution_time=execution_time,
                sub_results=sub_results,
                metadata={"task_plan": plan.to_dict()},
            )
            task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
            asyncio.create_task(
                self._context_manager.update_status(task.id, task.status)
            )
            self._task_results[task.id] = result
            return result

        except asyncio.CancelledError:
            return self._handle_cancellation(task, subtask_outputs, start_time)
        except Exception as e:
            return await self._handle_error(task, subtask_outputs, e, start_time)
        finally:
            await self._cleanup_team(team)


    async def _execute_with_team(self, task: Task) -> TaskResult:
        """使用团队模式执行任务。"""
        from ...models.team import TeamConfig
        start_time = time.time()
        team = None
        subtask_outputs: Dict[str, SubTaskResult] = {}
        
        try:
            # 分析和分解阶段
            task.status = TaskStatus.ANALYZING
            await self._context_manager.update_status(task.id, TaskStatus.ANALYZING)
            if task.id in self._cancelled_tasks:
                return self._create_cancelled_result(task, start_time)
            if task.complexity_score == 0.0:
                task.complexity_score = await self._task_decomposer.analyze_complexity(task)
            
            task.status = TaskStatus.DECOMPOSING
            await self._context_manager.update_status(task.id, TaskStatus.DECOMPOSING)
            if task.id in self._cancelled_tasks:
                return self._create_cancelled_result(task, start_time)
            decomposition = await self._task_decomposer.decompose(task)
            self._task_decompositions[task.id] = decomposition
            
            # 创建和设置团队
            team = await self._team_lifecycle_manager.create_team(task, TeamConfig())
            agent_roles, seen_roles = [], set()
            for st in decomposition.subtasks:
                hint = st.role_hint or "researcher"
                if hint not in seen_roles:
                    seen_roles.add(hint)
                    agent_roles.append(get_role_by_hint(hint))
            await self._team_lifecycle_manager.setup_team(team.id, agent_roles)
            self._team_lifecycle_manager.set_team_state(team.id, TeamState.EXECUTING)
            
            task.status = TaskStatus.EXECUTING
            await self._context_manager.update_status(task.id, TaskStatus.EXECUTING)
            if task.id in self._cancelled_tasks:
                return self._create_cancelled_result(task, start_time)
            
            # 发布任务到 TaskBoard
            task_board = self._team_lifecycle_manager.get_task_board(team.id)
            if task_board is None:
                raise TaskExecutionError(f"TaskBoard not found for team {team.id}")
            deps = {st.id: set(st.dependencies) for st in decomposition.subtasks}
            await task_board.publish_tasks(decomposition.subtasks, deps)
            
            # 执行
            message_bus = self._team_lifecycle_manager.get_message_bus(team.id)
            subtask_map = {st.id: st for st in decomposition.subtasks}
            
            async def agent_factory(subtask: SubTask):
                return await self._run_subtask(
                    task, subtask, subtask_map, subtask_outputs, message_bus
                )
            
            timeout_task = asyncio.create_task(self._monitor_timeout(task.id, start_time))
            try:
                wave_result = await self._wave_executor.execute(task_board, agent_factory)
            finally:
                timeout_task.cancel()
                try:
                    await timeout_task
                except asyncio.CancelledError:
                    pass
            
            # 完成和清理
            self._team_lifecycle_manager.set_team_state(team.id, TeamState.COMPLETED)
            await self._team_lifecycle_manager.disband_team(team.id)
            
            return self._build_team_result(
                task, decomposition, subtask_outputs, wave_result, start_time
            )
            
        except asyncio.CancelledError:
            return self._handle_cancellation(task, subtask_outputs, start_time)
        except Exception as e:
            return await self._handle_error(task, subtask_outputs, e, start_time)
        finally:
            await self._cleanup_team(team)
    
    async def _run_subtask(
        self, task: Task, subtask: SubTask, subtask_map: Dict[str, SubTask],
        subtask_outputs: Dict[str, SubTaskResult], message_bus
    ) -> str:
        """执行单个子任务。"""
        role = get_role_by_hint(subtask.role_hint or "researcher")
        enriched_content = self._enrich_content(subtask, subtask_map, subtask_outputs)
        enriched_subtask = SubTask(
            id=subtask.id, parent_task_id=subtask.parent_task_id,
            content=enriched_content, role_hint=subtask.role_hint,
            dependencies=subtask.dependencies, priority=subtask.priority,
            estimated_complexity=subtask.estimated_complexity,
        )
        agent = SubAgentImpl(
            agent_id=f"team-agent-{uuid.uuid4().hex[:8]}", role=role,
            qwen_client=self._agent_scheduler._qwen_client,
            tool_registry=self._agent_scheduler._tool_registry,
            config=self._build_role_config(role), message_bus=message_bus,
        )
        context = await self._context_manager.get_context(task.id)
        result = await agent.execute(enriched_subtask, context)
        subtask_outputs[subtask.id] = result
        if result.success:
            return result.output
        raise TaskExecutionError(result.error or "Subtask execution failed")

    async def _run_subtask_with_quality_gate(
        self,
        task: Task,
        subtask: SubTask,
        subtask_map: Dict[str, SubTask],
        subtask_outputs: Dict[str, SubTaskResult],
        message_bus,
        execution_flow: ExecutionFlow,
        supervisor: Optional["Supervisor"],
        stream_callback: Optional[StreamCallback],
        retry_counts: Dict[str, int],
        task_board,
        dependency_map: Dict[str, Set[str]],
    ) -> str:
        """执行子任务并在完成后进行质量门控评估。

        当 supervisor 存在且 enable_quality_gates 为 True 时，每个步骤完成后
        调用 evaluate_step_result() 评估结果质量，根据返回的 action 执行：
        - "continue": 继续执行下一步骤
        - "retry": 重新执行该步骤（不超过 max_retry_on_failure 次）
        - "add_step": 调用 adjust_execution_flow() 添加新步骤到 TaskBoard

        Args:
            task: 父任务对象
            subtask: 当前子任务
            subtask_map: 子任务ID到SubTask的映射
            subtask_outputs: 子任务执行结果存储
            message_bus: 消息总线
            execution_flow: 执行流程对象
            supervisor: Supervisor 实例（可选）
            stream_callback: 流式回调（可选）
            retry_counts: 每个子任务的重试计数
            task_board: 任务板
            dependency_map: 依赖关系映射

        Returns:
            子任务执行输出文本
        """
        # 执行子任务
        output = await self._run_subtask(
            task, subtask, subtask_map, subtask_outputs, message_bus
        )

        # 如果 supervisor 不存在或质量门控未启用，直接返回
        if not supervisor or not supervisor._config.enable_quality_gates:
            return output

        # 查找对应的 ExecutionStep
        step = execution_flow.steps.get(subtask.id)
        if not step:
            return output

        # 构建结果字典用于评估
        result_dict = {
            "subtask_id": subtask.id,
            "output": output,
            "success": True,
        }

        # 调用质量门控评估，异常时视为 continue
        try:
            evaluation = await supervisor.evaluate_step_result(
                step, result_dict, execution_flow, stream_callback
            )
        except Exception as e:
            logger.warning(
                "质量门控评估异常，视为 continue: %s", str(e)
            )
            return output

        action = evaluation.get("action", "continue")

        if action == "retry":
            max_retries = supervisor._config.max_retry_on_failure
            current_retries = retry_counts.get(subtask.id, 0)
            if current_retries < max_retries:
                retry_counts[subtask.id] = current_retries + 1
                logger.info(
                    "质量门控要求重试步骤 %s（第 %d/%d 次）",
                    subtask.id, current_retries + 1, max_retries,
                )
                # 清除之前的结果，重新执行
                subtask_outputs.pop(subtask.id, None)
                return await self._run_subtask_with_quality_gate(
                    task=task,
                    subtask=subtask,
                    subtask_map=subtask_map,
                    subtask_outputs=subtask_outputs,
                    message_bus=message_bus,
                    execution_flow=execution_flow,
                    supervisor=supervisor,
                    stream_callback=stream_callback,
                    retry_counts=retry_counts,
                    task_board=task_board,
                    dependency_map=dependency_map,
                )
            else:
                logger.warning(
                    "步骤 %s 已达最大重试次数 %d，继续执行",
                    subtask.id, max_retries,
                )
                return output

        elif action == "add_step":
            adjustments = evaluation.get("adjustments", [])
            if adjustments:
                try:
                    await supervisor.adjust_execution_flow(
                        execution_flow, adjustments, stream_callback
                    )
                    # 将新添加的步骤转换为 SubTask 并发布到 TaskBoard
                    new_subtasks = []
                    new_deps = {}
                    for adj in adjustments:
                        if adj.get("type") == "add_step":
                            step_id = adj.get("step_id", "")
                            new_step = execution_flow.steps.get(step_id)
                            if new_step:
                                new_subtask = SubTask(
                                    id=new_step.step_id,
                                    parent_task_id=task.id,
                                    content=new_step.description,
                                    role_hint=new_step.agent_type,
                                    dependencies=set(new_step.dependencies),
                                    priority=new_step.step_number,
                                    estimated_complexity=1.0,
                                )
                                new_subtasks.append(new_subtask)
                                new_deps[new_step.step_id] = set(new_step.dependencies)
                                subtask_map[new_subtask.id] = new_subtask
                    if new_subtasks:
                        await task_board.publish_tasks(new_subtasks, new_deps)
                        logger.info(
                            "质量门控添加了 %d 个新步骤到 TaskBoard",
                            len(new_subtasks),
                        )
                except Exception as e:
                    logger.warning(
                        "动态调整执行流程异常，忽略调整: %s", str(e)
                    )

        # action == "continue" 或其他情况，直接返回
        return output

    def _enrich_content(
        self, subtask: SubTask, subtask_map: Dict[str, SubTask],
        subtask_outputs: Dict[str, SubTaskResult]
    ) -> str:
        """注入前序依赖任务结果到子任务内容。"""
        if not subtask.dependencies:
            return subtask.content
        dep_sections = []
        for dep_id in subtask.dependencies:
            dep_result = subtask_outputs.get(dep_id)
            if dep_result and dep_result.success and dep_result.output:
                dep_st = subtask_map.get(dep_id)
                dep_desc = dep_st.content[:100] if dep_st else dep_id[:8]
                dep_output = dep_result.output[:4000]
                dep_sections.append(f"### 前序任务: {dep_desc}\n{dep_output}")
        if not dep_sections:
            return subtask.content
        return (f"{subtask.content}\n\n## 前序任务结果（请基于以下资料整合输出）\n\n"
                + "\n\n---\n\n".join(dep_sections))
    
    def _build_team_result(
        self, task: Task, decomposition: TaskDecomposition,
        subtask_outputs: Dict[str, SubTaskResult], wave_result, start_time: float
    ) -> TaskResult:
        """构建团队模式执行结果。"""
        execution_time = time.time() - start_time
        success = wave_result.failed_tasks == 0 and wave_result.completed_tasks > 0
        task.metadata["wave_execution_result"] = wave_result.to_dict()
        sub_results = list(subtask_outputs.values())
        output_parts = [sr.output for st in decomposition.subtasks 
                       if (sr := subtask_outputs.get(st.id)) and sr.success and sr.output]
        
        if output_parts:
            aggregated_output = output_parts[0] if len(output_parts) == 1 else (
                self._aggregate_outputs(sub_results, decomposition, output_parts)
            )
        else:
            aggregated_output = (f"Completed {wave_result.completed_tasks}/"
                               f"{wave_result.total_tasks} tasks in {wave_result.total_waves} waves")
        
        result = TaskResult(
            task_id=task.id, success=success, output=aggregated_output,
            error=None if success else f"{wave_result.failed_tasks} tasks failed",
            execution_time=execution_time, sub_results=sub_results,
        )
        task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        asyncio.create_task(self._context_manager.update_status(task.id, task.status))
        self._task_results[task.id] = result
        return result
    
    def _aggregate_outputs(
        self, sub_results: List[SubTaskResult], decomposition: TaskDecomposition,
        output_parts: List[str]
    ) -> str:
        """聚合多个子任务输出。"""
        try:
            loop = asyncio.get_event_loop()
            agg_result = loop.run_until_complete(
                self._result_aggregator.aggregate(sub_results, decomposition)
            )
            return agg_result.final_output or "\n\n---\n\n".join(output_parts)
        except Exception:
            return "\n\n---\n\n".join(output_parts)
    
    def _handle_cancellation(
        self, task: Task, subtask_outputs: Dict[str, SubTaskResult], start_time: float
    ) -> TaskResult:
        """处理任务取消。"""
        partial_results = list(subtask_outputs.values())
        partial_outputs = [sr.output for sr in partial_results if sr.success and sr.output]
        result = TaskResult(
            task_id=task.id, success=False,
            output="\n\n---\n\n".join(partial_outputs) if partial_outputs else None,
            error="Task cancelled", execution_time=time.time() - start_time,
            sub_results=partial_results,
        )
        task.status = TaskStatus.FAILED
        asyncio.create_task(self._context_manager.update_status(task.id, TaskStatus.FAILED))
        self._task_results[task.id] = result
        return result
    
    async def _handle_error(
        self, task: Task, subtask_outputs: Dict[str, SubTaskResult],
        error: Exception, start_time: float
    ) -> TaskResult:
        """处理执行错误。"""
        execution_time = time.time() - start_time
        task.status = TaskStatus.FAILED
        await self._context_manager.update_status(task.id, TaskStatus.FAILED)
        await self._context_manager.add_error(task.id, {
            "type": "execution_error", "error": str(error), "timestamp": time.time()
        })
        partial_results = list(subtask_outputs.values())
        partial_outputs = [sr.output for sr in partial_results if sr.success and sr.output]
        result = TaskResult(
            task_id=task.id, success=len(partial_outputs) > 0,
            output="\n\n---\n\n".join(partial_outputs) if partial_outputs else None,
            error=str(error), execution_time=execution_time, sub_results=partial_results,
        )
        self._task_results[task.id] = result
        return result
    
    async def _cleanup_team(self, team) -> None:
        """清理团队资源。"""
        if team and self._team_lifecycle_manager:
            try:
                status = await self._team_lifecycle_manager.get_team_status(team.id)
                if status.state != TeamState.DISBANDED:
                    await self._team_lifecycle_manager.disband_team(team.id)
            except Exception:
                pass

    def _build_role_config(self, role: AgentRole) -> QwenConfig:
        """根据角色构建 QwenConfig。"""
        mc = role.model_config
        if not mc:
            return QwenConfig()
        model_str = mc.get("model", "qwen3-max")
        model = QwenModel.QWEN3_MAX
        for m in QwenModel:
            if m.value == model_str:
                model = m
                break
        return QwenConfig(
            model=model, temperature=mc.get("temperature", 0.7),
            enable_search=mc.get("enable_search", False),
            enable_thinking=mc.get("enable_thinking", False),
        )

    async def _execute_with_scheduler(self, task: Task) -> TaskResult:
        """使用调度器模式执行任务。"""
        from ...interfaces.result_aggregator import ConflictResolution
        start_time = time.time()
        
        try:
            task.status = TaskStatus.ANALYZING
            await self._context_manager.update_status(task.id, TaskStatus.ANALYZING)
            if task.id in self._cancelled_tasks:
                return self._create_cancelled_result(task, start_time)
            if task.complexity_score == 0.0:
                task.complexity_score = await self._task_decomposer.analyze_complexity(task)
            
            task.status = TaskStatus.DECOMPOSING
            await self._context_manager.update_status(task.id, TaskStatus.DECOMPOSING)
            if task.id in self._cancelled_tasks:
                return self._create_cancelled_result(task, start_time)
            decomposition = await self._task_decomposer.decompose(task)
            self._task_decompositions[task.id] = decomposition
            
            task.status = TaskStatus.EXECUTING
            await self._context_manager.update_status(task.id, TaskStatus.EXECUTING)
            if task.id in self._cancelled_tasks:
                return self._create_cancelled_result(task, start_time)
            
            timeout_task = asyncio.create_task(self._monitor_timeout(task.id, start_time))
            try:
                sub_results = await self._agent_scheduler.schedule_execution(decomposition)
                if task.id in self._cancelled_tasks:
                    return self._create_cancelled_result(task, start_time)
                
                task.status = TaskStatus.AGGREGATING
                await self._context_manager.update_status(task.id, TaskStatus.AGGREGATING)
                aggregation_result = await self._result_aggregator.aggregate(
                    sub_results, decomposition, ConflictResolution.MAJORITY_VOTE
                )
                
                execution_time = time.time() - start_time
                result = TaskResult(
                    task_id=task.id, success=aggregation_result.success,
                    output=aggregation_result.final_output,
                    error=None if aggregation_result.success else self._extract_error(sub_results),
                    execution_time=execution_time, sub_results=sub_results,
                )
                task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
                await self._context_manager.update_status(task.id, task.status)
            finally:
                timeout_task.cancel()
                try:
                    await timeout_task
                except asyncio.CancelledError:
                    pass
            
            self._task_results[task.id] = result
            return result
        except asyncio.CancelledError:
            return self._create_cancelled_result(task, start_time)
        except Exception as e:
            execution_time = time.time() - start_time
            task.status = TaskStatus.FAILED
            await self._context_manager.update_status(task.id, TaskStatus.FAILED)
            await self._context_manager.add_error(task.id, {
                "type": "execution_error", "error": str(e), "timestamp": time.time()
            })
            result = TaskResult(
                task_id=task.id, success=False, output=None, error=str(e),
                execution_time=execution_time, sub_results=[],
            )
            self._task_results[task.id] = result
            return result
    
    def _create_cancelled_result(self, task: Task, start_time: float) -> TaskResult:
        """创建取消结果。"""
        task.status = TaskStatus.CANCELLED
        return TaskResult(
            task_id=task.id, success=False, output=None, error="Task was cancelled",
            execution_time=time.time() - start_time, sub_results=[],
        )
    
    def _extract_error(self, sub_results: List[SubTaskResult]) -> Optional[str]:
        """从子结果中提取错误信息。"""
        errors = [f"[{r.subtask_id}] {r.error}" for r in sub_results if not r.success and r.error]
        return "; ".join(errors[:5]) if errors else None
    
    async def _monitor_timeout(self, task_id: str, start_time: float) -> None:
        """监控任务执行超时。"""
        warning_time = self._config.execution_timeout * self._config.timeout_warning_threshold
        try:
            await asyncio.sleep(warning_time)
            elapsed = time.time() - start_time
            remaining = self._config.execution_timeout - elapsed
            for callback in self._timeout_warning_callbacks:
                try:
                    callback(task_id, elapsed, remaining)
                except Exception:
                    pass
            await self._context_manager.add_error(task_id, {
                "type": "timeout_warning", "elapsed": elapsed,
                "remaining": remaining, "timestamp": time.time()
            })
        except asyncio.CancelledError:
            pass
