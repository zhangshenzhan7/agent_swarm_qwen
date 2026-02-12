"""Data models for Qwen Agent Swarm."""

from .enums import TaskStatus, AgentStatus, OutputType
from .output import OutputMetadata, OutputArtifact
from .tool import ToolDefinition, ToolCallRecord
from .task import Task, SubTask, TaskDecomposition
from .result import SubTaskResult, TaskResult
from .agent import AgentRole, SubAgent, PREDEFINED_ROLES, get_role_by_hint, get_model_config_for_role, ROLE_MODEL_CONFIG
from .context import ExecutionContext, ThreadSafeExecutionContext
from .agent_registry import (
    AgentRegistry,
    RegisteredAgent,
    ModelConfig,
    AgentType,
    AgentCapability,
    get_registry,
    create_agent_from_template,
    MULTIMODAL_AGENT_TEMPLATES,
)
from .message import MessageType, MessageDeliveryStatus, Message, MessageDeliveryResult
from .team import (
    TeamState,
    TeamConfig,
    Team,
    DisbandResult,
    TaskBoardStatus,
    TaskBoardEntry,
    ClaimResult,
    PlanStatus,
    ExecutionPlan,
    WaveStats,
    WaveExecutionResult,
)

__all__ = [
    # Enums
    "TaskStatus",
    "AgentStatus",
    "OutputType",
    # Output models
    "OutputMetadata",
    "OutputArtifact",
    # Tool models
    "ToolDefinition",
    "ToolCallRecord",
    # Task models
    "Task",
    "SubTask",
    "TaskDecomposition",
    # Result models
    "SubTaskResult",
    "TaskResult",
    # Agent models
    "AgentRole",
    "SubAgent",
    "PREDEFINED_ROLES",
    "get_role_by_hint",
    "get_model_config_for_role",
    "ROLE_MODEL_CONFIG",
    # Context models
    "ExecutionContext",
    "ThreadSafeExecutionContext",
    # Agent Registry
    "AgentRegistry",
    "RegisteredAgent",
    "ModelConfig",
    "AgentType",
    "AgentCapability",
    "get_registry",
    "create_agent_from_template",
    "MULTIMODAL_AGENT_TEMPLATES",
    # Message models
    "MessageType",
    "MessageDeliveryStatus",
    "Message",
    "MessageDeliveryResult",
    # Team models
    "TeamState",
    "TeamConfig",
    "Team",
    "DisbandResult",
    "TaskBoardStatus",
    "TaskBoardEntry",
    "ClaimResult",
    "PlanStatus",
    "ExecutionPlan",
    "WaveStats",
    "WaveExecutionResult",
]
