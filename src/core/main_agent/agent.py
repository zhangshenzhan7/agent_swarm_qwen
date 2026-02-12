"""MainAgent 核心类模块。

本模块包含 MainAgent 核心类，负责任务的全生命周期管理与编排协调。
MainAgent 通过组合模式将职责委托给内部模块：
    - TaskExecutor: 任务执行协调
    - TaskMonitor: 进度监控与超时管理
    - TaskPlanner: 计划管理

主要职责：
    - 任务提交与解析（submit_task, parse_task）
    - 任务状态管理（get_task_status, get_task, get_all_tasks）
    - 任务取消与超时处理（cancel_task, handle_timeout）
    - 优雅关闭（graceful_shutdown）
"""

import asyncio
import time
import uuid
import re
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

from ...interfaces.main_agent import IMainAgent
from ...interfaces.task_decomposer import ITaskDecomposer
from ...interfaces.agent_scheduler import IAgentScheduler
from ...interfaces.result_aggregator import IResultAggregator
from ...interfaces.context_manager import IExecutionContextManager
from ...interfaces.team_lifecycle import ITeamLifecycleManager
from ...interfaces.wave_executor import IWaveExecutor
from ...models.task import Task, TaskDecomposition
from ...models.result import TaskResult
from ...models.enums import TaskStatus
from ...models.team import ExecutionPlan

from .executor import TaskExecutor, TaskExecutionError, DelegateModeForbiddenError
from .monitor import TaskMonitor, TaskNotFoundError
from .planner import TaskPlanner


class MainAgentError(Exception):
    """主智能体错误基类"""
    pass


class TaskParsingError(MainAgentError):
    """任务解析错误"""
    pass


@dataclass
class MainAgentConfig:
    """主智能体配置。"""
    complexity_threshold: float = 3.0
    execution_timeout: float = 3600.0
    timeout_warning_threshold: float = 0.8
    min_task_content_length: int = 1
    max_task_content_length: int = 100000
    delegate_mode: bool = False
    use_team_mode: bool = False


class MainAgent(IMainAgent):
    """主智能体实现。"""

    def __init__(
        self,
        task_decomposer: ITaskDecomposer,
        agent_scheduler: IAgentScheduler,
        result_aggregator: IResultAggregator,
        context_manager: IExecutionContextManager,
        config: Optional[MainAgentConfig] = None,
        team_lifecycle_manager: Optional[ITeamLifecycleManager] = None,
        wave_executor: Optional[IWaveExecutor] = None,
    ):
        """初始化主智能体。"""
        self._task_decomposer = task_decomposer
        self._agent_scheduler = agent_scheduler
        self._result_aggregator = result_aggregator
        self._context_manager = context_manager
        self._config = config or MainAgentConfig()
        self._team_lifecycle_manager = team_lifecycle_manager
        self._wave_executor = wave_executor

        self._tasks: Dict[str, Task] = {}
        self._task_decompositions: Dict[str, TaskDecomposition] = {}
        self._task_results: Dict[str, TaskResult] = {}

        self._executing_tasks: Dict[str, asyncio.Task] = {}
        self._cancelled_tasks: set = set()
        self._timeout_warning_callbacks: List[callable] = []

        self._executor = TaskExecutor(
            task_decomposer=task_decomposer,
            agent_scheduler=agent_scheduler,
            result_aggregator=result_aggregator,
            context_manager=context_manager,
            config=self._config,
            team_lifecycle_manager=team_lifecycle_manager,
            wave_executor=wave_executor,
            tasks=self._tasks,
            task_decompositions=self._task_decompositions,
            task_results=self._task_results,
            cancelled_tasks=self._cancelled_tasks,
            timeout_warning_callbacks=self._timeout_warning_callbacks,
        )

        self._monitor = TaskMonitor(
            context_manager=context_manager,
            config=self._config,
            tasks=self._tasks,
            task_decompositions=self._task_decompositions,
            task_results=self._task_results,
            timeout_warning_callbacks=self._timeout_warning_callbacks,
        )

        self._planner = TaskPlanner(
            task_decomposer=task_decomposer,
            agent_scheduler=agent_scheduler,
            result_aggregator=result_aggregator,
            context_manager=context_manager,
            config=self._config,
            tasks=self._tasks,
            task_decompositions=self._task_decompositions,
            task_results=self._task_results,
        )
    async def submit_task(self, content, metadata=None):
        """提交任务。"""
        self._validate_task_content(content)
        task_type = self._identify_task_type(content)
        task_id = str(uuid.uuid4())
        task = Task(id=task_id, content=content, status=TaskStatus.PENDING, complexity_score=0.0, created_at=time.time(), metadata=metadata or {})
        task.metadata["task_type"] = task_type
        try:
            complexity = await self._task_decomposer.analyze_complexity(task)
            task.complexity_score = complexity
        except Exception as e:
            task.complexity_score = 5.0
            task.metadata["complexity_analysis_error"] = str(e)
        self._tasks[task_id] = task
        await self._context_manager.create_context(task)
        return task

    def _validate_task_content(self, content):
        if content is None:
            raise TaskParsingError("Task content cannot be None")
        if not isinstance(content, str):
            raise TaskParsingError(f"Task content must be a string, got {type(content).__name__}")
        stripped_content = content.strip()
        if not stripped_content:
            raise TaskParsingError("Task content cannot be empty or whitespace only")
        if len(stripped_content) < self._config.min_task_content_length:
            raise TaskParsingError(f"Task content too short (minimum {self._config.min_task_content_length} characters)")
        if len(content) > self._config.max_task_content_length:
            raise TaskParsingError(f"Task content too long (maximum {self._config.max_task_content_length} characters)")

    def _identify_task_type(self, content):
        content_lower = content.lower()
        type_keywords = {
            "research": ["研究", "调研", "调查", "research", "investigate", "study"],
            "analysis": ["分析", "评估", "比较", "analyze", "evaluate", "compare"],
            "writing": ["撰写", "编写", "写", "write", "draft", "compose"],
            "coding": ["代码", "编程", "开发", "实现", "code", "program", "develop", "implement"],
            "translation": ["翻译", "转换", "translate", "convert"],
            "search": ["搜索", "查找", "检索", "search", "find", "lookup"],
            "summary": ["总结", "摘要", "概括", "summarize", "summary", "abstract"],
            "verification": ["核实", "验证", "确认", "verify", "validate", "confirm"],
        }
        type_scores = {}
        for task_type, keywords in type_keywords.items():
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > 0:
                type_scores[task_type] = score
        if type_scores:
            return max(type_scores.items(), key=lambda x: x[1])[0]
        return "general"

    def parse_task(self, content):
        self._validate_task_content(content)
        task_type = self._identify_task_type(content)
        return Task(id=str(uuid.uuid4()), content=content, status=TaskStatus.PENDING, complexity_score=self._estimate_complexity_sync(content), created_at=time.time(), metadata={"task_type": task_type})

    def _estimate_complexity_sync(self, content):
        score = 0.0
        length = len(content)
        if length > 500: score += 2.0
        elif length > 200: score += 1.5
        elif length > 100: score += 1.0
        elif length > 50: score += 0.5
        sentences = [s.strip() for s in re.split(r'[。.!?！？]', content) if s.strip()]
        if len(sentences) > 5: score += 2.0
        elif len(sentences) > 3: score += 1.0
        elif len(sentences) > 1: score += 0.5
        question_count = content.count('?') + content.count('？')
        if question_count > 3: score += 2.0
        elif question_count > 1: score += 1.0
        elif question_count > 0: score += 0.5
        return min(max(score, 0.0), 10.0)

    async def execute_task(self, task):
        return await self._executor.execute(task)

    async def get_task_status(self, task_id):
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task '{task_id}' not found")
        return task.status

    async def get_execution_progress(self, task_id):
        return await self._monitor.get_progress(task_id)

    async def generate_execution_summary(self, task_id):
        return await self._monitor.generate_summary(task_id)

    def get_task(self, task_id):
        return self._tasks.get(task_id)

    def get_task_result(self, task_id):
        return self._task_results.get(task_id)

    def get_task_decomposition(self, task_id):
        return self._task_decompositions.get(task_id)

    async def cancel_task(self, task_id):
        task = self._tasks.get(task_id)
        if task is None:
            return False
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return False
        self._cancelled_tasks.add(task_id)
        executing_task = self._executing_tasks.get(task_id)
        if executing_task and not executing_task.done():
            executing_task.cancel()
        try:
            terminated_count = await self._agent_scheduler.terminate_all_agents()
        except Exception:
            terminated_count = 0
        task.status = TaskStatus.CANCELLED
        await self._context_manager.update_status(task_id, TaskStatus.CANCELLED)
        await self._context_manager.add_error(task_id, {"type": "task_cancelled", "terminated_agents": terminated_count, "timestamp": time.time()})
        await self._cleanup_task_resources(task_id)
        return True

    async def _cleanup_task_resources(self, task_id):
        try:
            await self._agent_scheduler.cleanup()
        except Exception:
            pass
        if task_id in self._executing_tasks:
            del self._executing_tasks[task_id]
        self._cancelled_tasks.discard(task_id)

    async def handle_timeout(self, task_id):
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task '{task_id}' not found")
        await self._context_manager.add_error(task_id, {"type": "execution_timeout", "timeout": self._config.execution_timeout, "timestamp": time.time()})
        await self.cancel_task(task_id)
        result = TaskResult(task_id=task_id, success=False, output=None, error=f"Task execution timed out after {self._config.execution_timeout} seconds", execution_time=self._config.execution_timeout, sub_results=[])
        self._task_results[task_id] = result
        return result

    async def execute_with_timeout(self, task):
        try:
            return await asyncio.wait_for(self.execute_task(task), timeout=self._config.execution_timeout)
        except asyncio.TimeoutError:
            return await self.handle_timeout(task.id)

    async def graceful_shutdown(self):
        shutdown_summary = {"cancelled_tasks": [], "terminated_agents": 0, "errors": []}
        for task_id, task in list(self._tasks.items()):
            if task.status in (TaskStatus.ANALYZING, TaskStatus.DECOMPOSING, TaskStatus.EXECUTING, TaskStatus.AGGREGATING):
                try:
                    await self.cancel_task(task_id)
                    shutdown_summary["cancelled_tasks"].append(task_id)
                except Exception as e:
                    shutdown_summary["errors"].append({"task_id": task_id, "error": str(e)})
        try:
            terminated = await self._agent_scheduler.terminate_all_agents()
            shutdown_summary["terminated_agents"] = terminated
        except Exception as e:
            shutdown_summary["errors"].append({"component": "agent_scheduler", "error": str(e)})
        try:
            await self._agent_scheduler.cleanup()
        except Exception as e:
            shutdown_summary["errors"].append({"component": "cleanup", "error": str(e)})
        return shutdown_summary

    def is_task_cancelled(self, task_id):
        return task_id in self._cancelled_tasks

    def get_all_tasks(self):
        return dict(self._tasks)

    def get_active_tasks(self):
        active_statuses = {TaskStatus.PENDING, TaskStatus.ANALYZING, TaskStatus.DECOMPOSING, TaskStatus.EXECUTING, TaskStatus.AGGREGATING}
        return [task for task in self._tasks.values() if task.status in active_statuses]

    def add_timeout_warning_callback(self, callback):
        self._timeout_warning_callbacks.append(callback)

    async def plan_task(self, task):
        return await self._planner.plan(task)

    async def confirm_and_execute(self, task, plan):
        return await self._planner.confirm_and_execute(task, plan)

    async def revise_plan(self, task, plan, feedback):
        return await self._planner.revise_plan(task, plan, feedback)
