"""向后兼容性验证测试。

验证 submit_task()、execute_task() 方法签名和行为不变，
以及 __init__.py 中的 __all__ 导出项完整性。

Requirements: 7.1, 7.3, 7.4
"""

import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.agent_swarm import AgentSwarm, AgentSwarmConfig
from src.models.task import Task
from src.models.enums import TaskStatus


class TestSubmitTaskSignature:
    """验证 submit_task() 方法签名不变。"""

    def test_submit_task_exists(self):
        """submit_task 方法应存在于 AgentSwarm 上。"""
        assert hasattr(AgentSwarm, "submit_task")
        assert callable(getattr(AgentSwarm, "submit_task"))

    def test_submit_task_is_async(self):
        """submit_task 应为异步方法。"""
        assert inspect.iscoroutinefunction(AgentSwarm.submit_task)

    def test_submit_task_parameters(self):
        """submit_task(self, task_content: str, metadata=None) 签名应保持不变。"""
        sig = inspect.signature(AgentSwarm.submit_task)
        params = list(sig.parameters.keys())

        assert params == ["self", "task_content", "metadata"]

    def test_submit_task_task_content_required(self):
        """task_content 参数应为必填（无默认值）。"""
        sig = inspect.signature(AgentSwarm.submit_task)
        param = sig.parameters["task_content"]
        assert param.default is inspect.Parameter.empty

    def test_submit_task_metadata_optional_none(self):
        """metadata 参数应为可选，默认值为 None。"""
        sig = inspect.signature(AgentSwarm.submit_task)
        param = sig.parameters["metadata"]
        assert param.default is None

    def test_submit_task_return_annotation(self):
        """submit_task 返回类型应为 Task。"""
        sig = inspect.signature(AgentSwarm.submit_task)
        assert sig.return_annotation is Task


class TestExecuteTaskSignature:
    """验证 execute_task() 方法签名不变。"""

    def test_execute_task_exists(self):
        """execute_task 方法应存在于 AgentSwarm 上。"""
        assert hasattr(AgentSwarm, "execute_task")
        assert callable(getattr(AgentSwarm, "execute_task"))

    def test_execute_task_is_async(self):
        """execute_task 应为异步方法。"""
        assert inspect.iscoroutinefunction(AgentSwarm.execute_task)

    def test_execute_task_parameters(self):
        """execute_task(self, task) 签名应保持不变。"""
        sig = inspect.signature(AgentSwarm.execute_task)
        params = list(sig.parameters.keys())

        assert params == ["self", "task"]

    def test_execute_task_task_required(self):
        """task 参数应为必填（无默认值）。"""
        sig = inspect.signature(AgentSwarm.execute_task)
        param = sig.parameters["task"]
        assert param.default is inspect.Parameter.empty


class TestExecuteSignature:
    """验证 execute() 方法签名向后兼容。"""

    def test_execute_is_async(self):
        """execute 应为异步方法。"""
        assert inspect.iscoroutinefunction(AgentSwarm.execute)

    def test_execute_parameters(self):
        """execute(self, task_content, metadata=None, stream_callback=None) 签名应保持向后兼容。"""
        sig = inspect.signature(AgentSwarm.execute)
        params = list(sig.parameters.keys())

        assert params == ["self", "task_content", "metadata", "stream_callback"]

    def test_execute_stream_callback_optional_none(self):
        """stream_callback 参数应为可选，默认值为 None。"""
        sig = inspect.signature(AgentSwarm.execute)
        param = sig.parameters["stream_callback"]
        assert param.default is None

    def test_execute_task_content_required(self):
        """task_content 参数应为必填。"""
        sig = inspect.signature(AgentSwarm.execute)
        param = sig.parameters["task_content"]
        assert param.default is inspect.Parameter.empty

    def test_execute_metadata_optional_none(self):
        """metadata 参数应为可选，默认值为 None。"""
        sig = inspect.signature(AgentSwarm.execute)
        param = sig.parameters["metadata"]
        assert param.default is None


class TestInitAllExports:
    """验证 __init__.py 中的 __all__ 导出项完整性。"""

    def test_src_init_all_exists(self):
        """src/__init__.py 应定义 __all__。"""
        import src
        assert hasattr(src, "__all__")
        assert isinstance(src.__all__, list)

    def test_src_init_contains_core_exports(self):
        """src/__init__.py 的 __all__ 应包含所有核心导出项。"""
        import src

        expected_core_exports = [
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

        for export in expected_core_exports:
            assert export in src.__all__, f"src/__init__.py __all__ 缺少导出项: {export}"

    def test_src_core_init_all_exists(self):
        """src/core/__init__.py 应定义 __all__。"""
        import src.core
        assert hasattr(src.core, "__all__")
        assert isinstance(src.core.__all__, list)

    def test_src_core_init_contains_expected_exports(self):
        """src/core/__init__.py 的 __all__ 应包含所有预期导出项。"""
        import src.core

        expected_exports = [
            "AgentSwarm",
            "AgentSwarmConfig",
            "TaskDecomposer",
            "QualityLevel",
            "ConflictType",
            "QualityReport",
            "ConflictReport",
            "ReflectionResult",
            "QualityAssurance",
        ]

        for export in expected_exports:
            assert export in src.core.__all__, (
                f"src/core/__init__.py __all__ 缺少导出项: {export}"
            )

    def test_no_exports_removed_from_src_init(self):
        """src/__init__.py 的 __all__ 不应少于预期的最小数量。"""
        import src
        # The current __all__ has a known set of exports; ensure none were removed.
        # At minimum we expect the version + all the categories listed.
        assert len(src.__all__) >= 60, (
            f"src/__init__.py __all__ 导出项数量异常偏少: {len(src.__all__)}"
        )


class TestSubmitTaskExecuteTaskBehavior:
    """验证 submit_task() 和 execute_task() 在无 supervisor_config 时正常工作。"""

    @pytest.mark.asyncio
    async def test_submit_task_without_supervisor_delegates_to_main_agent(self):
        """submit_task() 应委托给 main_agent.submit_task()。"""
        config = AgentSwarmConfig()
        swarm = AgentSwarm(config=config)

        mock_task = Task(
            id="test-1",
            content="test task",
            status=TaskStatus.PENDING,
            complexity_score=1.0,
            created_at=0.0,
        )

        mock_main_agent = MagicMock()
        mock_main_agent.submit_task = AsyncMock(return_value=mock_task)
        swarm._main_agent = mock_main_agent
        swarm._initialized = True

        result = await swarm.submit_task("test task", None)

        mock_main_agent.submit_task.assert_called_once_with("test task", None)
        assert result == mock_task

    @pytest.mark.asyncio
    async def test_execute_task_without_supervisor_delegates_to_main_agent(self):
        """execute_task() 应委托给 main_agent.execute_with_timeout()。"""
        config = AgentSwarmConfig()
        swarm = AgentSwarm(config=config)

        mock_task = Task(
            id="test-1",
            content="test task",
            status=TaskStatus.PENDING,
            complexity_score=1.0,
            created_at=0.0,
        )

        from src.models.result import TaskResult
        mock_result = TaskResult(
            task_id="test-1",
            success=True,
            output="done",
            error=None,
            execution_time=1.0,
        )

        mock_main_agent = MagicMock()
        mock_main_agent.execute_with_timeout = AsyncMock(return_value=mock_result)
        swarm._main_agent = mock_main_agent
        swarm._initialized = True

        result = await swarm.execute_task(mock_task)

        mock_main_agent.execute_with_timeout.assert_called_once_with(mock_task)
        assert result.success is True
        assert result.task_id == "test-1"
