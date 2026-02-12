"""Agent Scheduler implementation."""

import asyncio
import time
import uuid
import heapq
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from enum import Enum

from .interfaces.agent_scheduler import IAgentScheduler, SchedulerConfig
from .interfaces.tool_registry import IToolRegistry
from .interfaces.context_manager import IExecutionContextManager
from .models.task import SubTask, TaskDecomposition
from .models.agent import SubAgent, AgentRole, get_role_by_hint
from .models.result import SubTaskResult
from .models.enums import AgentStatus, TaskStatus
from .models.context import ExecutionContext
from .sub_agent import SubAgentImpl
from .qwen.interface import IQwenClient
from .qwen.models import QwenConfig, QwenModel


class SchedulerError(Exception):
    """调度器错误基类"""
    pass


class ResourceLimitError(SchedulerError):
    """资源限制错误"""
    pass


class AgentNotFoundError(SchedulerError):
    """智能体未找到错误"""
    pass


class DependencyError(SchedulerError):
    """依赖错误"""
    pass


class SubTaskStatus(Enum):
    """子任务调度状态"""
    PENDING = "pending"      # 等待依赖完成
    QUEUED = "queued"        # 已入队等待执行
    RUNNING = "running"      # 正在执行
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 执行失败
    BLOCKED = "blocked"      # 被依赖失败阻塞


@dataclass(order=True)
class PriorityItem:
    """优先级队列项"""
    priority: int
    subtask_id: str = field(compare=False)
    subtask: SubTask = field(compare=False)


class AgentScheduler(IAgentScheduler):
    """智能体调度器实现"""
    
    def __init__(
        self,
        qwen_client: IQwenClient,
        tool_registry: IToolRegistry,
        context_manager: Optional[IExecutionContextManager] = None,
        config: Optional[SchedulerConfig] = None,
    ):
        """
        初始化调度器
        
        Args:
            qwen_client: Qwen 客户端
            tool_registry: 工具注册表
            context_manager: 执行上下文管理器（可选）
            config: 调度器配置
        """
        self._qwen_client = qwen_client
        self._tool_registry = tool_registry
        self._context_manager = context_manager
        self._config = config or SchedulerConfig()
        
        # 智能体池
        self._agents: Dict[str, SubAgentImpl] = {}
        self._agent_data: Dict[str, SubAgent] = {}  # SubAgent 数据对象
        
        # 并发控制
        self._active_count = 0
        self._active_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(self._config.max_concurrent_agents)
        
        # 工具调用计数
        self._total_tool_calls = 0
        self._tool_calls_lock = asyncio.Lock()
        
        # 任务状态跟踪
        self._subtask_status: Dict[str, SubTaskStatus] = {}
        self._subtask_results: Dict[str, SubTaskResult] = {}
        
        # 优先级队列
        self._priority_queue: List[PriorityItem] = []
        self._queue_lock = asyncio.Lock()
        
        # 等待条件
        self._resource_available = asyncio.Condition()
        
        # 当前执行上下文
        self._current_context: Optional[ExecutionContext] = None
        self._current_task_id: Optional[str] = None

    async def _on_agent_state_change(
        self, 
        agent_id: str, 
        old_status: AgentStatus, 
        new_status: AgentStatus
    ) -> None:
        """智能体状态变更回调"""
        # 更新 SubAgent 数据对象状态
        if agent_id in self._agent_data:
            self._agent_data[agent_id].status = new_status
            if new_status in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.TERMINATED):
                self._agent_data[agent_id].completed_at = time.time()
        
        # 更新上下文中的智能体状态
        if self._context_manager and self._current_task_id:
            context = await self._context_manager.get_context(self._current_task_id)
            if context and agent_id in context.sub_agents:
                context.sub_agents[agent_id].status = new_status
    
    def _build_role_config(self, role: AgentRole) -> QwenConfig:
        """根据角色的 model_config 构建专属 QwenConfig
        
        第三方模型（DeepSeek/GLM/Kimi）不支持 Qwen 专属功能：
        - enable_search / search_strategy（联网搜索）
        - enable_code_interpreter（代码解释器）
        对于不支持 enable_thinking 的模型会自动关闭。
        """
        mc = role.model_config
        if not mc:
            return QwenConfig()
        
        model_str = mc.get("model", "qwen3-max")
        model = QwenModel.QWEN3_MAX
        for m in QwenModel:
            if m.value == model_str:
                model = m
                break
        
        is_native = model.is_qwen_native()
        enable_thinking = mc.get("enable_thinking", False)
        # 不支持 thinking 的模型强制关闭
        if enable_thinking and not model.supports_thinking():
            enable_thinking = False
        
        return QwenConfig(
            model=model,
            temperature=mc.get("temperature", 0.7),
            # 第三方模型不支持 Qwen 联网搜索
            enable_search=mc.get("enable_search", True) if is_native else False,
            enable_thinking=enable_thinking,
        )
    
    async def create_agent(self, subtask: SubTask, role: AgentRole) -> SubAgent:
        """
        创建子智能体
        
        Args:
            subtask: 要执行的子任务
            role: 智能体角色
            
        Returns:
            创建的子智能体数据对象
            
        Raises:
            ResourceLimitError: 如果达到最大并发限制
        """
        async with self._active_lock:
            if self._active_count >= self._config.max_concurrent_agents:
                raise ResourceLimitError(
                    f"Maximum concurrent agents ({self._config.max_concurrent_agents}) reached"
                )
        
        # 生成智能体 ID
        agent_id = str(uuid.uuid4())
        
        # 根据角色的 model_config 构建专属 QwenConfig
        role_config = self._build_role_config(role)
        
        # 创建 SubAgentImpl 实例
        agent_impl = SubAgentImpl(
            agent_id=agent_id,
            role=role,
            qwen_client=self._qwen_client,
            tool_registry=self._tool_registry,
            config=role_config,
            on_state_change=self._on_agent_state_change,
        )
        
        # 创建 SubAgent 数据对象
        agent_data = SubAgent(
            id=agent_id,
            role=role,
            assigned_subtask=subtask,
            status=AgentStatus.IDLE,
            created_at=time.time(),
        )
        
        # 存储智能体
        self._agents[agent_id] = agent_impl
        self._agent_data[agent_id] = agent_data
        
        # 注册到上下文
        if self._context_manager and self._current_task_id:
            await self._context_manager.register_agent(self._current_task_id, agent_data)
        
        return agent_data
    
    async def _acquire_execution_slot(self) -> bool:
        """
        获取执行槽位
        
        Returns:
            是否成功获取
        """
        async with self._active_lock:
            if self._active_count >= self._config.max_concurrent_agents:
                return False
            self._active_count += 1
            return True
    
    async def _release_execution_slot(self) -> None:
        """释放执行槽位"""
        async with self._active_lock:
            self._active_count = max(0, self._active_count - 1)
        
        # 通知等待的任务
        async with self._resource_available:
            self._resource_available.notify_all()
    
    async def _wait_for_slot(self, timeout: Optional[float] = None) -> bool:
        """
        等待执行槽位
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            是否成功获取槽位
        """
        start_time = time.time()
        
        while True:
            if await self._acquire_execution_slot():
                return True
            
            # 检查超时
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return False
                remaining = timeout - elapsed
            else:
                remaining = None
            
            # 等待资源可用
            try:
                async with self._resource_available:
                    await asyncio.wait_for(
                        self._resource_available.wait(),
                        timeout=remaining
                    )
            except asyncio.TimeoutError:
                return False
    
    async def _check_tool_call_limit(self) -> bool:
        """检查是否达到工具调用限制"""
        async with self._tool_calls_lock:
            return self._total_tool_calls < self._config.max_tool_calls
    
    async def _increment_tool_calls(self, count: int = 1) -> int:
        """增加工具调用计数"""
        async with self._tool_calls_lock:
            self._total_tool_calls += count
            return self._total_tool_calls

    async def get_active_agents(self) -> List[SubAgent]:
        """获取所有活跃的子智能体"""
        active = []
        for agent_id, agent_data in self._agent_data.items():
            if agent_data.status in (AgentStatus.IDLE, AgentStatus.RUNNING):
                active.append(agent_data)
        return active
    
    async def get_resource_usage(self) -> Dict[str, Any]:
        """获取资源使用情况"""
        async with self._active_lock:
            active_count = self._active_count
        
        async with self._tool_calls_lock:
            tool_calls = self._total_tool_calls
        
        return {
            "active_agents": active_count,
            "max_concurrent_agents": self._config.max_concurrent_agents,
            "total_agents_created": len(self._agents),
            "total_tool_calls": tool_calls,
            "max_tool_calls": self._config.max_tool_calls,
            "tool_calls_remaining": self._config.max_tool_calls - tool_calls,
        }
    
    async def terminate_agent(self, agent_id: str) -> bool:
        """
        终止指定子智能体
        
        Args:
            agent_id: 智能体ID
            
        Returns:
            是否成功终止
        """
        if agent_id not in self._agents:
            return False
        
        agent_impl = self._agents[agent_id]
        
        # 停止智能体
        await agent_impl.stop()
        
        # 清理资源
        await agent_impl.cleanup()
        
        # 更新状态
        if agent_id in self._agent_data:
            self._agent_data[agent_id].status = AgentStatus.TERMINATED
            self._agent_data[agent_id].completed_at = time.time()
        
        return True
    
    async def cleanup(self) -> None:
        """清理所有资源"""
        # 终止所有智能体
        for agent_id in list(self._agents.keys()):
            await self.terminate_agent(agent_id)
        
        # 清空状态
        self._agents.clear()
        self._agent_data.clear()
        self._subtask_status.clear()
        self._subtask_results.clear()
        self._priority_queue.clear()
        
        # 重置计数器
        async with self._active_lock:
            self._active_count = 0
        
        async with self._tool_calls_lock:
            self._total_tool_calls = 0

    async def _execute_single_agent(
        self, 
        agent_impl: SubAgentImpl,
        subtask: SubTask,
        context: ExecutionContext,
    ) -> SubTaskResult:
        """
        执行单个智能体
        
        Args:
            agent_impl: 智能体实现
            subtask: 子任务
            context: 执行上下文
            
        Returns:
            执行结果
        """
        try:
            # 执行任务
            result = await asyncio.wait_for(
                agent_impl.execute(subtask, context),
                timeout=self._config.agent_timeout
            )
            
            # 更新工具调用计数
            tool_call_count = len(result.tool_calls)
            if tool_call_count > 0:
                await self._increment_tool_calls(tool_call_count)
                if self._context_manager and self._current_task_id:
                    await self._context_manager.increment_tool_calls(
                        self._current_task_id, tool_call_count
                    )
            
            return result
            
        except asyncio.TimeoutError:
            # 超时处理
            await agent_impl.stop()
            return SubTaskResult(
                subtask_id=subtask.id,
                agent_id=agent_impl.id,
                success=False,
                output=None,
                error=f"Agent execution timed out after {self._config.agent_timeout}s",
                tool_calls=agent_impl.tool_calls,
                execution_time=self._config.agent_timeout,
                token_usage=agent_impl.token_usage,
            )
        except Exception as e:
            import traceback
            print(f"[Scheduler] Agent {agent_impl.id[:8]} 执行异常: {e}")
            print(traceback.format_exc())
            return SubTaskResult(
                subtask_id=subtask.id,
                agent_id=agent_impl.id,
                success=False,
                output=None,
                error=str(e),
                tool_calls=agent_impl.tool_calls if hasattr(agent_impl, 'tool_calls') else [],
                execution_time=0,
                token_usage={},
            )
    
    async def execute_parallel_batch(self, agents: List[SubAgent]) -> List[SubTaskResult]:
        """
        并行执行一批子智能体
        
        Args:
            agents: 要并行执行的子智能体列表
            
        Returns:
            执行结果列表
        """
        if not agents:
            return []
        
        # 获取执行上下文
        context = self._current_context
        if not context and self._context_manager and self._current_task_id:
            context = await self._context_manager.get_context(self._current_task_id)
        
        if not context:
            # 创建临时上下文
            from .models.task import Task
            temp_task = Task(
                id=str(uuid.uuid4()),
                content="Temporary task",
                status=TaskStatus.EXECUTING,
                complexity_score=0,
                created_at=time.time(),
            )
            context = ExecutionContext(
                task_id=temp_task.id,
                start_time=time.time(),
                status=TaskStatus.EXECUTING,
            )
        
        async def execute_with_slot(agent_data: SubAgent) -> SubTaskResult:
            """带槽位控制的执行"""
            agent_id = agent_data.id
            subtask = agent_data.assigned_subtask
            
            # 等待执行槽位
            if not await self._wait_for_slot(timeout=self._config.agent_timeout):
                return SubTaskResult(
                    subtask_id=subtask.id,
                    agent_id=agent_id,
                    success=False,
                    output=None,
                    error="Failed to acquire execution slot",
                    tool_calls=[],
                    execution_time=0,
                    token_usage={},
                )
            
            try:
                # 获取智能体实现
                agent_impl = self._agents.get(agent_id)
                if not agent_impl:
                    return SubTaskResult(
                        subtask_id=subtask.id,
                        agent_id=agent_id,
                        success=False,
                        output=None,
                        error=f"Agent {agent_id} not found",
                        tool_calls=[],
                        execution_time=0,
                        token_usage={},
                    )
                
                # 执行
                result = await self._execute_single_agent(agent_impl, subtask, context)
                
                # 记录结果
                if self._context_manager and self._current_task_id:
                    await self._context_manager.record_result(self._current_task_id, result)
                
                return result
                
            finally:
                # 释放槽位
                await self._release_execution_slot()
        
        # 并行执行所有智能体
        tasks = [execute_with_slot(agent) for agent in agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                agent_data = agents[i]
                processed_results.append(SubTaskResult(
                    subtask_id=agent_data.assigned_subtask.id,
                    agent_id=agent_data.id,
                    success=False,
                    output=None,
                    error=str(result),
                    tool_calls=[],
                    execution_time=0,
                    token_usage={},
                ))
            else:
                processed_results.append(result)
        
        return processed_results

    def _build_dependency_graph(
        self, 
        subtasks: List[SubTask]
    ) -> Dict[str, Set[str]]:
        """
        构建依赖图
        
        Args:
            subtasks: 子任务列表
            
        Returns:
            依赖图 {subtask_id: set of dependency ids}
        """
        subtask_ids = {st.id for st in subtasks}
        graph = {}
        
        for subtask in subtasks:
            # 只保留有效的依赖（存在于当前子任务列表中的）
            valid_deps = subtask.dependencies & subtask_ids
            graph[subtask.id] = valid_deps
        
        return graph
    
    def _compute_layers(
        self, 
        subtasks: List[SubTask],
        dependency_graph: Dict[str, Set[str]]
    ) -> List[List[SubTask]]:
        """
        计算分层执行顺序
        
        使用拓扑排序将子任务分层，每层内的任务可以并行执行。
        
        Args:
            subtasks: 子任务列表
            dependency_graph: 依赖图
            
        Returns:
            分层的子任务列表
        """
        subtask_map = {st.id: st for st in subtasks}
        remaining = set(subtask_map.keys())
        completed = set()
        layers = []
        
        while remaining:
            # 找出所有依赖已完成的任务
            ready = []
            for st_id in remaining:
                deps = dependency_graph.get(st_id, set())
                if deps <= completed:
                    ready.append(subtask_map[st_id])
            
            if not ready:
                # 存在循环依赖，打破循环
                # 选择优先级最高的任务
                remaining_list = [subtask_map[st_id] for st_id in remaining]
                remaining_list.sort(key=lambda x: x.priority, reverse=True)
                ready = [remaining_list[0]]
            
            # 按优先级排序
            ready.sort(key=lambda x: x.priority, reverse=True)
            
            layers.append(ready)
            
            # 更新状态
            for st in ready:
                remaining.remove(st.id)
                completed.add(st.id)
        
        return layers
    
    async def schedule_execution(self, decomposition: TaskDecomposition) -> List[SubTaskResult]:
        """
        调度任务执行
        
        根据依赖关系分层并行执行子任务。
        
        Args:
            decomposition: 任务分解结果
            
        Returns:
            所有子任务的执行结果
        """
        if not decomposition.subtasks:
            return []
        
        # 设置当前任务 ID
        self._current_task_id = decomposition.original_task_id
        
        # 获取或创建执行上下文
        if self._context_manager:
            self._current_context = await self._context_manager.get_context(
                decomposition.original_task_id
            )
        
        # 初始化子任务状态
        for subtask in decomposition.subtasks:
            self._subtask_status[subtask.id] = SubTaskStatus.PENDING
        
        # 构建依赖图
        dependency_graph = self._build_dependency_graph(decomposition.subtasks)
        
        # 计算分层执行顺序
        layers = self._compute_layers(decomposition.subtasks, dependency_graph)
        
        all_results: List[SubTaskResult] = []
        failed_subtasks: Set[str] = set()
        
        # 按层执行
        for layer_idx, layer in enumerate(layers):
            # 过滤掉被阻塞的任务
            executable = []
            for subtask in layer:
                # 检查依赖是否有失败的
                deps = dependency_graph.get(subtask.id, set())
                if deps & failed_subtasks:
                    # 依赖失败，标记为阻塞
                    self._subtask_status[subtask.id] = SubTaskStatus.BLOCKED
                    all_results.append(SubTaskResult(
                        subtask_id=subtask.id,
                        agent_id="",
                        success=False,
                        output=None,
                        error="Blocked due to dependency failure",
                        tool_calls=[],
                        execution_time=0,
                        token_usage={},
                    ))
                else:
                    executable.append(subtask)
            
            if not executable:
                continue
            
            # 为每个子任务创建智能体
            agents = []
            for subtask in executable:
                role = get_role_by_hint(subtask.role_hint)
                try:
                    agent = await self.create_agent(subtask, role)
                    agents.append(agent)
                    self._subtask_status[subtask.id] = SubTaskStatus.RUNNING
                except ResourceLimitError:
                    # 资源不足，加入队列等待
                    self._subtask_status[subtask.id] = SubTaskStatus.QUEUED
                    await self._enqueue_subtask(subtask)
            
            # 并行执行当前层
            if agents:
                print(f"[Scheduler] 执行第 {layer_idx+1} 层，{len(agents)} 个智能体")
                results = await self.execute_parallel_batch(agents)
                
                # 处理结果
                for result in results:
                    self._subtask_results[result.subtask_id] = result
                    if result.success:
                        self._subtask_status[result.subtask_id] = SubTaskStatus.COMPLETED
                        print(f"[Scheduler] 子任务 {result.subtask_id[:8]} 成功")
                    else:
                        self._subtask_status[result.subtask_id] = SubTaskStatus.FAILED
                        failed_subtasks.add(result.subtask_id)
                        print(f"[Scheduler] 子任务 {result.subtask_id[:8]} 失败: {result.error[:100] if result.error else 'Unknown'}")
                    
                    all_results.append(result)
            
            # 处理队列中的任务
            queued_results = await self._process_queue()
            for result in queued_results:
                self._subtask_results[result.subtask_id] = result
                if result.success:
                    self._subtask_status[result.subtask_id] = SubTaskStatus.COMPLETED
                else:
                    self._subtask_status[result.subtask_id] = SubTaskStatus.FAILED
                    failed_subtasks.add(result.subtask_id)
                
                all_results.append(result)
        
        return all_results

    async def _enqueue_subtask(self, subtask: SubTask) -> None:
        """
        将子任务加入优先级队列
        
        Args:
            subtask: 子任务
        """
        async with self._queue_lock:
            # 使用负优先级，因为 heapq 是最小堆
            item = PriorityItem(
                priority=-subtask.priority,
                subtask_id=subtask.id,
                subtask=subtask,
            )
            heapq.heappush(self._priority_queue, item)
            self._subtask_status[subtask.id] = SubTaskStatus.QUEUED
    
    async def _dequeue_subtask(self) -> Optional[SubTask]:
        """
        从优先级队列中取出最高优先级的子任务
        
        Returns:
            子任务，如果队列为空则返回 None
        """
        async with self._queue_lock:
            if not self._priority_queue:
                return None
            item = heapq.heappop(self._priority_queue)
            return item.subtask
    
    async def _process_queue(self) -> List[SubTaskResult]:
        """
        处理队列中的任务
        
        Returns:
            执行结果列表
        """
        results = []
        
        while True:
            # 检查是否有可用槽位
            async with self._active_lock:
                if self._active_count >= self._config.max_concurrent_agents:
                    break
            
            # 取出任务
            subtask = await self._dequeue_subtask()
            if not subtask:
                break
            
            # 创建智能体并执行
            role = get_role_by_hint(subtask.role_hint)
            try:
                agent = await self.create_agent(subtask, role)
                self._subtask_status[subtask.id] = SubTaskStatus.RUNNING
                
                # 执行
                batch_results = await self.execute_parallel_batch([agent])
                results.extend(batch_results)
                
            except ResourceLimitError:
                # 重新入队
                await self._enqueue_subtask(subtask)
                break
        
        return results
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """
        获取队列状态
        
        Returns:
            队列状态信息
        """
        async with self._queue_lock:
            queue_size = len(self._priority_queue)
            
            # 获取队列中的任务优先级分布
            priority_distribution = {}
            for item in self._priority_queue:
                priority = -item.priority  # 恢复原始优先级
                priority_distribution[priority] = priority_distribution.get(priority, 0) + 1
        
        return {
            "queue_size": queue_size,
            "priority_distribution": priority_distribution,
        }
    
    async def reprioritize_subtask(self, subtask_id: str, new_priority: int) -> bool:
        """
        重新设置子任务优先级
        
        Args:
            subtask_id: 子任务 ID
            new_priority: 新优先级
            
        Returns:
            是否成功
        """
        async with self._queue_lock:
            # 查找并更新任务
            for i, item in enumerate(self._priority_queue):
                if item.subtask_id == subtask_id:
                    # 更新优先级
                    item.subtask.priority = new_priority
                    item.priority = -new_priority
                    # 重新堆化
                    heapq.heapify(self._priority_queue)
                    return True
        
        return False

    def _get_dependent_subtasks(
        self, 
        subtask_id: str,
        dependency_graph: Dict[str, Set[str]]
    ) -> Set[str]:
        """
        获取依赖于指定子任务的所有子任务（递归）
        
        Args:
            subtask_id: 子任务 ID
            dependency_graph: 依赖图
            
        Returns:
            依赖于该子任务的所有子任务 ID
        """
        dependents = set()
        
        # 构建反向依赖图
        reverse_graph: Dict[str, Set[str]] = {}
        for st_id, deps in dependency_graph.items():
            for dep_id in deps:
                if dep_id not in reverse_graph:
                    reverse_graph[dep_id] = set()
                reverse_graph[dep_id].add(st_id)
        
        # BFS 查找所有依赖者
        queue = list(reverse_graph.get(subtask_id, set()))
        while queue:
            current = queue.pop(0)
            if current not in dependents:
                dependents.add(current)
                queue.extend(reverse_graph.get(current, set()))
        
        return dependents
    
    async def propagate_failure(
        self, 
        failed_subtask_id: str,
        dependency_graph: Dict[str, Set[str]]
    ) -> Set[str]:
        """
        传播失败状态到依赖链
        
        当一个子任务失败时，所有依赖它的子任务都应该被阻塞。
        
        Args:
            failed_subtask_id: 失败的子任务 ID
            dependency_graph: 依赖图
            
        Returns:
            被阻塞的子任务 ID 集合
        """
        blocked = self._get_dependent_subtasks(failed_subtask_id, dependency_graph)
        
        for subtask_id in blocked:
            current_status = self._subtask_status.get(subtask_id)
            
            # 只阻塞尚未完成的任务
            if current_status in (SubTaskStatus.PENDING, SubTaskStatus.QUEUED):
                self._subtask_status[subtask_id] = SubTaskStatus.BLOCKED
                
                # 如果在队列中，移除
                async with self._queue_lock:
                    self._priority_queue = [
                        item for item in self._priority_queue 
                        if item.subtask_id != subtask_id
                    ]
                    heapq.heapify(self._priority_queue)
        
        return blocked
    
    async def terminate_all_agents(self) -> int:
        """
        终止所有活跃的智能体
        
        Returns:
            终止的智能体数量
        """
        terminated_count = 0
        
        for agent_id in list(self._agents.keys()):
            agent_data = self._agent_data.get(agent_id)
            if agent_data and agent_data.status in (AgentStatus.IDLE, AgentStatus.RUNNING):
                if await self.terminate_agent(agent_id):
                    terminated_count += 1
        
        return terminated_count
    
    async def handle_agent_failure(
        self, 
        agent_id: str, 
        error: str,
        dependency_graph: Optional[Dict[str, Set[str]]] = None
    ) -> Dict[str, Any]:
        """
        处理智能体失败
        
        Args:
            agent_id: 失败的智能体 ID
            error: 错误信息
            dependency_graph: 依赖图（用于错误传播）
            
        Returns:
            处理结果
        """
        result = {
            "agent_id": agent_id,
            "error": error,
            "terminated": False,
            "blocked_subtasks": set(),
        }
        
        # 获取智能体信息
        agent_data = self._agent_data.get(agent_id)
        if not agent_data:
            return result
        
        subtask_id = agent_data.assigned_subtask.id
        
        # 终止智能体
        if await self.terminate_agent(agent_id):
            result["terminated"] = True
        
        # 更新子任务状态
        self._subtask_status[subtask_id] = SubTaskStatus.FAILED
        
        # 记录错误
        if self._context_manager and self._current_task_id:
            await self._context_manager.add_error(
                self._current_task_id,
                {
                    "type": "agent_failure",
                    "agent_id": agent_id,
                    "subtask_id": subtask_id,
                    "error": error,
                    "timestamp": time.time(),
                }
            )
        
        # 传播失败
        if dependency_graph:
            blocked = await self.propagate_failure(subtask_id, dependency_graph)
            result["blocked_subtasks"] = blocked
        
        return result
    
    async def isolate_parallel_failure(
        self, 
        failed_results: List[SubTaskResult],
        all_agents: List[SubAgent]
    ) -> Dict[str, Any]:
        """
        隔离并行执行中的失败
        
        确保单个任务的失败不影响其他独立任务。
        
        Args:
            failed_results: 失败的结果列表
            all_agents: 所有智能体列表
            
        Returns:
            隔离结果
        """
        isolation_result = {
            "failed_count": len(failed_results),
            "isolated_agents": [],
            "continuing_agents": [],
        }
        
        failed_agent_ids = {r.agent_id for r in failed_results}
        
        for agent in all_agents:
            if agent.id in failed_agent_ids:
                # 终止失败的智能体
                await self.terminate_agent(agent.id)
                isolation_result["isolated_agents"].append(agent.id)
            else:
                # 其他智能体继续运行
                isolation_result["continuing_agents"].append(agent.id)
        
        return isolation_result
    
    def get_subtask_status(self, subtask_id: str) -> Optional[SubTaskStatus]:
        """获取子任务状态"""
        return self._subtask_status.get(subtask_id)
    
    def get_all_subtask_statuses(self) -> Dict[str, SubTaskStatus]:
        """获取所有子任务状态"""
        return dict(self._subtask_status)
    
    def get_subtask_result(self, subtask_id: str) -> Optional[SubTaskResult]:
        """获取子任务结果"""
        return self._subtask_results.get(subtask_id)
