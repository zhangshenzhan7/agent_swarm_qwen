"""Unit tests for AgentSwarm.execute() → TaskExecutor.execute_with_plan() integration (Task 7.1).

Tests that:
1. Non-simple tasks route through execute_with_plan() with correct arguments
2. Task.content is set to plan.refined_task
3. execution_flow and suggested_agents are passed through
4. Supervisor instance is passed for quality gate support
5. Supervisor planning failure falls back to original flow
6. Simple direct tasks still work as before
7. No-supervisor path remains unchanged
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from src.core.agent_swarm import AgentSwarm, AgentSwarmConfig
from src.models.result import TaskResult
from src.models.task import Task
from src.models.enums import TaskStatus
from src.supervisor import SupervisorConfig, StreamCallback


def _make_mock_plan(task_type="comprehensive", direct_answer=None,
                    refined_task="refined task content",
                    execution_flow=None, suggested_agents=None,
                    estimated_complexity=5.0):
    """Create a mock TaskPlan object."""
    plan = MagicMock()
    plan.task_analysis = {
        "task_type": task_type,
        "complexity": 3,
        "direct_answer": direct_answer,
    }
    plan.refined_task = refined_task
    plan.execution_flow = execution_flow
    plan.suggested_agents = suggested_agents or []
    plan.estimated_complexity = estimated_complexity
    plan.to_dict.return_value = {
        "original_task": "test task",
        "task_analysis": plan.task_analysis,
        "refined_task": refined_task,
        "execution_flow": None,
        "suggested_agents": suggested_agents or [],
    }
    return plan


class TestExecuteWithPlanRouting:
    """Test that non-simple tasks are routed through execute_with_plan()."""

    @pytest.mark.asyncio
    async def test_complex_task_calls_execute_with_plan(self):
        """Non-simple tasks should call executor.execute_with_plan() instead of submit_task."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        mock_flow = MagicMock()
        plan = _make_mock_plan(
            task_type="comprehensive",
            refined_task="improved task description",
            execution_flow=mock_flow,
            suggested_agents=["researcher", "coder"],
            estimated_complexity=7.0,
        )

        mock_executor = MagicMock()
        mock_plan_result = TaskResult(
            task_id="t1", success=True, output="plan result",
            error=None, execution_time=2.0, metadata={},
        )
        mock_executor.execute_with_plan = AsyncMock(return_value=mock_plan_result)

        mock_main_agent = MagicMock()
        mock_main_agent._executor = mock_executor

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(return_value=plan)

            result = await swarm.execute("Build a web app")

            # Should have called execute_with_plan, NOT submit_task
            mock_executor.execute_with_plan.assert_awaited_once()
            mock_main_agent.submit_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_task_content_is_refined_task(self):
        """The Task passed to execute_with_plan should have content = plan.refined_task."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(
            task_type="comprehensive",
            refined_task="this is the refined version",
        )

        mock_executor = MagicMock()
        mock_plan_result = TaskResult(
            task_id="t1", success=True, output="result",
            error=None, execution_time=1.0, metadata={},
        )
        mock_executor.execute_with_plan = AsyncMock(return_value=mock_plan_result)

        mock_main_agent = MagicMock()
        mock_main_agent._executor = mock_executor

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(return_value=plan)

            await swarm.execute("original task")

            call_args = mock_executor.execute_with_plan.call_args
            task_arg = call_args[0][0]  # first positional arg
            assert isinstance(task_arg, Task)
            assert task_arg.content == "this is the refined version"

    @pytest.mark.asyncio
    async def test_plan_passed_to_execute_with_plan(self):
        """The TaskPlan should be passed as the second argument."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="comprehensive")

        mock_executor = MagicMock()
        mock_plan_result = TaskResult(
            task_id="t1", success=True, output="result",
            error=None, execution_time=1.0, metadata={},
        )
        mock_executor.execute_with_plan = AsyncMock(return_value=mock_plan_result)

        mock_main_agent = MagicMock()
        mock_main_agent._executor = mock_executor

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(return_value=plan)

            await swarm.execute("test task")

            call_args = mock_executor.execute_with_plan.call_args
            plan_arg = call_args[0][1]  # second positional arg
            assert plan_arg is plan

    @pytest.mark.asyncio
    async def test_supervisor_passed_to_execute_with_plan(self):
        """The Supervisor instance should be passed for quality gate support."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="comprehensive")

        mock_executor = MagicMock()
        mock_plan_result = TaskResult(
            task_id="t1", success=True, output="result",
            error=None, execution_time=1.0, metadata={},
        )
        mock_executor.execute_with_plan = AsyncMock(return_value=mock_plan_result)

        mock_main_agent = MagicMock()
        mock_main_agent._executor = mock_executor

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(return_value=plan)

            await swarm.execute("test task")

            call_args = mock_executor.execute_with_plan.call_args
            assert call_args.kwargs.get("supervisor") is mock_sv

    @pytest.mark.asyncio
    async def test_stream_callback_passed_to_execute_with_plan(self):
        """stream_callback should be forwarded to execute_with_plan()."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="comprehensive")
        callback = AsyncMock()

        mock_executor = MagicMock()
        mock_plan_result = TaskResult(
            task_id="t1", success=True, output="result",
            error=None, execution_time=1.0, metadata={},
        )
        mock_executor.execute_with_plan = AsyncMock(return_value=mock_plan_result)

        mock_main_agent = MagicMock()
        mock_main_agent._executor = mock_executor

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(return_value=plan)

            await swarm.execute("test task", stream_callback=callback)

            call_args = mock_executor.execute_with_plan.call_args
            assert call_args.kwargs.get("stream_callback") is callback


class TestTaskObjectCreation:
    """Test that the Task object is created correctly for execute_with_plan."""

    @pytest.mark.asyncio
    async def test_task_has_pending_status(self):
        """Task should be created with PENDING status."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="comprehensive", estimated_complexity=8.0)

        mock_executor = MagicMock()
        mock_plan_result = TaskResult(
            task_id="t1", success=True, output="result",
            error=None, execution_time=1.0, metadata={},
        )
        mock_executor.execute_with_plan = AsyncMock(return_value=mock_plan_result)

        mock_main_agent = MagicMock()
        mock_main_agent._executor = mock_executor

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(return_value=plan)

            await swarm.execute("test task")

            call_args = mock_executor.execute_with_plan.call_args
            task_arg = call_args[0][0]
            assert task_arg.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_task_has_estimated_complexity(self):
        """Task complexity_score should come from plan.estimated_complexity."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="comprehensive", estimated_complexity=8.5)

        mock_executor = MagicMock()
        mock_plan_result = TaskResult(
            task_id="t1", success=True, output="result",
            error=None, execution_time=1.0, metadata={},
        )
        mock_executor.execute_with_plan = AsyncMock(return_value=mock_plan_result)

        mock_main_agent = MagicMock()
        mock_main_agent._executor = mock_executor

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(return_value=plan)

            await swarm.execute("test task")

            call_args = mock_executor.execute_with_plan.call_args
            task_arg = call_args[0][0]
            assert task_arg.complexity_score == 8.5

    @pytest.mark.asyncio
    async def test_task_has_uuid_id(self):
        """Task should have a valid UUID id."""
        import uuid

        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="comprehensive")

        mock_executor = MagicMock()
        mock_plan_result = TaskResult(
            task_id="t1", success=True, output="result",
            error=None, execution_time=1.0, metadata={},
        )
        mock_executor.execute_with_plan = AsyncMock(return_value=mock_plan_result)

        mock_main_agent = MagicMock()
        mock_main_agent._executor = mock_executor

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(return_value=plan)

            await swarm.execute("test task")

            call_args = mock_executor.execute_with_plan.call_args
            task_arg = call_args[0][0]
            # Should be a valid UUID string
            uuid.UUID(task_arg.id)

    @pytest.mark.asyncio
    async def test_task_metadata_from_user(self):
        """Task metadata should come from the user-provided metadata."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="comprehensive")
        user_meta = {"project": "test", "priority": "high"}

        mock_executor = MagicMock()
        mock_plan_result = TaskResult(
            task_id="t1", success=True, output="result",
            error=None, execution_time=1.0, metadata={},
        )
        mock_executor.execute_with_plan = AsyncMock(return_value=mock_plan_result)

        mock_main_agent = MagicMock()
        mock_main_agent._executor = mock_executor

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(return_value=plan)

            await swarm.execute("test task", metadata=user_meta)

            call_args = mock_executor.execute_with_plan.call_args
            task_arg = call_args[0][0]
            assert task_arg.metadata == user_meta


class TestPlanMetadataInResult:
    """Test that TaskPlan is stored in result metadata."""

    @pytest.mark.asyncio
    async def test_plan_stored_in_result_metadata(self):
        """Result metadata should contain task_plan from plan.to_dict()."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="comprehensive")

        mock_executor = MagicMock()
        mock_plan_result = TaskResult(
            task_id="t1", success=True, output="result",
            error=None, execution_time=1.0, metadata={},
        )
        mock_executor.execute_with_plan = AsyncMock(return_value=mock_plan_result)

        mock_main_agent = MagicMock()
        mock_main_agent._executor = mock_executor

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(return_value=plan)

            result = await swarm.execute("test task")

            assert result.metadata is not None
            assert "task_plan" in result.metadata
            assert result.metadata["task_plan"] == plan.to_dict()

    @pytest.mark.asyncio
    async def test_plan_stored_even_when_result_metadata_is_none(self):
        """If execute_with_plan returns result with metadata=None, we should still store plan."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="comprehensive")

        mock_executor = MagicMock()
        mock_plan_result = TaskResult(
            task_id="t1", success=True, output="result",
            error=None, execution_time=1.0, metadata=None,
        )
        mock_executor.execute_with_plan = AsyncMock(return_value=mock_plan_result)

        mock_main_agent = MagicMock()
        mock_main_agent._executor = mock_executor

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(return_value=plan)

            result = await swarm.execute("test task")

            assert result.metadata is not None
            assert "task_plan" in result.metadata


class TestSupervisorPlanningFailure:
    """Test fallback behavior when Supervisor planning fails."""

    @pytest.mark.asyncio
    async def test_planning_failure_falls_back_to_original_flow(self):
        """When plan_task() raises, should fall back to submit_task + execute_with_timeout."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        mock_task = MagicMock()
        mock_result = TaskResult(
            task_id="t1", success=True, output="fallback result",
            error=None, execution_time=1.0,
        )

        mock_main_agent = MagicMock()
        mock_main_agent.submit_task = AsyncMock(return_value=mock_task)
        mock_main_agent.execute_with_timeout = AsyncMock(return_value=mock_result)

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(side_effect=RuntimeError("LLM timeout"))

            result = await swarm.execute("test task")

            # Should have fallen back to original flow
            mock_main_agent.submit_task.assert_awaited_once_with("test task", None)
            mock_main_agent.execute_with_timeout.assert_awaited_once_with(mock_task)
            assert result.output == "fallback result"

    @pytest.mark.asyncio
    async def test_planning_failure_stores_error_in_metadata(self):
        """Planning failure info should be stored in result metadata."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        mock_task = MagicMock()
        mock_result = TaskResult(
            task_id="t1", success=True, output="fallback result",
            error=None, execution_time=1.0,
        )

        mock_main_agent = MagicMock()
        mock_main_agent.submit_task = AsyncMock(return_value=mock_task)
        mock_main_agent.execute_with_timeout = AsyncMock(return_value=mock_result)

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(side_effect=ValueError("bad input"))

            result = await swarm.execute("test task")

            assert result.metadata is not None
            assert "supervisor_planning_error" in result.metadata
            assert "bad input" in result.metadata["supervisor_planning_error"]

    @pytest.mark.asyncio
    async def test_planning_failure_with_none_metadata(self):
        """Fallback should handle result with metadata=None."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        mock_task = MagicMock()
        mock_result = TaskResult(
            task_id="t1", success=True, output="fallback result",
            error=None, execution_time=1.0, metadata=None,
        )

        mock_main_agent = MagicMock()
        mock_main_agent.submit_task = AsyncMock(return_value=mock_task)
        mock_main_agent.execute_with_timeout = AsyncMock(return_value=mock_result)

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(side_effect=Exception("network error"))

            result = await swarm.execute("test task")

            assert result.metadata is not None
            assert "supervisor_planning_error" in result.metadata

    @pytest.mark.asyncio
    async def test_planning_failure_uses_original_task_content(self):
        """Fallback should use the original task_content, not refined_task."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        mock_task = MagicMock()
        mock_result = TaskResult(
            task_id="t1", success=True, output="result",
            error=None, execution_time=1.0,
        )

        mock_main_agent = MagicMock()
        mock_main_agent.submit_task = AsyncMock(return_value=mock_task)
        mock_main_agent.execute_with_timeout = AsyncMock(return_value=mock_result)

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(side_effect=RuntimeError("fail"))

            await swarm.execute("original task content", metadata={"key": "val"})

            mock_main_agent.submit_task.assert_awaited_once_with(
                "original task content", {"key": "val"}
            )


class TestSimpleDirectStillWorks:
    """Verify simple_direct path is unchanged after Task 7.1 modifications."""

    @pytest.mark.asyncio
    async def test_simple_direct_returns_immediately(self):
        """simple_direct with direct_answer should still return immediately."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="simple_direct", direct_answer="42")

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv:
            mock_sv.plan_task = AsyncMock(return_value=plan)

            result = await swarm.execute("What is 42?")

            assert result.success is True
            assert result.output == "42"
            assert result.metadata["task_plan"] == plan.to_dict()


class TestNoSupervisorUnchanged:
    """Verify no-supervisor path is completely unchanged."""

    @pytest.mark.asyncio
    async def test_no_supervisor_uses_original_flow(self):
        """Without supervisor, should use submit_task + execute_with_timeout."""
        swarm = AgentSwarm(config=AgentSwarmConfig())

        mock_task = MagicMock()
        mock_result = TaskResult(
            task_id="t1", success=True, output="result",
            error=None, execution_time=1.0,
        )

        mock_main_agent = MagicMock()
        mock_main_agent.submit_task = AsyncMock(return_value=mock_task)
        mock_main_agent.execute_with_timeout = AsyncMock(return_value=mock_result)

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_main_agent', mock_main_agent), \
             patch.object(swarm, '_supervisor', None):

            result = await swarm.execute("test task")

            mock_main_agent.submit_task.assert_awaited_once_with("test task", None)
            mock_main_agent.execute_with_timeout.assert_awaited_once_with(mock_task)
            assert result.output == "result"
