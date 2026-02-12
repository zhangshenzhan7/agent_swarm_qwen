"""Task-related data models."""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

from .enums import TaskStatus


@dataclass
class Task:
    """任务数据结构"""
    id: str
    content: str
    status: TaskStatus
    complexity_score: float
    created_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status.value,
            "complexity_score": self.complexity_score,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """从字典反序列化"""
        return cls(
            id=data["id"],
            content=data["content"],
            status=TaskStatus(data["status"]),
            complexity_score=data["complexity_score"],
            created_at=data["created_at"],
            metadata=data.get("metadata", {}),
        )


@dataclass
class SubTask:
    """子任务数据结构"""
    id: str
    parent_task_id: str
    content: str
    role_hint: str  # 建议的执行角色
    dependencies: Set[str] = field(default_factory=set)  # 依赖的子任务ID
    priority: int = 0
    estimated_complexity: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "id": self.id,
            "parent_task_id": self.parent_task_id,
            "content": self.content,
            "role_hint": self.role_hint,
            "dependencies": list(self.dependencies),
            "priority": self.priority,
            "estimated_complexity": self.estimated_complexity,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubTask":
        """从字典反序列化"""
        return cls(
            id=data["id"],
            parent_task_id=data["parent_task_id"],
            content=data["content"],
            role_hint=data["role_hint"],
            dependencies=set(data.get("dependencies", [])),
            priority=data.get("priority", 0),
            estimated_complexity=data.get("estimated_complexity", 1.0),
        )


@dataclass
class TaskDecomposition:
    """任务分解结果"""
    original_task_id: str
    subtasks: List[SubTask]
    execution_order: List[List[str]]  # 分层执行顺序，每层可并行
    total_estimated_time: float
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "original_task_id": self.original_task_id,
            "subtasks": [st.to_dict() for st in self.subtasks],
            "execution_order": self.execution_order,
            "total_estimated_time": self.total_estimated_time,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskDecomposition":
        """从字典反序列化"""
        return cls(
            original_task_id=data["original_task_id"],
            subtasks=[SubTask.from_dict(st) for st in data["subtasks"]],
            execution_order=data["execution_order"],
            total_estimated_time=data["total_estimated_time"],
        )
