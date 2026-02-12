"""Sub Agent interface."""

from abc import ABC, abstractmethod
from typing import Dict, Any

from ..models.enums import AgentStatus
from ..models.task import SubTask
from ..models.result import SubTaskResult
from ..models.context import ExecutionContext


class ISubAgent(ABC):
    """子智能体接口"""
    
    @abstractmethod
    async def execute(self, subtask: SubTask, context: ExecutionContext) -> SubTaskResult:
        """
        执行子任务
        
        Args:
            subtask: 要执行的子任务
            context: 执行上下文
            
        Returns:
            子任务执行结果
        """
        pass
    
    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        调用工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        pass
    
    @abstractmethod
    def get_status(self) -> AgentStatus:
        """获取当前状态"""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """停止执行"""
        pass
