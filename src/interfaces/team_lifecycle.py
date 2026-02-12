"""Team Lifecycle Manager interface for Agent Team architecture.

Defines the abstract interface for managing team lifecycle operations
including creation, setup, status querying, and disbanding.

Requirements: 5.1, 5.3, 5.5, 5.6
"""

from abc import ABC, abstractmethod
from typing import List

from ..models.agent import AgentRole
from ..models.task import Task
from ..models.team import DisbandResult, Team, TeamConfig


class ITeamLifecycleManager(ABC):
    """团队生命周期管理器接口

    Manages the complete lifecycle of agent teams from creation to disbanding.
    Responsible for:
    - Creating teams with unique IDs and resource allocation (Req 5.1)
    - Setting up team members based on task requirements
    - Maintaining and querying team state (Req 5.5, 5.6)
    - Disbanding teams and releasing all resources (Req 5.3)
    """

    @abstractmethod
    async def create_team(self, task: Task, config: TeamConfig) -> Team:
        """创建团队

        Creates a new team instance with a unique team ID, task context,
        and resource quota based on the provided configuration.

        Args:
            task: The task that requires team collaboration.
            config: Team configuration including max agents, timeouts, etc.

        Returns:
            A new Team instance in the CREATING state.

        Raises:
            TeamCreationError: If team creation fails.
        """
        pass

    @abstractmethod
    async def setup_team(self, team_id: str, agent_roles: List[AgentRole]) -> None:
        """初始化团队成员

        Initializes the required SubAgent instances based on the provided
        agent roles and registers them to the team's messaging system.

        Args:
            team_id: The unique identifier of the team to set up.
            agent_roles: List of agent role definitions for team members.

        Raises:
            ValueError: If the team_id does not exist.
            TeamCreationError: If member initialization fails.
        """
        pass

    @abstractmethod
    async def get_team_status(self, team_id: str) -> Team:
        """查询团队状态

        Returns the current team state including team ID, current state,
        member list, task progress, and resource usage information.

        Args:
            team_id: The unique identifier of the team to query.

        Returns:
            The Team object containing current state and metadata.

        Raises:
            ValueError: If the team_id does not exist.
        """
        pass

    @abstractmethod
    async def disband_team(self, team_id: str, timeout: float = 30.0) -> DisbandResult:
        """解散团队，释放所有资源

        Terminates all SubAgents in the team, releases message channels,
        and cleans up shared state. The disbanding process follows:
        1. Send shutdown signals to all agents
        2. Wait for graceful termination within timeout
        3. Force-terminate agents that don't respond in time
        4. Clean up all resources

        Args:
            team_id: The unique identifier of the team to disband.
            timeout: Maximum time (in seconds) to wait for graceful
                     agent termination before force-terminating.

        Returns:
            A DisbandResult with details about the disbanding process.

        Raises:
            ValueError: If the team_id does not exist.
        """
        pass
