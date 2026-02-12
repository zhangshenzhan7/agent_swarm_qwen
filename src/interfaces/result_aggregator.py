"""Result Aggregator interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional

from ..models.result import SubTaskResult
from ..models.task import TaskDecomposition
from ..models.agent import SubAgent
from ..models.enums import OutputType


class ConflictResolution(Enum):
    """冲突解决策略"""
    FIRST_WINS = "first_wins"
    LAST_WINS = "last_wins"
    MAJORITY_VOTE = "majority_vote"
    MANUAL = "manual"


@dataclass
class ResultConflict:
    """结果冲突"""
    subtask_ids: List[str]
    conflict_type: str
    description: str
    resolution: Optional[str] = None


@dataclass
class AggregationResult:
    """聚合结果"""
    task_id: str
    success: bool
    final_output: Any
    sub_results: List[SubTaskResult]
    conflicts: List[ResultConflict] = field(default_factory=list)
    missing_subtasks: List[str] = field(default_factory=list)
    aggregation_time: float = 0.0
    artifacts: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "task_id": self.task_id,
            "success": self.success,
            "final_output": self.final_output,
            "sub_results": [sr.to_dict() for sr in self.sub_results],
            "conflicts": [
                {
                    "subtask_ids": c.subtask_ids,
                    "conflict_type": c.conflict_type,
                    "description": c.description,
                    "resolution": c.resolution,
                }
                for c in self.conflicts
            ],
            "missing_subtasks": self.missing_subtasks,
            "aggregation_time": self.aggregation_time,
            "artifacts": self.artifacts,
        }


class IResultAggregator(ABC):
    """结果聚合器接口"""
    
    @abstractmethod
    async def collect_results(self, agents: List[SubAgent]) -> List[SubTaskResult]:
        """
        收集所有子智能体的结果
        
        Args:
            agents: 子智能体列表
            
        Returns:
            子任务结果列表
        """
        pass
    
    @abstractmethod
    async def validate_results(self, results: List[SubTaskResult]) -> List[SubTaskResult]:
        """
        验证结果的格式和完整性
        
        Args:
            results: 待验证的结果列表
            
        Returns:
            验证后的结果列表（可能包含验证状态）
        """
        pass
    
    @abstractmethod
    async def detect_conflicts(self, results: List[SubTaskResult]) -> List[ResultConflict]:
        """
        检测结果之间的冲突
        
        Args:
            results: 结果列表
            
        Returns:
            检测到的冲突列表
        """
        pass
    
    @abstractmethod
    async def aggregate(
        self, 
        results: List[SubTaskResult],
        decomposition: TaskDecomposition,
        conflict_resolution: ConflictResolution = ConflictResolution.MAJORITY_VOTE,
        output_type: OutputType = OutputType.REPORT
    ) -> AggregationResult:
        """
        聚合所有结果为最终输出
        
        Args:
            results: 子任务结果列表
            decomposition: 原始任务分解
            conflict_resolution: 冲突解决策略
            output_type: 目标输出类型，默认为 REPORT 以保持向后兼容
            
        Returns:
            聚合结果
        """
        pass
