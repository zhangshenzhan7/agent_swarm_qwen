"""Tests for TaskExecutor.execute_with_plan() and _convert_steps_to_subtasks()."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.main_agent.executor import TaskExecutor
from src.core.supervisor.flow import ExecutionFlow, ExecutionStep, ExecutionStepStatus, TaskPlan
from src.models.task import Task, SubTask
from src.models.result import TaskResult, SubTaskResult
from src.models.enums import TaskStatus
from src.models.team import TeamState, WaveExecutionResult, WaveStats


def _make_execution_flow(*steps_data):
    """Helper to build an ExecutionFlow from (step_id, step_number, description, agent_type, deps) tuples."""
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
    """Helper to build a TaskPlan."""
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


class TestConvertStepsToSubtasks:
    """Tests for _convert_steps_to_subtasks()."""

    def test_single_step_conversion(self):
        flow = _make_execution_flow(
            ("s1", 1, "Do research", "researcher", []),
        )
        executor = _make_executor()
        subtasks, dep_map = executor._convert_steps_to_subtasks(flow, "parent-1")

        assert len(subtasks) == 1
        st = subtasks[0]
        assert st.id == "s1"
        assert st.parent_task_id == "parent-1"
        assert st.content == "Do research"
        assert st.role_hint == "researcher"
        assert st.dependencies == set()
        assert st.priority == 1
        assert st.estimated_complexity == 1.0
        assert dep_map == {"s1": set()}

    def test_multiple_steps_with_dependencies(self):
        flow = _make_execution_flow(
            ("s1", 1, "Research", "researcher", []),
            ("s2", 2, "Analyze", "analyst", ["s1"]),
            ("s3", 3, "Summarize", "summarizer", ["s1", "s2"]),
        )
        executor = _make_executor()
        subtasks, dep_map = executor._convert_steps_to_subtasks(flow, "parent-2")

        assert len(subtasks) == 3
        ids = {st.id for st in subtasks}
        assert ids == {"s1", "s2", "s3"}

        s2 = next(st for st in subtasks if st.id == "s2")
        assert s2.dependencies == {"s1"}
        assert s2.role_hint == "analyst"

        s3 = next(st for st in subtasks if st.id == "s3")
        assert s3.dependencies == {"s1", "s2"}

        assert dep_map["s2"] == {"s1"}
        assert dep_map["s3"] == {"s1", "s2"}

    def test_empty_flow(self):
        flow = ExecutionFlow()
        executor = _make_executor()
        subtasks, dep_map = executor._convert_steps_to_subtasks(flow, "parent-3")
        assert subtasks == []
        assert dep_map == {}


class TestExecuteWithPlan:
    """Tests for execute_with_plan()."""

    @pytest.fixture
    def executor_with_mocks(self):
        """Create executor with fully mocked team lifecycle."""
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
            total_tasks=2,
            completed_tasks=2,
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

    @pytest.mark.asyncio
    async def test_execute_with_plan_publishes_subtasks(self, executor_with_mocks):
        executor, tlm, task_board_mock, wave_executor = executor_with_mocks
        flow = _make_execution_flow(
            ("s1", 1, "Research", "researcher", []),
            ("s2", 2, "Analyze", "analyst", ["s1"]),
        )
        plan = _make_task_plan(flow)
        task = _make_task()

        result = await executor.execute_with_plan(task, plan)

        # Verify subtasks were published to TaskBoard
        task_board_mock.publish_tasks.assert_called_once()
        published_subtasks, published_deps = task_board_mock.publish_tasks.call_args[0]
        assert len(published_subtasks) == 2
        assert published_deps["s2"] == {"s1"}

        # Verify result
        assert result.success is True
        assert result.metadata == {"task_plan": plan.to_dict()}

    @pytest.mark.asyncio
    async def test_execute_with_plan_skips_decomposer(self, executor_with_mocks):
        executor, tlm, task_board_mock, wave_executor = executor_with_mocks
        flow = _make_execution_flow(
            ("s1", 1, "Research", "researcher", []),
        )
        plan = _make_task_plan(flow)
        task = _make_task()

        await executor.execute_with_plan(task, plan)

        # TaskDecomposer should NOT be called
        executor._task_decomposer.decompose.assert_not_called()
        executor._task_decomposer.analyze_complexity.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_with_plan_applies_suggested_agents(self, executor_with_mocks):
        executor, tlm, task_board_mock, wave_executor = executor_with_mocks
        flow = _make_execution_flow(
            ("s1", 1, "Research", "researcher", []),
            ("s2", 2, "Write", "writer", ["s1"]),
        )
        plan = _make_task_plan(flow, suggested_agents=["searcher", "summarizer"])
        task = _make_task()

        await executor.execute_with_plan(task, plan)

        published_subtasks = task_board_mock.publish_tasks.call_args[0][0]
        hints = {st.id: st.role_hint for st in published_subtasks}
        assert hints["s1"] == "searcher"
        assert hints["s2"] == "summarizer"

    @pytest.mark.asyncio
    async def test_execute_with_plan_no_flow_falls_back(self, executor_with_mocks):
        """When execution_flow is None, should fall back to execute()."""
        executor, tlm, task_board_mock, wave_executor = executor_with_mocks
        plan = _make_task_plan(execution_flow=None)
        task = _make_task()

        # Mock the fallback execute() to return a known result
        fallback_result = TaskResult(
            task_id=task.id, success=True, output="fallback",
            error=None, execution_time=0.1,
        )
        with patch.object(executor, 'execute', new_callable=AsyncMock, return_value=fallback_result):
            result = await executor.execute_with_plan(task, plan)

        assert result.output == "fallback"
        # TaskBoard should NOT be used
        task_board_mock.publish_tasks.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_with_plan_stores_plan_in_metadata(self, executor_with_mocks):
        executor, tlm, task_board_mock, wave_executor = executor_with_mocks
        flow = _make_execution_flow(
            ("s1", 1, "Research", "researcher", []),
        )
        plan = _make_task_plan(flow)
        task = _make_task()

        result = await executor.execute_with_plan(task, plan)

        assert "task_plan" in result.metadata
        assert result.metadata["task_plan"]["refined_task"] == "refined task content"

    @pytest.mark.asyncio
    async def test_execute_with_plan_no_team_manager_falls_back(self):
        """When team_lifecycle_manager is None, should fall back to scheduler mode."""
        executor = _make_executor(team_lifecycle_manager=None, wave_executor=None)
        flow = _make_execution_flow(
            ("s1", 1, "Research", "researcher", []),
        )
        plan = _make_task_plan(flow)
        task = _make_task()

        fallback_result = TaskResult(
            task_id=task.id, success=True, output="scheduler fallback",
            error=None, execution_time=0.1,
        )
        with patch.object(executor, '_execute_with_scheduler', new_callable=AsyncMock, return_value=fallback_result):
            result = await executor.execute_with_plan(task, plan)

        assert result.output == "scheduler fallback"
