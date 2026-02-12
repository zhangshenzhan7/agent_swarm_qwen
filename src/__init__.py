"""
Qwen Agent Swarm - 基于 Qwen 系列模型的智能体集群系统

This package provides a multi-agent system based on Qwen models that can:
- Dynamically create and schedule up to 100 concurrent sub-agents
- Support up to 1500 tool calls per task
- Intelligently decompose complex tasks into parallel/serial subtasks
- Aggregate results from multiple agents

Core Components:
- MainAgent: Task coordination and orchestration
- TaskDecomposer: Task analysis and decomposition
- AgentScheduler: Sub-agent creation and scheduling
- SubAgent: Task execution workers
- ResultAggregator: Result collection and integration
- ToolRegistry: Tool management and invocation
- ExecutionContext: Runtime state management
- QwenClient: Qwen model integration

Usage:
    from src import AgentSwarm
    
    swarm = AgentSwarm()
    result = await swarm.execute("Your complex task here")
"""

__version__ = "0.1.0"

# Core models
from .models import (
    # Enums
    TaskStatus,
    AgentStatus,
    # Tool models
    ToolDefinition,
    ToolCallRecord,
    # Task models
    Task,
    SubTask,
    TaskDecomposition,
    # Result models
    SubTaskResult,
    TaskResult,
    # Agent models
    AgentRole,
    SubAgent,
    PREDEFINED_ROLES,
    get_role_by_hint,
    # Context models
    ExecutionContext,
    ThreadSafeExecutionContext,
)

# Interfaces
from .interfaces import (
    IToolRegistry, 
    IExecutionContextManager, 
    ISubAgent,
    IAgentScheduler,
    SchedulerConfig,
    IResultAggregator,
    ConflictResolution,
    ResultConflict,
    AggregationResult,
    IMainAgent,
)

# Implementations
from .tool_registry import ToolRegistry, ToolNotFoundError, ToolTimeoutError
from .context_manager import ExecutionContextManager, ContextNotFoundError
from .task_decomposer import TaskDecomposer
from .sub_agent import (
    SubAgentImpl,
    SubAgentError,
    SubAgentExecutionError,
    InvalidStateTransitionError,
    VALID_STATE_TRANSITIONS,
)
from .agent_scheduler import (
    AgentScheduler,
    SchedulerError,
    ResourceLimitError,
    AgentNotFoundError,
    DependencyError,
    SubTaskStatus,
)
from .result_aggregator import (
    ResultAggregatorImpl,
    ResultAggregatorError,
    ValidationError,
)
from .main_agent import (
    MainAgent,
    MainAgentConfig,
    MainAgentError,
    TaskParsingError,
    TaskNotFoundError,
    TaskExecutionError,
)
from .long_text_processor import (
    LongTextProcessor,
    LongTextConfig,
    ChunkingStrategy,
    TextChunk,
    ChunkResult,
    MergedResult,
    MODEL_CONTEXT_LIMITS,
)
from .agent_swarm import AgentSwarm, AgentSwarmConfig

# Supervisor (AI 主管)
from .supervisor import (
    Supervisor,
    SupervisorConfig,
    TaskPlan,
    PlanningPhase,
    StreamCallback,
    ExecutionStep,
    ExecutionStepStatus,
    ExecutionFlow,
)

# Quality Assurance (质量保障)
from .quality_assurance import (
    QualityAssurance,
    QualityLevel,
    QualityReport,
    ConflictType,
    ConflictReport,
    ReflectionResult,
)

# Memory Manager (记忆管理)
from .memory_manager import (
    MemoryManager,
    MemoryType,
    MemoryItem,
)

# Adaptive Orchestrator (自适应编排器)
from .adaptive_orchestrator import (
    AdaptiveOrchestrator,
    OrchestrationConfig,
    TaskNode,
    TaskPriority,
    OrchestrationSignal,
)

# Built-in tools
from .tools import (
    CodeExecutionTool,
    create_code_execution_tool,
    FileOperationsTool,
    create_file_operations_tool,
)

__all__ = [
    # Version
    "__version__",
    # Enums
    "TaskStatus",
    "AgentStatus",
    "SubTaskStatus",
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
    # Context models
    "ExecutionContext",
    "ThreadSafeExecutionContext",
    # Interfaces
    "IToolRegistry",
    "IExecutionContextManager",
    "ISubAgent",
    "IAgentScheduler",
    "SchedulerConfig",
    "IResultAggregator",
    "ConflictResolution",
    "ResultConflict",
    "AggregationResult",
    "IMainAgent",
    # Implementations
    "ToolRegistry",
    "ExecutionContextManager",
    "TaskDecomposer",
    "SubAgentImpl",
    "AgentScheduler",
    "ResultAggregatorImpl",
    "MainAgent",
    "MainAgentConfig",
    # Exceptions
    "ToolNotFoundError",
    "ToolTimeoutError",
    "ContextNotFoundError",
    "SubAgentError",
    "SubAgentExecutionError",
    "InvalidStateTransitionError",
    "SchedulerError",
    "ResourceLimitError",
    "AgentNotFoundError",
    "DependencyError",
    "ResultAggregatorError",
    "ValidationError",
    "MainAgentError",
    "TaskParsingError",
    "TaskNotFoundError",
    "TaskExecutionError",
    # Long text processing
    "LongTextProcessor",
    "LongTextConfig",
    "ChunkingStrategy",
    "TextChunk",
    "ChunkResult",
    "MergedResult",
    "MODEL_CONTEXT_LIMITS",
    # AgentSwarm
    "AgentSwarm",
    "AgentSwarmConfig",
    # Supervisor
    "Supervisor",
    "SupervisorConfig",
    "TaskPlan",
    "PlanningPhase",
    "StreamCallback",
    "ExecutionStep",
    "ExecutionStepStatus",
    "ExecutionFlow",
    # Quality Assurance
    "QualityAssurance",
    "QualityLevel",
    "QualityReport",
    "ConflictType",
    "ConflictReport",
    "ReflectionResult",
    # Memory Manager
    "MemoryManager",
    "MemoryType",
    "MemoryItem",
    # Adaptive Orchestrator
    "AdaptiveOrchestrator",
    "OrchestrationConfig",
    "TaskNode",
    "TaskPriority",
    "OrchestrationSignal",
    # Built-in tools
    "CodeExecutionTool",
    "create_code_execution_tool",
    "FileOperationsTool",
    "create_file_operations_tool",
    # Constants
    "VALID_STATE_TRANSITIONS",
]
