"""任务监控模块。

本模块包含 TaskMonitor 类，负责任务执行的进度监控、
执行摘要生成和超时管理。

主要职责：
    - 获取执行进度（get_progress）
    - 生成执行摘要（generate_summary）
    - 监控超时（monitor_timeout）
"""

import asyncio
import time
from typing import TYPE_CHECKING, Dict, Any, Optional, List

from ...models.task import Task, TaskDecomposition
from ...models.result import TaskResult
from ...models.enums import TaskStatus

if TYPE_CHECKING:
    from ...interfaces.context_manager import IExecutionContextManager
    from .agent import MainAgentConfig


class TaskNotFoundError(Exception):
    """任务未找到错误"""
    pass


class TaskMonitor:
    """任务监控器。
    
    负责监控任务执行进度、生成执行摘要报告和管理超时。
    
    Attributes:
        _context_manager: 执行上下文管理器
        _config: 主智能体配置
        _tasks: 任务存储引用
        _task_decompositions: 任务分解存储引用
        _task_results: 任务结果存储引用
        _timeout_warning_callbacks: 超时警告回调列表
    """
    
    def __init__(
        self,
        context_manager: "IExecutionContextManager",
        config: "MainAgentConfig",
        # 共享状态引用
        tasks: Optional[Dict[str, Task]] = None,
        task_decompositions: Optional[Dict[str, TaskDecomposition]] = None,
        task_results: Optional[Dict[str, TaskResult]] = None,
        timeout_warning_callbacks: Optional[List[callable]] = None,
    ):
        """
        初始化任务监控器。
        
        Args:
            context_manager: 执行上下文管理器
            config: 主智能体配置
            tasks: 共享的任务存储
            task_decompositions: 共享的任务分解存储
            task_results: 共享的任务结果存储
            timeout_warning_callbacks: 共享的超时警告回调列表
        """
        self._context_manager = context_manager
        self._config = config
        self._tasks = tasks if tasks is not None else {}
        self._task_decompositions = task_decompositions if task_decompositions is not None else {}
        self._task_results = task_results if task_results is not None else {}
        self._timeout_warning_callbacks = timeout_warning_callbacks if timeout_warning_callbacks is not None else []
    
    async def get_progress(self, task_id: str) -> Dict[str, Any]:
        """
        获取执行进度。
        
        Args:
            task_id: 任务ID
            
        Returns:
            包含 progress_percent, current_stage, sub_agent_count, completed_subtasks 等信息
            
        Raises:
            TaskNotFoundError: 如果任务不存在
        """
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task '{task_id}' not found")
        
        # 获取上下文进度
        try:
            context_progress = await self._context_manager.get_progress(task_id)
        except Exception:
            context_progress = {
                "progress_percent": 0,
                "current_stage": "未知",
                "status": task.status.value,
                "sub_agent_count": 0,
                "completed_subtasks": 0,
                "tool_call_count": 0,
                "error_count": 0,
            }
        
        # 获取任务分解信息
        decomposition = self._task_decompositions.get(task_id)
        total_subtasks = len(decomposition.subtasks) if decomposition else 0
        
        # 计算更精确的进度
        progress_percent = context_progress.get("progress_percent", 0)
        
        # 根据状态调整进度
        status = task.status
        if status == TaskStatus.PENDING:
            progress_percent = 0
        elif status == TaskStatus.ANALYZING:
            progress_percent = max(progress_percent, 5)
        elif status == TaskStatus.DECOMPOSING:
            progress_percent = max(progress_percent, 10)
        elif status == TaskStatus.EXECUTING:
            # 执行阶段，进度在 15-85 之间
            if total_subtasks > 0:
                completed = context_progress.get("completed_subtasks", 0)
                exec_progress = int((completed / total_subtasks) * 70)
                progress_percent = 15 + exec_progress
            else:
                progress_percent = max(progress_percent, 15)
        elif status == TaskStatus.AGGREGATING:
            progress_percent = max(progress_percent, 90)
        elif status == TaskStatus.COMPLETED:
            progress_percent = 100
        elif status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
            # 保持当前进度
            pass
        
        # 确保进度在 0-100 范围内
        progress_percent = max(0, min(100, progress_percent))
        
        # 获取阶段描述
        stage_descriptions = {
            TaskStatus.PENDING: "等待开始",
            TaskStatus.ANALYZING: "分析任务复杂度",
            TaskStatus.DECOMPOSING: "分解任务为子任务",
            TaskStatus.EXECUTING: "执行子任务",
            TaskStatus.AGGREGATING: "聚合执行结果",
            TaskStatus.COMPLETED: "任务完成",
            TaskStatus.FAILED: "任务失败",
            TaskStatus.CANCELLED: "任务已取消",
        }
        
        return {
            "task_id": task_id,
            "progress_percent": progress_percent,
            "current_stage": stage_descriptions.get(status, "未知"),
            "status": status.value,
            "sub_agent_count": context_progress.get("sub_agent_count", 0),
            "completed_subtasks": context_progress.get("completed_subtasks", 0),
            "total_subtasks": total_subtasks,
            "tool_call_count": context_progress.get("tool_call_count", 0),
            "error_count": context_progress.get("error_count", 0),
            "complexity_score": task.complexity_score,
        }
    
    async def generate_summary(self, task_id: str) -> Dict[str, Any]:
        """
        生成执行摘要报告。
        
        Args:
            task_id: 任务ID
            
        Returns:
            执行摘要报告
            
        Raises:
            TaskNotFoundError: 如果任务不存在
        """
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task '{task_id}' not found")
        
        # 获取结果
        result = self._task_results.get(task_id)
        decomposition = self._task_decompositions.get(task_id)
        
        # 获取上下文信息
        context = await self._context_manager.get_context(task_id)
        errors = await self._context_manager.get_errors(task_id) if context else []
        
        # 构建摘要
        summary = {
            "task_id": task_id,
            "task_content": task.content[:200] + "..." if len(task.content) > 200 else task.content,
            "task_type": task.metadata.get("task_type", "unknown"),
            "status": task.status.value,
            "complexity_score": task.complexity_score,
            "created_at": task.created_at,
        }
        
        # 添加执行信息
        if result:
            summary["execution"] = {
                "success": result.success,
                "execution_time": result.execution_time,
                "error": result.error,
                "sub_results_count": len(result.sub_results),
                "successful_subtasks": len([r for r in result.sub_results if r.success]),
                "failed_subtasks": len([r for r in result.sub_results if not r.success]),
            }
        
        # 添加分解信息
        if decomposition:
            summary["decomposition"] = {
                "total_subtasks": len(decomposition.subtasks),
                "execution_layers": len(decomposition.execution_order),
                "estimated_time": decomposition.total_estimated_time,
            }
        
        # 添加错误信息
        if errors:
            summary["errors"] = errors[:10]  # 最多10个错误
            summary["total_errors"] = len(errors)
        
        # 添加资源使用信息
        if context:
            summary["resource_usage"] = {
                "sub_agents_created": len(context.sub_agents),
                "tool_calls": context.tool_call_count,
            }
        
        return summary
    
    async def monitor_timeout(self, task_id: str, start_time: float) -> None:
        """
        监控任务执行超时。
        
        Args:
            task_id: 任务ID
            start_time: 开始时间
        """
        warning_time = self._config.execution_timeout * self._config.timeout_warning_threshold
        
        try:
            # 等待到警告时间
            await asyncio.sleep(warning_time)
            
            # 发出超时警告
            elapsed = time.time() - start_time
            remaining = self._config.execution_timeout - elapsed
            
            # 调用警告回调
            for callback in self._timeout_warning_callbacks:
                try:
                    callback(task_id, elapsed, remaining)
                except Exception:
                    pass
            
            # 记录警告
            await self._context_manager.add_error(task_id, {
                "type": "timeout_warning",
                "elapsed": elapsed,
                "remaining": remaining,
                "timestamp": time.time(),
            })
            
        except asyncio.CancelledError:
            # 任务完成，取消监控
            pass
    
    def add_timeout_warning_callback(self, callback: callable) -> None:
        """
        添加超时警告回调。
        
        Args:
            callback: 回调函数，接收 (task_id, elapsed, remaining) 参数
        """
        self._timeout_warning_callbacks.append(callback)
