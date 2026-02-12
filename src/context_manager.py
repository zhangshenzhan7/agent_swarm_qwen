"""Execution Context Manager implementation."""

import asyncio
import time
from typing import Dict, Any, Optional

from .interfaces.context_manager import IExecutionContextManager
from .models.task import Task
from .models.enums import TaskStatus
from .models.agent import SubAgent
from .models.result import SubTaskResult
from .models.context import ExecutionContext, ThreadSafeExecutionContext


class ContextNotFoundError(Exception):
    """上下文未找到异常"""
    pass


class ExecutionContextManager(IExecutionContextManager):
    """执行上下文管理器实现"""
    
    def __init__(self):
        self._contexts: Dict[str, ThreadSafeExecutionContext] = {}
        self._lock = asyncio.Lock()
    
    async def create_context(self, task: Task) -> ExecutionContext:
        """创建执行上下文"""
        context = ExecutionContext(
            task_id=task.id,
            start_time=time.time(),
            status=TaskStatus.PENDING,
        )
        
        async with self._lock:
            self._contexts[task.id] = ThreadSafeExecutionContext(context)
        
        return context
    
    async def get_context(self, task_id: str) -> Optional[ExecutionContext]:
        """获取执行上下文"""
        async with self._lock:
            wrapper = self._contexts.get(task_id)
            if wrapper:
                return wrapper.get_raw_context()
            return None
    
    def _get_wrapper(self, task_id: str) -> ThreadSafeExecutionContext:
        """获取线程安全的上下文包装器"""
        wrapper = self._contexts.get(task_id)
        if wrapper is None:
            raise ContextNotFoundError(f"Context for task '{task_id}' not found")
        return wrapper
    
    async def update_status(self, task_id: str, status: TaskStatus) -> None:
        """更新任务状态"""
        wrapper = self._get_wrapper(task_id)
        wrapper.status = status
    
    async def register_agent(self, task_id: str, agent: SubAgent) -> None:
        """注册子智能体"""
        wrapper = self._get_wrapper(task_id)
        wrapper.register_agent(agent)
    
    async def record_result(self, task_id: str, result: SubTaskResult) -> None:
        """记录子任务结果"""
        wrapper = self._get_wrapper(task_id)
        wrapper.record_result(result)
    
    async def increment_tool_calls(self, task_id: str, count: int = 1) -> int:
        """增加工具调用计数"""
        wrapper = self._get_wrapper(task_id)
        return wrapper.increment_tool_calls(count)
    
    async def set_shared_data(self, task_id: str, key: str, value: Any) -> None:
        """设置共享数据"""
        wrapper = self._get_wrapper(task_id)
        wrapper.set_shared_data(key, value)
    
    async def get_shared_data(self, task_id: str, key: str) -> Optional[Any]:
        """获取共享数据"""
        wrapper = self._get_wrapper(task_id)
        return wrapper.get_shared_data(key)
    
    async def add_error(self, task_id: str, error: Dict[str, Any]) -> None:
        """添加错误记录"""
        wrapper = self._get_wrapper(task_id)
        wrapper.add_error(error)
    
    async def get_errors(self, task_id: str) -> list:
        """获取所有错误"""
        wrapper = self._get_wrapper(task_id)
        return wrapper.get_errors()
    
    async def cleanup_context(self, task_id: str) -> None:
        """清理执行上下文"""
        async with self._lock:
            if task_id in self._contexts:
                del self._contexts[task_id]
    
    async def get_all_contexts(self) -> Dict[str, ExecutionContext]:
        """获取所有执行上下文"""
        async with self._lock:
            return {
                task_id: wrapper.get_raw_context()
                for task_id, wrapper in self._contexts.items()
            }
    
    async def get_progress(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务执行进度
        
        Returns:
            包含 progress_percent, current_stage, sub_agent_count, completed_subtasks 等信息
        """
        wrapper = self._get_wrapper(task_id)
        context = wrapper.get_raw_context()
        
        total_agents = len(context.sub_agents)
        completed_results = len(context.subtask_results)
        
        # 计算进度百分比
        if total_agents == 0:
            progress_percent = 0
        else:
            progress_percent = int((completed_results / total_agents) * 100)
        
        # 确定当前阶段
        status = context.status
        stage_map = {
            TaskStatus.PENDING: "等待开始",
            TaskStatus.ANALYZING: "分析任务",
            TaskStatus.DECOMPOSING: "分解任务",
            TaskStatus.EXECUTING: "执行中",
            TaskStatus.AGGREGATING: "聚合结果",
            TaskStatus.COMPLETED: "已完成",
            TaskStatus.FAILED: "执行失败",
            TaskStatus.CANCELLED: "已取消",
        }
        
        return {
            "progress_percent": progress_percent,
            "current_stage": stage_map.get(status, "未知"),
            "status": status.value,
            "sub_agent_count": total_agents,
            "completed_subtasks": completed_results,
            "tool_call_count": context.tool_call_count,
            "error_count": len(context.errors),
        }
