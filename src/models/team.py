"""Team-related data models for Agent Team architecture.

Defines the core data structures for team lifecycle management,
task board operations, execution planning, and wave execution,
including serialization support via to_dict/from_dict methods.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from .task import SubTask


class TeamState(Enum):
    """团队状态枚举"""
    CREATING = "creating"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    DISBANDED = "disbanded"


@dataclass
class TeamConfig:
    """团队配置

    Attributes:
        max_agents: 最大智能体数量
        agent_timeout: 智能体超时时间（秒）
        claim_timeout: 认领超时时间（秒）
        enable_p2p_messaging: 是否启用 P2P 消息通信
        enable_self_claiming: 是否启用自认领机制
    """
    max_agents: int = 20
    agent_timeout: float = 300.0
    claim_timeout: float = 60.0
    enable_p2p_messaging: bool = True
    enable_self_claiming: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "max_agents": self.max_agents,
            "agent_timeout": self.agent_timeout,
            "claim_timeout": self.claim_timeout,
            "enable_p2p_messaging": self.enable_p2p_messaging,
            "enable_self_claiming": self.enable_self_claiming,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TeamConfig":
        """从字典反序列化"""
        return cls(
            max_agents=data.get("max_agents", 20),
            agent_timeout=data.get("agent_timeout", 300.0),
            claim_timeout=data.get("claim_timeout", 60.0),
            enable_p2p_messaging=data.get("enable_p2p_messaging", True),
            enable_self_claiming=data.get("enable_self_claiming", True),
        )


@dataclass
class Team:
    """团队数据结构

    Attributes:
        id: 团队唯一 ID
        task_id: 关联的任务 ID
        state: 团队状态
        config: 团队配置
        members: 成员映射 (agent_id -> role)
        created_at: 创建时间戳
        completed_at: 完成时间戳
    """
    id: str
    task_id: str
    state: TeamState
    config: TeamConfig
    members: Dict[str, str] = field(default_factory=dict)
    created_at: float = 0.0
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "state": self.state.value,
            "config": self.config.to_dict(),
            "members": self.members,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Team":
        """从字典反序列化"""
        return cls(
            id=data["id"],
            task_id=data["task_id"],
            state=TeamState(data["state"]),
            config=TeamConfig.from_dict(data["config"]),
            members=data.get("members", {}),
            created_at=data.get("created_at", 0.0),
            completed_at=data.get("completed_at"),
        )


@dataclass
class DisbandResult:
    """团队解散结果

    Attributes:
        team_id: 团队 ID
        success: 是否成功解散
        terminated_agents: 正常终止的智能体数量
        force_terminated_agents: 强制终止的智能体数量
        errors: 解散过程中的错误列表
    """
    team_id: str
    success: bool
    terminated_agents: int
    force_terminated_agents: int
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "team_id": self.team_id,
            "success": self.success,
            "terminated_agents": self.terminated_agents,
            "force_terminated_agents": self.force_terminated_agents,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DisbandResult":
        """从字典反序列化"""
        return cls(
            team_id=data["team_id"],
            success=data["success"],
            terminated_agents=data["terminated_agents"],
            force_terminated_agents=data["force_terminated_agents"],
            errors=data.get("errors", []),
        )


class TaskBoardStatus(Enum):
    """任务板任务状态枚举"""
    BLOCKED = "blocked"
    PENDING = "pending"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskBoardEntry:
    """任务板条目

    Attributes:
        task_id: 任务 ID
        subtask: 关联的子任务
        status: 任务板状态
        claimed_by: 认领者智能体 ID
        claimed_at: 认领时间
        started_at: 开始执行时间
        completed_at: 完成时间
        result: 执行结果
        dependencies: 依赖的任务 ID 集合
        priority: 优先级
        role_hint: 角色提示
    """
    task_id: str
    subtask: SubTask
    status: TaskBoardStatus
    claimed_by: Optional[str] = None
    claimed_at: Optional[float] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Any] = None
    dependencies: Set[str] = field(default_factory=set)
    priority: int = 0
    role_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "task_id": self.task_id,
            "subtask": self.subtask.to_dict(),
            "status": self.status.value,
            "claimed_by": self.claimed_by,
            "claimed_at": self.claimed_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "dependencies": list(self.dependencies),
            "priority": self.priority,
            "role_hint": self.role_hint,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskBoardEntry":
        """从字典反序列化"""
        return cls(
            task_id=data["task_id"],
            subtask=SubTask.from_dict(data["subtask"]),
            status=TaskBoardStatus(data["status"]),
            claimed_by=data.get("claimed_by"),
            claimed_at=data.get("claimed_at"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            result=data.get("result"),
            dependencies=set(data.get("dependencies", [])),
            priority=data.get("priority", 0),
            role_hint=data.get("role_hint", ""),
        )


@dataclass
class ClaimResult:
    """任务认领结果

    Attributes:
        success: 是否成功认领
        task_id: 任务 ID
        error: 错误信息（认领失败时）
    """
    success: bool
    task_id: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "success": self.success,
            "task_id": self.task_id,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClaimResult":
        """从字典反序列化"""
        return cls(
            success=data["success"],
            task_id=data["task_id"],
            error=data.get("error"),
        )


class PlanStatus(Enum):
    """执行计划状态枚举"""
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    REVISED = "revised"


@dataclass
class ExecutionPlan:
    """执行计划

    Attributes:
        task_id: 任务 ID
        subtasks: 子任务列表
        dependency_graph: 依赖关系图 (task_id -> 依赖的 task_id 集合)
        agent_assignments: 智能体分配 (subtask_id -> role)
        estimated_token_usage: 预估 token 用量
        estimated_execution_time: 预估执行时间（秒）
        wave_preview: 预览波次分组
        created_at: 创建时间戳
        status: 计划状态
    """
    task_id: str
    subtasks: List[SubTask]
    dependency_graph: Dict[str, Set[str]]
    agent_assignments: Dict[str, str]
    estimated_token_usage: int
    estimated_execution_time: float
    wave_preview: List[List[str]]
    created_at: float
    status: PlanStatus = PlanStatus.DRAFT

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "task_id": self.task_id,
            "subtasks": [st.to_dict() for st in self.subtasks],
            "dependency_graph": {
                k: list(v) for k, v in self.dependency_graph.items()
            },
            "agent_assignments": self.agent_assignments,
            "estimated_token_usage": self.estimated_token_usage,
            "estimated_execution_time": self.estimated_execution_time,
            "wave_preview": self.wave_preview,
            "created_at": self.created_at,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionPlan":
        """从字典反序列化"""
        return cls(
            task_id=data["task_id"],
            subtasks=[SubTask.from_dict(st) for st in data["subtasks"]],
            dependency_graph={
                k: set(v) for k, v in data["dependency_graph"].items()
            },
            agent_assignments=data["agent_assignments"],
            estimated_token_usage=data["estimated_token_usage"],
            estimated_execution_time=data["estimated_execution_time"],
            wave_preview=data["wave_preview"],
            created_at=data["created_at"],
            status=PlanStatus(data.get("status", "draft")),
        )


@dataclass
class WaveStats:
    """波次执行统计

    Attributes:
        wave_number: 波次编号
        task_count: 任务数量
        parallelism: 并行度
        start_time: 开始时间
        end_time: 结束时间
        completed_tasks: 完成的任务数
        failed_tasks: 失败的任务数
    """
    wave_number: int
    task_count: int
    parallelism: int
    start_time: float
    end_time: float
    completed_tasks: int
    failed_tasks: int

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "wave_number": self.wave_number,
            "task_count": self.task_count,
            "parallelism": self.parallelism,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WaveStats":
        """从字典反序列化"""
        return cls(
            wave_number=data["wave_number"],
            task_count=data["task_count"],
            parallelism=data["parallelism"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            completed_tasks=data["completed_tasks"],
            failed_tasks=data["failed_tasks"],
        )


@dataclass
class WaveExecutionResult:
    """波次执行结果

    Attributes:
        total_waves: 总波次数
        total_tasks: 总任务数
        completed_tasks: 完成的任务数
        failed_tasks: 失败的任务数
        blocked_tasks: 被阻塞的任务数
        wave_stats: 各波次统计列表
        total_execution_time: 总执行时间（秒）
    """
    total_waves: int
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    blocked_tasks: int
    wave_stats: List[WaveStats]
    total_execution_time: float

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "total_waves": self.total_waves,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "blocked_tasks": self.blocked_tasks,
            "wave_stats": [ws.to_dict() for ws in self.wave_stats],
            "total_execution_time": self.total_execution_time,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WaveExecutionResult":
        """从字典反序列化"""
        return cls(
            total_waves=data["total_waves"],
            total_tasks=data["total_tasks"],
            completed_tasks=data["completed_tasks"],
            failed_tasks=data["failed_tasks"],
            blocked_tasks=data["blocked_tasks"],
            wave_stats=[WaveStats.from_dict(ws) for ws in data["wave_stats"]],
            total_execution_time=data["total_execution_time"],
        )
