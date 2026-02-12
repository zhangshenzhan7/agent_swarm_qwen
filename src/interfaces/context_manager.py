"""Execution Context Manager interface."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from ..models.task import Task
from ..models.enums import TaskStatus
from ..models.agent import SubAgent
from ..models.result import SubTaskResult
from ..models.context import ExecutionContext


class IExecutionContextManager(ABC):
    """执行上下文管理器接口"""
    
    @abstractmethod
    async def create_context(self, task: Task) -> ExecutionContext:
        """
        创建执行上下文
        
        Args:
            task: 任务对象
            
        Returns:
            创建的执行上下文
        """
        pass
    
    @abstractmethod
    async def get_context(self, task_id: str) -> Optional[ExecutionContext]:
        """
        获取执行上下文
        
        Args:
            task_id: 任务ID
            
        Returns:
            执行上下文，如果不存在则返回 None
        """
        pass
    
    @abstractmethod
    async def update_status(self, task_id: str, status: TaskStatus) -> None:
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态
        """
        pass
    
    @abstractmethod
    async def register_agent(self, task_id: str, agent: SubAgent) -> None:
        """
        注册子智能体
        
        Args:
            task_id: 任务ID
            agent: 子智能体
        """
        pass
    
    @abstractmethod
    async def record_result(self, task_id: str, result: SubTaskResult) -> None:
        """
        记录子任务结果
        
        Args:
            task_id: 任务ID
            result: 子任务结果
        """
        pass
    
    @abstractmethod
    async def increment_tool_calls(self, task_id: str, count: int = 1) -> int:
        """
        增加工具调用计数
        
        Args:
            task_id: 任务ID
            count: 增加的数量
            
        Returns:
            当前总调用次数
        """
        pass
    
    @abstractmethod
    async def set_shared_data(self, task_id: str, key: str, value: Any) -> None:
        """
        设置共享数据
        
        Args:
            task_id: 任务ID
            key: 数据键
            value: 数据值
        """
        pass
    
    @abstractmethod
    async def get_shared_data(self, task_id: str, key: str) -> Optional[Any]:
        """
        获取共享数据
        
        Args:
            task_id: 任务ID
            key: 数据键
            
        Returns:
            数据值，如果不存在则返回 None
        """
        pass
    
    @abstractmethod
    async def cleanup_context(self, task_id: str) -> None:
        """
        清理执行上下文
        
        Args:
            task_id: 任务ID
        """
        pass
