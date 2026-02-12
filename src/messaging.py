"""P2P Agent Messaging System implementation.

Provides the MessageBus class that manages point-to-point communication
between agents, supporting direct messages, broadcast, and shutdown signals.
Each agent has an asyncio.Queue as its inbox for async non-blocking delivery.
"""

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from .interfaces.messaging import IMessageBus
from .models.message import (
    Message,
    MessageDeliveryResult,
    MessageDeliveryStatus,
    MessageType,
)


# Default maximum inbox size per agent
DEFAULT_MAX_INBOX_SIZE = 1000


class MessageBus(IMessageBus):
    """消息总线实现

    基于 asyncio.Queue 的点对点智能体通信系统。
    支持直接消息、广播和关闭信号。

    Attributes:
        _inboxes: 智能体 ID → asyncio.Queue 的映射（收件箱）
        _agent_teams: 智能体 ID → 团队 ID 的映射
        _team_agents: 团队 ID → 智能体 ID 集合的映射
        _terminated_agents: 已注销的智能体 ID 集合
        _max_inbox_size: 每个智能体收件箱的最大容量
    """

    def __init__(self, max_inbox_size: int = DEFAULT_MAX_INBOX_SIZE) -> None:
        """初始化消息总线

        Args:
            max_inbox_size: 每个智能体收件箱的最大消息数量
        """
        self._inboxes: Dict[str, asyncio.Queue] = {}
        self._agent_teams: Dict[str, str] = {}
        self._team_agents: Dict[str, Set[str]] = {}
        self._terminated_agents: Set[str] = set()
        self._max_inbox_size = max_inbox_size

    async def register_agent(self, agent_id: str, team_id: str) -> None:
        """注册智能体到消息系统

        为智能体创建收件箱并关联到指定团队。
        如果智能体之前被注销过，会从已终止集合中移除。

        Args:
            agent_id: 智能体 ID
            team_id: 所属团队 ID
        """
        # Create inbox for the agent
        self._inboxes[agent_id] = asyncio.Queue(maxsize=self._max_inbox_size)
        # Map agent to team
        self._agent_teams[agent_id] = team_id
        # Add agent to team's member set
        if team_id not in self._team_agents:
            self._team_agents[team_id] = set()
        self._team_agents[team_id].add(agent_id)
        # Remove from terminated set if re-registering
        self._terminated_agents.discard(agent_id)

    async def unregister_agent(self, agent_id: str) -> None:
        """从消息系统注销智能体

        移除智能体的收件箱和团队关联，并将其标记为已终止。

        Args:
            agent_id: 智能体 ID
        """
        # Mark as terminated
        self._terminated_agents.add(agent_id)
        # Remove inbox
        if agent_id in self._inboxes:
            del self._inboxes[agent_id]
        # Remove from team mapping
        team_id = self._agent_teams.pop(agent_id, None)
        if team_id and team_id in self._team_agents:
            self._team_agents[team_id].discard(agent_id)
            # Clean up empty team sets
            if not self._team_agents[team_id]:
                del self._team_agents[team_id]

    def _create_message(
        self,
        sender_id: str,
        receiver_id: str,
        content: Any,
        msg_type: MessageType,
        team_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """创建消息对象

        Args:
            sender_id: 发送者智能体 ID
            receiver_id: 接收者智能体 ID
            content: 消息内容
            msg_type: 消息类型
            team_id: 所属团队 ID
            metadata: 附加元数据

        Returns:
            Message: 新创建的消息对象
        """
        return Message(
            id=str(uuid.uuid4()),
            sender_id=sender_id,
            receiver_id=receiver_id,
            content=content,
            msg_type=msg_type,
            timestamp=time.time(),
            team_id=team_id,
            metadata=metadata or {},
        )

    def _deliver_to_inbox(
        self, agent_id: str, message: Message
    ) -> MessageDeliveryResult:
        """尝试将消息投递到智能体收件箱（同步，非阻塞）

        Args:
            agent_id: 目标智能体 ID
            message: 要投递的消息

        Returns:
            MessageDeliveryResult: 投递结果
        """
        # Check if agent was terminated
        if agent_id in self._terminated_agents:
            return MessageDeliveryResult(
                message_id=message.id,
                status=MessageDeliveryStatus.FAILED,
                error=f"Agent terminated: {agent_id}",
            )
        # Check if agent exists
        if agent_id not in self._inboxes:
            return MessageDeliveryResult(
                message_id=message.id,
                status=MessageDeliveryStatus.FAILED,
                error=f"Agent not found: {agent_id}",
            )
        # Try to put message in inbox (non-blocking)
        try:
            self._inboxes[agent_id].put_nowait(message)
            return MessageDeliveryResult(
                message_id=message.id,
                status=MessageDeliveryStatus.DELIVERED,
            )
        except asyncio.QueueFull:
            return MessageDeliveryResult(
                message_id=message.id,
                status=MessageDeliveryStatus.FAILED,
                error=f"Inbox full for agent: {agent_id}",
            )

    async def send_message(
        self, sender_id: str, receiver_id: str, content: Any, msg_type: MessageType
    ) -> MessageDeliveryResult:
        """发送直接消息

        创建消息并投递到目标智能体的收件箱。

        Args:
            sender_id: 发送者智能体 ID
            receiver_id: 接收者智能体 ID
            content: 消息内容
            msg_type: 消息类型

        Returns:
            MessageDeliveryResult: 投递结果，包含状态和可能的错误信息
        """
        # Determine team_id from sender's registration
        team_id = self._agent_teams.get(sender_id, "")
        message = self._create_message(
            sender_id=sender_id,
            receiver_id=receiver_id,
            content=content,
            msg_type=msg_type,
            team_id=team_id,
        )
        return self._deliver_to_inbox(receiver_id, message)

    async def broadcast(
        self, sender_id: str, team_id: str, content: Any, msg_type: MessageType
    ) -> List[MessageDeliveryResult]:
        """广播消息给团队所有成员

        将消息投递到同一团队内所有其他活跃智能体的收件箱。
        发送者自身不会收到广播消息。

        Args:
            sender_id: 发送者智能体 ID
            team_id: 目标团队 ID
            content: 消息内容
            msg_type: 消息类型

        Returns:
            List[MessageDeliveryResult]: 每个团队成员的投递结果列表
        """
        results: List[MessageDeliveryResult] = []
        team_members = self._team_agents.get(team_id, set())

        for member_id in team_members:
            # Skip the sender
            if member_id == sender_id:
                continue
            message = self._create_message(
                sender_id=sender_id,
                receiver_id=member_id,
                content=content,
                msg_type=msg_type,
                team_id=team_id,
            )
            result = self._deliver_to_inbox(member_id, message)
            results.append(result)

        return results

    async def send_shutdown_request(
        self, sender_id: str, target_id: str, reason: str
    ) -> MessageDeliveryResult:
        """发送关闭请求

        通知目标智能体进入优雅关闭流程。
        消息类型固定为 SHUTDOWN，内容为关闭原因。

        Args:
            sender_id: 发送者智能体 ID
            target_id: 目标智能体 ID
            reason: 关闭原因说明

        Returns:
            MessageDeliveryResult: 投递结果
        """
        team_id = self._agent_teams.get(sender_id, "")
        message = self._create_message(
            sender_id=sender_id,
            receiver_id=target_id,
            content=reason,
            msg_type=MessageType.SHUTDOWN,
            team_id=team_id,
            metadata={"reason": reason},
        )
        return self._deliver_to_inbox(target_id, message)

    async def receive_messages(self, agent_id: str) -> List[Message]:
        """接收智能体收件箱中的所有消息

        获取并清空指定智能体收件箱中的所有待处理消息。
        如果智能体未注册，返回空列表。

        Args:
            agent_id: 智能体 ID

        Returns:
            List[Message]: 收件箱中的消息列表
        """
        if agent_id not in self._inboxes:
            return []

        messages: List[Message] = []
        inbox = self._inboxes[agent_id]
        while not inbox.empty():
            try:
                message = inbox.get_nowait()
                messages.append(message)
            except asyncio.QueueEmpty:
                break

        return messages
