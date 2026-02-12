"""Interfaces for Qwen Agent Swarm."""

from .tool_registry import IToolRegistry
from .context_manager import IExecutionContextManager
from .task_decomposer import ITaskDecomposer
from .sub_agent import ISubAgent
from .agent_scheduler import IAgentScheduler, SchedulerConfig
from .result_aggregator import (
    IResultAggregator,
    ConflictResolution,
    ResultConflict,
    AggregationResult,
)
from .main_agent import IMainAgent
from .messaging import IMessageBus
from .task_board import ITaskBoard
from .wave_executor import IWaveExecutor
from .team_lifecycle import ITeamLifecycleManager
from .output_handler import IOutputHandler, ValidationResult

__all__ = [
    "IToolRegistry",
    "IExecutionContextManager",
    "ITaskDecomposer",
    "ISubAgent",
    "IAgentScheduler",
    "SchedulerConfig",
    "IResultAggregator",
    "ConflictResolution",
    "ResultConflict",
    "AggregationResult",
    "IMainAgent",
    "IMessageBus",
    "ITaskBoard",
    "IWaveExecutor",
    "ITeamLifecycleManager",
    "IOutputHandler",
    "ValidationResult",
]
