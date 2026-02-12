"""Team Lifecycle Manager implementation.

Provides the TeamLifecycleManager class that manages the complete lifecycle
of agent teams from creation to disbanding, including member initialization,
state management, and resource cleanup.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from .interfaces.team_lifecycle import ITeamLifecycleManager
from .messaging import MessageBus
from .models.agent import AgentRole
from .models.message import MessageDeliveryStatus
from .models.task import Task
from .models.team import DisbandResult, Team, TeamConfig, TeamState
from .task_board import TaskBoard


logger = logging.getLogger(__name__)


class TeamCreationError(Exception):
    """Raised when team creation fails."""
    pass


class TeamLifecycleManager(ITeamLifecycleManager):
    """团队生命周期管理器实现

    管理团队从创建到销毁的完整生命周期，包括：
    - 创建团队：分配唯一 ID、初始化 MessageBus 和 TaskBoard (Req 5.1)
    - 初始化成员：根据角色创建智能体并注册到消息系统 (Req 5.2)
    - 状态管理：维护团队状态机 (Req 5.5)
    - 解散团队：发送关闭信号 → 等待 → 强制终止 → 清理 (Req 5.3, 5.4)
    - 状态查询：返回团队完整状态信息 (Req 5.6)

    团队状态机：
        creating → ready → executing → completed → disbanded

    Attributes:
        _teams: 团队 ID → Team 的映射
        _message_buses: 团队 ID → MessageBus 的映射
        _task_boards: 团队 ID → TaskBoard 的映射
        _agent_shutdown_events: agent_id → asyncio.Event 的映射，用于跟踪关闭确认
    """

    def __init__(self) -> None:
        """初始化团队生命周期管理器"""
        self._teams: Dict[str, Team] = {}
        self._message_buses: Dict[str, MessageBus] = {}
        self._task_boards: Dict[str, TaskBoard] = {}
        self._agent_shutdown_events: Dict[str, asyncio.Event] = {}

    async def create_team(self, task: Task, config: TeamConfig) -> Team:
        """创建团队

        分配唯一团队 ID，初始化 MessageBus 和 TaskBoard，
        创建 Team 实例并设置为 CREATING 状态。

        Args:
            task: 需要团队协作执行的任务
            config: 团队配置

        Returns:
            新创建的 Team 实例（CREATING 状态）

        Raises:
            TeamCreationError: 如果团队创建过程中发生错误
        """
        team_id = str(uuid.uuid4())

        try:
            # Initialize MessageBus and TaskBoard for this team
            message_bus = MessageBus()
            task_board = TaskBoard()

            # Create Team instance
            team = Team(
                id=team_id,
                task_id=task.id,
                state=TeamState.CREATING,
                config=config,
                members={},
                created_at=time.time(),
            )

            # Store all resources
            self._teams[team_id] = team
            self._message_buses[team_id] = message_bus
            self._task_boards[team_id] = task_board

            logger.info(f"Team {team_id} created for task {task.id}")
            return team

        except Exception as e:
            # Clean up partial resources on failure
            self._message_buses.pop(team_id, None)
            self._task_boards.pop(team_id, None)
            self._teams.pop(team_id, None)
            logger.error(f"Failed to create team: {e}")
            raise TeamCreationError(f"Failed to create team: {e}") from e

    async def setup_team(self, team_id: str, agent_roles: List[AgentRole]) -> None:
        """初始化团队成员

        根据提供的角色列表创建智能体 ID，注册到团队的消息系统，
        并将团队状态从 CREATING 转换为 READY。

        Args:
            team_id: 团队 ID
            agent_roles: 智能体角色定义列表

        Raises:
            ValueError: 如果团队不存在
            TeamCreationError: 如果成员初始化失败
        """
        if team_id not in self._teams:
            raise ValueError(f"Team not found: {team_id}")

        team = self._teams[team_id]
        message_bus = self._message_buses[team_id]

        registered_agents: List[str] = []

        try:
            for role in agent_roles:
                agent_id = f"agent-{uuid.uuid4().hex[:8]}"

                # Register agent to the message bus
                await message_bus.register_agent(agent_id, team_id)

                # Add agent to team members
                team.members[agent_id] = role.name

                # Create shutdown event for tracking graceful termination
                self._agent_shutdown_events[agent_id] = asyncio.Event()

                registered_agents.append(agent_id)

            # Transition to READY state
            team.state = TeamState.READY
            logger.info(
                f"Team {team_id} setup complete with {len(agent_roles)} agents"
            )

        except Exception as e:
            # Clean up partially registered agents
            for agent_id in registered_agents:
                try:
                    await message_bus.unregister_agent(agent_id)
                except Exception:
                    pass
                team.members.pop(agent_id, None)
                self._agent_shutdown_events.pop(agent_id, None)

            logger.error(f"Failed to setup team {team_id}: {e}")
            raise TeamCreationError(
                f"Failed to initialize team members: {e}"
            ) from e

    async def get_team_status(self, team_id: str) -> Team:
        """查询团队状态

        返回团队的完整状态信息，包括团队 ID、当前状态、
        成员列表、任务进度和资源使用情况。

        Args:
            team_id: 团队 ID

        Returns:
            Team 对象，包含当前状态和元数据

        Raises:
            ValueError: 如果团队不存在
        """
        if team_id not in self._teams:
            raise ValueError(f"Team not found: {team_id}")

        return self._teams[team_id]

    async def disband_team(
        self, team_id: str, timeout: float = 30.0
    ) -> DisbandResult:
        """解散团队，释放所有资源

        按以下步骤解散团队：
        1. 发送关闭信号给所有智能体
        2. 等待优雅终止（在 timeout 时间内）
        3. 强制终止未响应的智能体
        4. 清理所有资源（MessageBus、TaskBoard）

        Args:
            team_id: 团队 ID
            timeout: 等待优雅终止的最大时间（秒）

        Returns:
            DisbandResult: 解散结果详情

        Raises:
            ValueError: 如果团队不存在
        """
        if team_id not in self._teams:
            raise ValueError(f"Team not found: {team_id}")

        team = self._teams[team_id]

        # Handle duplicate disband - return already disbanded status
        if team.state == TeamState.DISBANDED:
            return DisbandResult(
                team_id=team_id,
                success=True,
                terminated_agents=0,
                force_terminated_agents=0,
                errors=[],
            )

        errors: List[str] = []
        terminated_count = 0
        force_terminated_count = 0

        message_bus = self._message_buses.get(team_id)
        agent_ids = list(team.members.keys())

        # Step 1: Send shutdown signals to all agents
        if message_bus and agent_ids:
            # Use a "lifecycle-manager" sender ID for shutdown signals
            manager_sender_id = f"lifecycle-manager-{team_id}"

            for agent_id in agent_ids:
                try:
                    result = await message_bus.send_shutdown_request(
                        sender_id=manager_sender_id,
                        target_id=agent_id,
                        reason="Team disbanding",
                    )
                    if result.status == MessageDeliveryStatus.FAILED:
                        # Agent may already be gone, count as terminated
                        terminated_count += 1
                        logger.warning(
                            f"Failed to send shutdown to {agent_id}: {result.error}"
                        )
                except Exception as e:
                    errors.append(
                        f"Error sending shutdown to {agent_id}: {str(e)}"
                    )
                    logger.error(
                        f"Error sending shutdown signal to {agent_id}: {e}"
                    )

        # Step 2: Wait for graceful termination within timeout
        agents_to_force_terminate: List[str] = []

        if agent_ids:
            # Check each agent's shutdown acknowledgment
            # Use a per-agent timeout share of the total timeout
            per_agent_timeout = timeout / max(len(agent_ids), 1)

            for agent_id in agent_ids:
                event = self._agent_shutdown_events.get(agent_id)
                if event is None:
                    # No event means already handled
                    terminated_count += 1
                    continue

                if event.is_set():
                    # Already acknowledged
                    terminated_count += 1
                    continue

                # Wait for this agent with its share of the timeout
                try:
                    await asyncio.wait_for(
                        event.wait(),
                        timeout=per_agent_timeout,
                    )
                    terminated_count += 1
                except asyncio.TimeoutError:
                    agents_to_force_terminate.append(agent_id)
                except Exception as e:
                    errors.append(
                        f"Error waiting for agent {agent_id}: {str(e)}"
                    )
                    agents_to_force_terminate.append(agent_id)

        # Step 3: Force-terminate agents that didn't respond in time
        for agent_id in agents_to_force_terminate:
            try:
                logger.warning(
                    f"Force-terminating agent {agent_id} in team {team_id} "
                    f"(did not respond within timeout)"
                )
                force_terminated_count += 1
            except Exception as e:
                errors.append(
                    f"Error force-terminating {agent_id}: {str(e)}"
                )

        # Step 4: Clean up all resources
        # Unregister all agents from message bus
        if message_bus:
            for agent_id in agent_ids:
                try:
                    await message_bus.unregister_agent(agent_id)
                except Exception as e:
                    errors.append(
                        f"Error unregistering agent {agent_id}: {str(e)}"
                    )

        # Clean up shutdown events
        for agent_id in agent_ids:
            self._agent_shutdown_events.pop(agent_id, None)

        # Remove message bus and task board references
        self._message_buses.pop(team_id, None)
        self._task_boards.pop(team_id, None)

        # Update team state
        team.state = TeamState.DISBANDED
        team.completed_at = time.time()
        team.members.clear()

        logger.info(
            f"Team {team_id} disbanded: {terminated_count} terminated, "
            f"{force_terminated_count} force-terminated"
        )

        return DisbandResult(
            team_id=team_id,
            success=len(errors) == 0,
            terminated_agents=terminated_count,
            force_terminated_agents=force_terminated_count,
            errors=errors,
        )

    # ---- Helper methods ----

    def get_message_bus(self, team_id: str) -> Optional[MessageBus]:
        """获取团队的消息总线

        Args:
            team_id: 团队 ID

        Returns:
            MessageBus 实例，如果团队不存在则返回 None
        """
        return self._message_buses.get(team_id)

    def get_task_board(self, team_id: str) -> Optional[TaskBoard]:
        """获取团队的任务板

        Args:
            team_id: 团队 ID

        Returns:
            TaskBoard 实例，如果团队不存在则返回 None
        """
        return self._task_boards.get(team_id)

    def acknowledge_shutdown(self, agent_id: str) -> None:
        """智能体确认关闭

        由智能体调用以确认已收到关闭信号并完成清理。

        Args:
            agent_id: 智能体 ID
        """
        event = self._agent_shutdown_events.get(agent_id)
        if event:
            event.set()

    def set_team_state(self, team_id: str, state: TeamState) -> None:
        """设置团队状态

        用于外部组件（如 WaveExecutor）更新团队状态。

        Args:
            team_id: 团队 ID
            state: 新的团队状态

        Raises:
            ValueError: 如果团队不存在
        """
        if team_id not in self._teams:
            raise ValueError(f"Team not found: {team_id}")

        team = self._teams[team_id]
        team.state = state

        if state == TeamState.COMPLETED:
            team.completed_at = time.time()
