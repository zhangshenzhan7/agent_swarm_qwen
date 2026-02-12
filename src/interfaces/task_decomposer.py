"""Task Decomposer interface."""

from abc import ABC, abstractmethod
from typing import List

from ..models.task import Task, SubTask, TaskDecomposition


class ITaskDecomposer(ABC):
    """任务分解器接口"""
    
    @abstractmethod
    async def analyze_complexity(self, task: Task) -> float:
        """
        分析任务复杂度
        
        Args:
            task: 待分析的任务
            
        Returns:
            复杂度评分 (0.0 - 10.0)
        """
        pass
    
    @abstractmethod
    async def decompose(self, task: Task) -> TaskDecomposition:
        """
        分解任务为子任务
        
        Args:
            task: 待分解的任务
            
        Returns:
            任务分解结果，包含子任务列表和执行顺序
        """
        pass
    
    @abstractmethod
    async def identify_dependencies(self, subtasks: List[SubTask]) -> List[SubTask]:
        """
        识别子任务之间的依赖关系
        
        Args:
            subtasks: 子任务列表
            
        Returns:
            更新了依赖关系的子任务列表
        """
        pass
    
    @abstractmethod
    async def suggest_roles(self, subtasks: List[SubTask]) -> List[SubTask]:
        """
        为子任务建议执行角色
        
        Args:
            subtasks: 子任务列表
            
        Returns:
            更新了角色建议的子任务列表
        """
        pass
