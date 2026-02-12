"""Unit tests for AgentSwarm.execute() Supervisor integration (Task 2.1).

Tests the extended execute() method signature with stream_callback parameter,
simple_direct task handling, TaskPlan metadata storage, and backward compatibility.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

from src.core.agent_swarm import AgentSwarm, AgentSwarmConfig
from src.models.result import TaskResult
from src.supervisor import SupervisorConfig, StreamCallback


def _make_task_plan_dict(**overrides):
    """Helper to build a TaskPlan-like mock with to_dict()."""
    defaults = {
        "original_task": "test task",
        "task_analysis": {"task_type": "comprehensive", "complexity": 5},
        "refined_task": "refined test task",
        "background_research": "",
        "execution_plan": [],
        "execution_flow": None,
        "suggested_agents": [],
        "estimated_complexity": 5.0,
        "key_objectives": [],
        "success_criteria": [],
        "potential_challenges": [],
        "react_trace": [],
    }
    defaults.update(overrides)
    return defaults


def _make_mock_plan(task_type="comprehensive", direct_answer=None):
    """Create a mock TaskPlan object."""
    plan = MagicMock()
    plan.task_analysis = {
        "task_type": task_type,
        "complexity": 3,
        "direct_answer": direct_answer,
    }
    plan.refined_task = "refined task"
    plan.execution_flow = None
    plan.suggested_agents = []
    plan.to_dict.return_value = _make_task_plan_dict(
        task_analysis=plan.task_analysis,
    )
    return plan


class TestExecuteSignature:
    """Test that execute() accepts the new stream_callback parameter."""

    def test_execute_accepts_stream_callback_kwarg(self):
        """execute() should accept stream_callback as an optional keyword argument."""
        import inspect
        sig = inspect.signature(AgentSwarm.execute)
        params = list(sig.parameters.keys())
        assert "stream_callback" in params
        # Should have a default of None
        p = sig.parameters["stream_callback"]
        assert p.default is None

    def test_execute_signature_backward_compatible(self):
        """execute() should still accept (task_content, metadata) without stream_callback."""
        import inspect
        sig = inspect.signature(AgentSwarm.execute)
        params = sig.parameters
        # task_content is required (no default)
        assert params["task_content"].default is inspect.Parameter.empty
        # metadata is optional
        assert params["metadata"].default is None
        # stream_callback is optional
        assert params["stream_callback"].default is None


class TestExecuteWithSupervisor:
    """Test execute() behavior when supervisor is configured."""

    @pytest.mark.asyncio
    async def test_simple_direct_returns_immediately(self):
        """When task_type is simple_direct with a direct_answer, return TaskResult directly."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="simple_direct", direct_answer="42 is the answer")

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv:
            mock_sv.plan_task = AsyncMock(return_value=plan)

            result = await swarm.execute("What is 42?")

            assert result.success is True
            assert result.output == "42 is the answer"
            assert result.metadata is not None
            assert "task_plan" in result.metadata
            mock_sv.plan_task.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_simple_direct_empty_answer_falls_back(self):
        """When task_type is simple_direct but direct_answer is empty, fall back to execute_with_plan."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="simple_direct", direct_answer="")

        mock_result = TaskResult(
            task_id="t1", success=True, output="full flow result",
            error=None, execution_time=1.0, metadata={},
        )

        mock_executor = MagicMock()
        mock_executor.execute_with_plan = AsyncMock(return_value=mock_result)

        mock_main_agent = MagicMock()
        mock_main_agent._executor = mock_executor

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(return_value=plan)

            result = await swarm.execute("What is 42?")

            # Should have gone through execute_with_plan (non-simple path)
            mock_executor.execute_with_plan.assert_awaited_once()
            assert result.metadata is not None
            assert "task_plan" in result.metadata

    @pytest.mark.asyncio
    async def test_simple_direct_none_answer_falls_back(self):
        """When task_type is simple_direct but direct_answer is None, fall back to execute_with_plan."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="simple_direct", direct_answer=None)

        mock_result = TaskResult(
            task_id="t1", success=True, output="full flow result",
            error=None, execution_time=1.0, metadata={},
        )

        mock_executor = MagicMock()
        mock_executor.execute_with_plan = AsyncMock(return_value=mock_result)

        mock_main_agent = MagicMock()
        mock_main_agent._executor = mock_executor

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(return_value=plan)

            result = await swarm.execute("What is 42?")

            mock_executor.execute_with_plan.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complex_task_stores_plan_in_metadata(self):
        """Non-simple tasks should store TaskPlan in result.metadata['task_plan']."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="comprehensive")

        mock_result = TaskResult(
            task_id="t1", success=True, output="complex result",
            error=None, execution_time=2.0, metadata={},
        )

        mock_executor = MagicMock()
        mock_executor.execute_with_plan = AsyncMock(return_value=mock_result)

        mock_main_agent = MagicMock()
        mock_main_agent._executor = mock_executor

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv, \
             patch.object(swarm, '_main_agent', mock_main_agent):
            mock_sv.plan_task = AsyncMock(return_value=plan)

            result = await swarm.execute("Build a web app")

            assert result.metadata is not None
            assert result.metadata["task_plan"] == plan.to_dict()

    @pytest.mark.asyncio
    async def test_stream_callback_forwarded_to_plan_task(self):
        """stream_callback should be passed to supervisor.plan_task()."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="simple_direct", direct_answer="answer")
        callback = AsyncMock()

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv:
            mock_sv.plan_task = AsyncMock(return_value=plan)

            await swarm.execute("test", stream_callback=callback)

            mock_sv.plan_task.assert_awaited_once_with("test", None, callback)

    @pytest.mark.asyncio
    async def test_metadata_forwarded_to_plan_task(self):
        """metadata should be passed to supervisor.plan_task()."""
        swarm = AgentSwarm(config=AgentSwarmConfig(
            supervisor_config=SupervisorConfig(),
        ))

        plan = _make_mock_plan(task_type="simple_direct", direct_answer="answer")
        meta = {"key": "value"}

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_supervisor', create=True) as mock_sv:
            mock_sv.plan_task = AsyncMock(return_value=plan)

            await swarm.execute("test", metadata=meta, stream_callback=None)

            mock_sv.plan_task.assert_awaited_once_with("test", meta, None)


class TestExecuteWithoutSupervisor:
    """Test execute() behavior when no supervisor is configured (backward compat)."""

    @pytest.mark.asyncio
    async def test_no_supervisor_uses_original_flow(self):
        """Without supervisor_config, execute() should use the original submit+execute flow."""
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

    @pytest.mark.asyncio
    async def test_no_supervisor_ignores_stream_callback(self):
        """Without supervisor, stream_callback should be ignored."""
        swarm = AgentSwarm(config=AgentSwarmConfig())

        mock_task = MagicMock()
        mock_result = TaskResult(
            task_id="t1", success=True, output="result",
            error=None, execution_time=1.0,
        )

        mock_main_agent = MagicMock()
        mock_main_agent.submit_task = AsyncMock(return_value=mock_task)
        mock_main_agent.execute_with_timeout = AsyncMock(return_value=mock_result)

        callback = AsyncMock()

        with patch.object(swarm, '_initialize'), \
             patch.object(swarm, '_main_agent', mock_main_agent), \
             patch.object(swarm, '_supervisor', None):

            result = await swarm.execute("test task", stream_callback=callback)

            # Callback should never be called
            callback.assert_not_awaited()
            assert result.output == "result"


class TestTaskResultMetadata:
    """Test that TaskResult now supports the metadata field."""

    def test_task_result_has_metadata_field(self):
        """TaskResult should have an optional metadata field."""
        result = TaskResult(
            task_id="t1", success=True, output="out",
            error=None, execution_time=1.0,
        )
        assert result.metadata is None

    def test_task_result_metadata_can_be_set(self):
        """TaskResult metadata can be set to a dict."""
        result = TaskResult(
            task_id="t1", success=True, output="out",
            error=None, execution_time=1.0,
            metadata={"task_plan": {"key": "value"}},
        )
        assert result.metadata == {"task_plan": {"key": "value"}}
