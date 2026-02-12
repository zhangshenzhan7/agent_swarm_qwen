"""Main Agent interface."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from ..models.task import Task
from ..models.result import TaskResult
from ..models.enums import TaskStatus


class IMainAgent(ABC):
    """主智能体接口"""
    
    @abstractmethod
    async def submit_task(self, content: str, metadata: Optional[Dict] = None) -> Task:
        """
        提交任务
        
        Args:
            content: 任务内容描述
            metadata: 可选的任务元数据
            
        Returns:
            创建的任务对象
            
        Raises:
            TaskParsingError: 如果任务格式无效或无法解析
        """
        pass
    
    @abstractmethod
    async def execute_task(self, task: Task) -> TaskResult:
        """
        执行任务（包含分解、调度、聚合全流程）
        
        Args:
            task: 要执行的任务
            
        Returns:
            任务执行结果
        """
        pass
    
    @abstractmethod
    async def get_task_status(self, task_id: str) -> TaskStatus:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务状态
            
        Raises:
            TaskNotFoundError: 如果任务不存在
        """
        pass
    
    @abstractmethod
    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务执行
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功取消
        """
        pass
    
    @abstractmethod
    async def get_execution_progress(self, task_id: str) -> Dict[str, Any]:
        """
        获取执行进度
        
        Args:
            task_id: 任务ID
            
        Returns:
            包含 progress_percent, current_stage, sub_agent_count, completed_subtasks 等信息
            
        Raises:
            TaskNotFoundError: 如果任务不存在
        """
        pass
