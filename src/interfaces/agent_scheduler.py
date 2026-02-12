"""Agent Scheduler interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from ..models.task import SubTask, TaskDecomposition
from ..models.agent import SubAgent, AgentRole
from ..models.result import SubTaskResult


@dataclass
class SchedulerConfig:
    """调度器配置"""
    max_concurrent_agents: int = 100
    max_tool_calls: int = 1500
    agent_timeout: float = 300.0  # 秒
    retry_attempts: int = 3


class IAgentScheduler(ABC):
    """智能体调度器接口"""
    
    @abstractmethod
    async def create_agent(self, subtask: SubTask, role: AgentRole) -> SubAgent:
        """
        创建子智能体
        
        Args:
            subtask: 要执行的子任务
            role: 智能体角色
            
        Returns:
            创建的子智能体
        """
        pass
    
    @abstractmethod
    async def schedule_execution(self, decomposition: TaskDecomposition) -> List[SubTaskResult]:
        """
        调度任务执行
        
        Args:
            decomposition: 任务分解结果
            
        Returns:
            所有子任务的执行结果
        """
        pass
    
    @abstractmethod
    async def execute_parallel_batch(self, agents: List[SubAgent]) -> List[SubTaskResult]:
        """
        并行执行一批子智能体
        
        Args:
            agents: 要并行执行的子智能体列表
            
        Returns:
            执行结果列表
        """
        pass
    
    @abstractmethod
    async def terminate_agent(self, agent_id: str) -> bool:
        """
        终止指定子智能体
        
        Args:
            agent_id: 智能体ID
            
        Returns:
            是否成功终止
        """
        pass
    
    @abstractmethod
    async def get_active_agents(self) -> List[SubAgent]:
        """
        获取所有活跃的子智能体
        
        Returns:
            活跃智能体列表
        """
        pass
    
    @abstractmethod
    async def get_resource_usage(self) -> Dict[str, Any]:
        """
        获取资源使用情况
        
        Returns:
            包含 active_agents, total_tool_calls, memory_usage 等信息
        """
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """
        清理所有资源
        
        终止所有智能体并释放资源
        """
        pass
