"""Tests for quality gate integration in execute_with_plan() (Task 5.1).

Tests the quality gate logic that evaluates step results after each subtask
execution and handles retry, add_step, and continue actions.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.core.main_agent.executor import TaskExecutor, TaskExecutionError
from src.core.supervisor.flow import (
    ExecutionFlow, ExecutionStep, ExecutionStepStatus, TaskPlan,
)
from src.models.task import Task, SubTask
from src.models.result import TaskResult, SubTaskResult
from src.models.enums import TaskStatus
from src.models.team import TeamState, WaveExecutionResult
from src.supervisor import SupervisorConfig


def _make_execution_flow(*steps_data):
    """Helper to build an ExecutionFlow from tuples."""
    flow = ExecutionFlow()
    for step_id, step_number, desc, agent_type, deps in steps_data:
        step = ExecutionStep(
            step_id=step_id,
            step_number=step_number,
            name=f"Step {step_number}",
            description=desc,
            agent_type=agent_type,
            expected_output="output",
            dependencies=deps,
        )
        flow.add_step(step)
    flow.execution_order = [s[0] for s in steps_data]
    return flow


def _make_task_plan(execution_flow, suggested_agents=None):
    return TaskPlan(
        original_task="original task",
        task_analysis={"task_type": "comprehensive", "complexity": 7},
        refined_task="refined task content",
        background_research="some research",
        execution_plan=[],
        execution_flow=execution_flow,
        suggested_agents=suggested_agents or [],
    )


def _make_task(task_id="task-1"):
    return Task(
        id=task_id,
        content="refined task content",
        status=TaskStatus.PENDING,
        complexity_score=5.0,
        created_at=time.time(),
        metadata={},
    )


def _make_executor(**overrides):
    """Create a TaskExecutor with mocked dependencies."""
    defaults = dict(
        task_decomposer=MagicMock(),
        agent_scheduler=MagicMock(),
        result_aggregator=MagicMock(),
        context_manager=AsyncMock(),
        config=MagicMock(
            delegate_mode=False,
            use_team_mode=True,
            execution_timeout=300,
            timeout_warning_threshold=0.8,
        ),
        team_lifecycle_manager=MagicMock(),
        wave_executor=AsyncMock(),
    )
    defaults.update(overrides)
    return TaskExecutor(**defaults)


def _make_supervisor_mock(
    enable_quality_gates=True,
    max_retry_on_failure=2,
    evaluate_return=None,
    adjust_return=None,
):
    """Create a mock Supervisor with configurable quality gate behavior."""
    supervisor = MagicMock()
    supervisor._config = SupervisorConfig(
        enable_quality_gates=enable_quality_gates,
        max_retry_on_failure=max_retry_on_failure,
    )
    if evaluate_return is None:
        evaluate_return = {"action": "continue"}
    supervisor.evaluate_step_result = AsyncMock(return_value=evaluate_return)
    if adjust_return is None:
        adjust_return = MagicMock()
    supervisor.adjust_execution_flow = AsyncMock(return_value=adjust_return)
    return supervisor


def _setup_executor_with_team():
    """Create executor with fully mocked team lifecycle for execute_with_plan tests."""
    team_mock = MagicMock()
    team_mock.id = "team-1"

    task_board_mock = AsyncMock()
    message_bus_mock = MagicMock()

    tlm = MagicMock()
    tlm.create_team = AsyncMock(return_value=team_mock)
    tlm.setup_team = AsyncMock()
    tlm.set_team_state = MagicMock()
    tlm.get_task_board = MagicMock(return_value=task_board_mock)
    tlm.get_message_bus = MagicMock(return_value=message_bus_mock)
    tlm.disband_team = AsyncMock()
    tlm.get_team_status = AsyncMock(
        return_value=MagicMock(state=TeamState.DISBANDED)
    )

    wave_result = WaveExecutionResult(
        total_waves=1,
        total_tasks=1,
        completed_tasks=1,
        failed_tasks=0,
        blocked_tasks=0,
        wave_stats=[],
        total_execution_time=1.0,
    )
    wave_executor = AsyncMock()
    wave_executor.execute = AsyncMock(return_value=wave_result)

    context_manager = AsyncMock()

    executor = _make_executor(
        team_lifecycle_manager=tlm,
        wave_executor=wave_executor,
        context_manager=context_manager,
    )
    return executor, tlm, task_board_mock, wave_executor


class TestQualityGateSkipped:
    """Test that quality gate is skipped when disabled or supervisor is None."""

    @pytest.mark.asyncio
    async def test_no_supervisor_skips_quality_gate(self):
        """Req 6.5: When supervisor is None, evaluate_step_result should not be called."""
        executor = _make_executor()
        subtask = SubTask(
            id="s1", parent_task_id="t1", content="test",
            role_hint="researcher", dependencies=set(), priority=1,
        )
        subtask_outputs = {}
        flow = _make_execution_flow(("s1", 1, "test", "researcher", []))

        with patch.object(executor, '_run_subtask', new_callable=AsyncMock, return_value="output"):
            result = await executor._run_subtask_with_quality_gate(
                task=_make_task(),
                subtask=subtask,
                subtask_map={"s1": subtask},
                subtask_outputs=subtask_outputs,
                message_bus=MagicMock(),
                execution_flow=flow,
                supervisor=None,
                stream_callback=None,
                retry_counts={},
                task_board=AsyncMock(),
                dependency_map={},
            )

        assert result == "output"

    @pytest.mark.asyncio
    async def test_quality_gates_disabled_skips_evaluation(self):
        """Req 6.5: When enable_quality_gates is False, skip evaluation."""
        executor = _make_executor()
        supervisor = _make_supervisor_mock(enable_quality_gates=False)
        subtask = SubTask(
            id="s1", parent_task_id="t1", content="test",
            role_hint="researcher", dependencies=set(), priority=1,
        )
        flow = _make_execution_flow(("s1", 1, "test", "researcher", []))

        with patch.object(executor, '_run_subtask', new_callable=AsyncMock, return_value="output"):
            result = await executor._run_subtask_with_quality_gate(
                task=_make_task(),
                subtask=subtask,
                subtask_map={"s1": subtask},
                subtask_outputs={},
                message_bus=MagicMock(),
                execution_flow=flow,
                supervisor=supervisor,
                stream_callback=None,
                retry_counts={},
                task_board=AsyncMock(),
                dependency_map={},
            )

        assert result == "output"
        supervisor.evaluate_step_result.assert_not_awaited()


class TestQualityGateContinue:
    """Test quality gate with action='continue'."""

    @pytest.mark.asyncio
    async def test_continue_action_returns_output(self):
        """Req 6.1, 6.4: When action is 'continue', return output normally."""
        executor = _make_executor()
        supervisor = _make_supervisor_mock(
            evaluate_return={"action": "continue"}
        )
        subtask = SubTask(
            id="s1", parent_task_id="t1", content="test",
            role_hint="researcher", dependencies=set(), priority=1,
        )
        flow = _make_execution_flow(("s1", 1, "test", "researcher", []))

        with patch.object(executor, '_run_subtask', new_callable=AsyncMock, return_value="good output"):
            result = await executor._run_subtask_with_quality_gate(
                task=_make_task(),
                subtask=subtask,
                subtask_map={"s1": subtask},
                subtask_outputs={},
                message_bus=MagicMock(),
                execution_flow=flow,
                supervisor=supervisor,
                stream_callback=None,
                retry_counts={},
                task_board=AsyncMock(),
                dependency_map={},
            )

        assert result == "good output"
        supervisor.evaluate_step_result.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_evaluate_called_with_correct_args(self):
        """Req 6.1: evaluate_step_result receives step, result_dict, flow, callback."""
        executor = _make_executor()
        callback = AsyncMock()
        supervisor = _make_supervisor_mock(
            evaluate_return={"action": "continue"}
        )
        subtask = SubTask(
            id="s1", parent_task_id="t1", content="test",
            role_hint="researcher", dependencies=set(), priority=1,
        )
        flow = _make_execution_flow(("s1", 1, "test", "researcher", []))

        with patch.object(executor, '_run_subtask', new_callable=AsyncMock, return_value="output"):
            await executor._run_subtask_with_quality_gate(
                task=_make_task(),
                subtask=subtask,
                subtask_map={"s1": subtask},
                subtask_outputs={},
                message_bus=MagicMock(),
                execution_flow=flow,
                supervisor=supervisor,
                stream_callback=callback,
                retry_counts={},
                task_board=AsyncMock(),
                dependency_map={},
            )

        call_args = supervisor.evaluate_step_result.call_args
        step_arg = call_args[0][0]
        result_arg = call_args[0][1]
        flow_arg = call_args[0][2]
        callback_arg = call_args[0][3]

        assert step_arg.step_id == "s1"
        assert result_arg["subtask_id"] == "s1"
        assert result_arg["output"] == "output"
        assert result_arg["success"] is True
        assert flow_arg is flow
        assert callback_arg is callback


class TestQualityGateRetry:
    """Test quality gate with action='retry'."""

    @pytest.mark.asyncio
    async def test_retry_re_executes_subtask(self):
        """Req 6.2: When action is 'retry', re-execute the subtask."""
        executor = _make_executor()
        # First call returns retry, second returns continue
        supervisor = _make_supervisor_mock(max_retry_on_failure=2)
        supervisor.evaluate_step_result = AsyncMock(
            side_effect=[
                {"action": "retry"},
                {"action": "continue"},
            ]
        )
        subtask = SubTask(
            id="s1", parent_task_id="t1", content="test",
            role_hint="researcher", dependencies=set(), priority=1,
        )
        flow = _make_execution_flow(("s1", 1, "test", "researcher", []))

        call_count = 0

        async def mock_run_subtask(task, subtask, subtask_map, subtask_outputs, message_bus):
            nonlocal call_count
            call_count += 1
            subtask_outputs[subtask.id] = SubTaskResult(
                subtask_id=subtask.id, agent_id="agent-1", success=True,
                output=f"output-{call_count}", error=None, tool_calls=[],
                execution_time=0.1,
            )
            return f"output-{call_count}"

        with patch.object(executor, '_run_subtask', side_effect=mock_run_subtask):
            result = await executor._run_subtask_with_quality_gate(
                task=_make_task(),
                subtask=subtask,
                subtask_map={"s1": subtask},
                subtask_outputs={},
                message_bus=MagicMock(),
                execution_flow=flow,
                supervisor=supervisor,
                stream_callback=None,
                retry_counts={},
                task_board=AsyncMock(),
                dependency_map={},
            )

        assert call_count == 2
        assert result == "output-2"
        assert supervisor.evaluate_step_result.await_count == 2

    @pytest.mark.asyncio
    async def test_retry_respects_max_retry_limit(self):
        """Req 6.2: Retry count must not exceed max_retry_on_failure."""
        executor = _make_executor()
        supervisor = _make_supervisor_mock(max_retry_on_failure=1)
        # Always returns retry
        supervisor.evaluate_step_result = AsyncMock(
            return_value={"action": "retry"}
        )
        subtask = SubTask(
            id="s1", parent_task_id="t1", content="test",
            role_hint="researcher", dependencies=set(), priority=1,
        )
        flow = _make_execution_flow(("s1", 1, "test", "researcher", []))

        call_count = 0

        async def mock_run_subtask(task, subtask, subtask_map, subtask_outputs, message_bus):
            nonlocal call_count
            call_count += 1
            subtask_outputs[subtask.id] = SubTaskResult(
                subtask_id=subtask.id, agent_id="agent-1", success=True,
                output=f"output-{call_count}", error=None, tool_calls=[],
                execution_time=0.1,
            )
            return f"output-{call_count}"

        with patch.object(executor, '_run_subtask', side_effect=mock_run_subtask):
            result = await executor._run_subtask_with_quality_gate(
                task=_make_task(),
                subtask=subtask,
                subtask_map={"s1": subtask},
                subtask_outputs={},
                message_bus=MagicMock(),
                execution_flow=flow,
                supervisor=supervisor,
                stream_callback=None,
                retry_counts={},
                task_board=AsyncMock(),
                dependency_map={},
            )

        # max_retry_on_failure=1: original + 1 retry = 2 calls, then stops
        assert call_count == 2
        # After retry limit, returns the last output
        assert result == "output-2"

    @pytest.mark.asyncio
    async def test_retry_zero_max_retries_no_retry(self):
        """When max_retry_on_failure=0, no retries should happen."""
        executor = _make_executor()
        supervisor = _make_supervisor_mock(max_retry_on_failure=0)
        supervisor.evaluate_step_result = AsyncMock(
            return_value={"action": "retry"}
        )
        subtask = SubTask(
            id="s1", parent_task_id="t1", content="test",
            role_hint="researcher", dependencies=set(), priority=1,
        )
        flow = _make_execution_flow(("s1", 1, "test", "researcher", []))

        call_count = 0

        async def mock_run_subtask(task, subtask, subtask_map, subtask_outputs, message_bus):
            nonlocal call_count
            call_count += 1
            subtask_outputs[subtask.id] = SubTaskResult(
                subtask_id=subtask.id, agent_id="agent-1", success=True,
                output="output", error=None, tool_calls=[],
                execution_time=0.1,
            )
            return "output"

        with patch.object(executor, '_run_subtask', side_effect=mock_run_subtask):
            result = await executor._run_subtask_with_quality_gate(
                task=_make_task(),
                subtask=subtask,
                subtask_map={"s1": subtask},
                subtask_outputs={},
                message_bus=MagicMock(),
                execution_flow=flow,
                supervisor=supervisor,
                stream_callback=None,
                retry_counts={},
                task_board=AsyncMock(),
                dependency_map={},
            )

        assert call_count == 1
        assert result == "output"


class TestQualityGateAddStep:
    """Test quality gate with action='add_step'."""

    @pytest.mark.asyncio
    async def test_add_step_calls_adjust_and_publishes(self):
        """Req 6.3: When action is 'add_step', call adjust_execution_flow and publish new tasks."""
        executor = _make_executor()
        flow = _make_execution_flow(("s1", 1, "test", "researcher", []))
        supervisor = _make_supervisor_mock(
            evaluate_return={
                "action": "add_step",
                "adjustments": [
                    {
                        "type": "add_step",
                        "step_id": "s_new",
                        "details": {
                            "name": "New Step",
                            "description": "Dynamic step",
                            "agent_type": "analyst",
                            "dependencies": ["s1"],
                        },
                    }
                ],
            }
        )

        # After adjust_execution_flow, the new step should exist in the flow
        async def mock_adjust(ef, adjustments, cb):
            new_step = ExecutionStep(
                step_id="s_new",
                step_number=2,
                name="New Step",
                description="Dynamic step",
                agent_type="analyst",
                expected_output="",
                dependencies=["s1"],
            )
            ef.add_step(new_step)
            return ef

        supervisor.adjust_execution_flow = AsyncMock(side_effect=mock_adjust)

        subtask = SubTask(
            id="s1", parent_task_id="t1", content="test",
            role_hint="researcher", dependencies=set(), priority=1,
        )
        task_board = AsyncMock()
        subtask_map = {"s1": subtask}

        with patch.object(executor, '_run_subtask', new_callable=AsyncMock, return_value="output"):
            result = await executor._run_subtask_with_quality_gate(
                task=_make_task(),
                subtask=subtask,
                subtask_map=subtask_map,
                subtask_outputs={},
                message_bus=MagicMock(),
                execution_flow=flow,
                supervisor=supervisor,
                stream_callback=None,
                retry_counts={},
                task_board=task_board,
                dependency_map={},
            )

        assert result == "output"
        supervisor.adjust_execution_flow.assert_awaited_once()
        # New subtask should be published to task_board
        task_board.publish_tasks.assert_awaited_once()
        published_subtasks = task_board.publish_tasks.call_args[0][0]
        assert len(published_subtasks) == 1
        assert published_subtasks[0].id == "s_new"
        assert published_subtasks[0].content == "Dynamic step"
        assert published_subtasks[0].role_hint == "analyst"
        # New subtask should be added to subtask_map
        assert "s_new" in subtask_map

    @pytest.mark.asyncio
    async def test_add_step_with_empty_adjustments(self):
        """When add_step has empty adjustments, no new tasks are published."""
        executor = _make_executor()
        flow = _make_execution_flow(("s1", 1, "test", "researcher", []))
        supervisor = _make_supervisor_mock(
            evaluate_return={"action": "add_step", "adjustments": []}
        )
        subtask = SubTask(
            id="s1", parent_task_id="t1", content="test",
            role_hint="researcher", dependencies=set(), priority=1,
        )
        task_board = AsyncMock()

        with patch.object(executor, '_run_subtask', new_callable=AsyncMock, return_value="output"):
            result = await executor._run_subtask_with_quality_gate(
                task=_make_task(),
                subtask=subtask,
                subtask_map={"s1": subtask},
                subtask_outputs={},
                message_bus=MagicMock(),
                execution_flow=flow,
                supervisor=supervisor,
                stream_callback=None,
                retry_counts={},
                task_board=task_board,
                dependency_map={},
            )

        assert result == "output"
        # adjust_execution_flow should not be called with empty adjustments
        supervisor.adjust_execution_flow.assert_not_awaited()
        task_board.publish_tasks.assert_not_awaited()


class TestQualityGateErrorHandling:
    """Test error handling in quality gate evaluation."""

    @pytest.mark.asyncio
    async def test_evaluate_exception_treated_as_continue(self):
        """Design doc: When evaluate_step_result throws, treat as action='continue'."""
        executor = _make_executor()
        supervisor = _make_supervisor_mock()
        supervisor.evaluate_step_result = AsyncMock(
            side_effect=RuntimeError("LLM error")
        )
        subtask = SubTask(
            id="s1", parent_task_id="t1", content="test",
            role_hint="researcher", dependencies=set(), priority=1,
        )
        flow = _make_execution_flow(("s1", 1, "test", "researcher", []))

        with patch.object(executor, '_run_subtask', new_callable=AsyncMock, return_value="output"):
            result = await executor._run_subtask_with_quality_gate(
                task=_make_task(),
                subtask=subtask,
                subtask_map={"s1": subtask},
                subtask_outputs={},
                message_bus=MagicMock(),
                execution_flow=flow,
                supervisor=supervisor,
                stream_callback=None,
                retry_counts={},
                task_board=AsyncMock(),
                dependency_map={},
            )

        # Should return output despite the exception
        assert result == "output"

    @pytest.mark.asyncio
    async def test_adjust_exception_ignored_and_continues(self):
        """Design doc: When adjust_execution_flow throws, ignore and continue."""
        executor = _make_executor()
        flow = _make_execution_flow(("s1", 1, "test", "researcher", []))
        supervisor = _make_supervisor_mock(
            evaluate_return={
                "action": "add_step",
                "adjustments": [{"type": "add_step", "step_id": "s_new", "details": {}}],
            }
        )
        supervisor.adjust_execution_flow = AsyncMock(
            side_effect=RuntimeError("Adjustment failed")
        )
        subtask = SubTask(
            id="s1", parent_task_id="t1", content="test",
            role_hint="researcher", dependencies=set(), priority=1,
        )
        task_board = AsyncMock()

        with patch.object(executor, '_run_subtask', new_callable=AsyncMock, return_value="output"):
            result = await executor._run_subtask_with_quality_gate(
                task=_make_task(),
                subtask=subtask,
                subtask_map={"s1": subtask},
                subtask_outputs={},
                message_bus=MagicMock(),
                execution_flow=flow,
                supervisor=supervisor,
                stream_callback=None,
                retry_counts={},
                task_board=task_board,
                dependency_map={},
            )

        # Should return output despite the adjustment exception
        assert result == "output"
        # publish_tasks should NOT be called since adjust failed
        task_board.publish_tasks.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_step_in_flow_skips_evaluation(self):
        """When subtask.id is not in execution_flow.steps, skip evaluation."""
        executor = _make_executor()
        supervisor = _make_supervisor_mock()
        # Flow has step "s2" but subtask is "s1"
        flow = _make_execution_flow(("s2", 1, "other", "researcher", []))
        subtask = SubTask(
            id="s1", parent_task_id="t1", content="test",
            role_hint="researcher", dependencies=set(), priority=1,
        )

        with patch.object(executor, '_run_subtask', new_callable=AsyncMock, return_value="output"):
            result = await executor._run_subtask_with_quality_gate(
                task=_make_task(),
                subtask=subtask,
                subtask_map={"s1": subtask},
                subtask_outputs={},
                message_bus=MagicMock(),
                execution_flow=flow,
                supervisor=supervisor,
                stream_callback=None,
                retry_counts={},
                task_board=AsyncMock(),
                dependency_map={},
            )

        assert result == "output"
        supervisor.evaluate_step_result.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_action_treated_as_continue(self):
        """When evaluate returns an unknown action, treat as continue."""
        executor = _make_executor()
        supervisor = _make_supervisor_mock(
            evaluate_return={"action": "unknown_action"}
        )
        subtask = SubTask(
            id="s1", parent_task_id="t1", content="test",
            role_hint="researcher", dependencies=set(), priority=1,
        )
        flow = _make_execution_flow(("s1", 1, "test", "researcher", []))

        with patch.object(executor, '_run_subtask', new_callable=AsyncMock, return_value="output"):
            result = await executor._run_subtask_with_quality_gate(
                task=_make_task(),
                subtask=subtask,
                subtask_map={"s1": subtask},
                subtask_outputs={},
                message_bus=MagicMock(),
                execution_flow=flow,
                supervisor=supervisor,
                stream_callback=None,
                retry_counts={},
                task_board=AsyncMock(),
                dependency_map={},
            )

        assert result == "output"

    @pytest.mark.asyncio
    async def test_no_action_key_defaults_to_continue(self):
        """When evaluate returns dict without 'action' key, default to continue."""
        executor = _make_executor()
        supervisor = _make_supervisor_mock(
            evaluate_return={"quality_score": 8}
        )
        subtask = SubTask(
            id="s1", parent_task_id="t1", content="test",
            role_hint="researcher", dependencies=set(), priority=1,
        )
        flow = _make_execution_flow(("s1", 1, "test", "researcher", []))

        with patch.object(executor, '_run_subtask', new_callable=AsyncMock, return_value="output"):
            result = await executor._run_subtask_with_quality_gate(
                task=_make_task(),
                subtask=subtask,
                subtask_map={"s1": subtask},
                subtask_outputs={},
                message_bus=MagicMock(),
                execution_flow=flow,
                supervisor=supervisor,
                stream_callback=None,
                retry_counts={},
                task_board=AsyncMock(),
                dependency_map={},
            )

        assert result == "output"


class TestQualityGateEndToEnd:
    """Integration-style tests using execute_with_plan with quality gates."""

    @pytest.mark.asyncio
    async def test_execute_with_plan_quality_gate_continue(self):
        """Full execute_with_plan with quality gate returning continue."""
        executor, tlm, task_board_mock, wave_executor = _setup_executor_with_team()
        flow = _make_execution_flow(("s1", 1, "Research", "researcher", []))
        plan = _make_task_plan(flow)
        task = _make_task()
        supervisor = _make_supervisor_mock(
            evaluate_return={"action": "continue"}
        )

        result = await executor.execute_with_plan(task, plan, supervisor=supervisor)

        assert result.success is True
        assert result.metadata == {"task_plan": plan.to_dict()}

    @pytest.mark.asyncio
    async def test_execute_with_plan_no_supervisor_no_quality_gate(self):
        """execute_with_plan without supervisor should not call any quality gate."""
        executor, tlm, task_board_mock, wave_executor = _setup_executor_with_team()
        flow = _make_execution_flow(("s1", 1, "Research", "researcher", []))
        plan = _make_task_plan(flow)
        task = _make_task()

        result = await executor.execute_with_plan(task, plan, supervisor=None)

        assert result.success is True
