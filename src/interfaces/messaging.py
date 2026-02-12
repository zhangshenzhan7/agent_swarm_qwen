"""Message Bus interface for P2P agent communication.

Defines the abstract interface for the Agent Messaging System,
supporting direct messages, broadcast, and shutdown signals.
"""

from abc import ABC, abstractmethod
from typing import Any, List

from ..models.message import Message, MessageDeliveryResult, MessageType


class IMessageBus(ABC):
    """消息总线接口

    管理智能体间的点对点通信，支持直接消息、广播和关闭信号。
    每个智能体拥有一个收件箱，消息投递为异步非阻塞操作。
    """

    @abstractmethod
    async def send_message(
        self, sender_id: str, receiver_id: str, content: Any, msg_type: MessageType
    ) -> MessageDeliveryResult:
        """发送直接消息

        Args:
            sender_id: 发送者智能体 ID
            receiver_id: 接收者智能体 ID
            content: 消息内容
            msg_type: 消息类型

        Returns:
            MessageDeliveryResult: 投递结果，包含状态和可能的错误信息
        """
        pass

    @abstractmethod
    async def broadcast(
        self, sender_id: str, team_id: str, content: Any, msg_type: MessageType
    ) -> List[MessageDeliveryResult]:
        """广播消息给团队所有成员

        将消息投递到同一团队内所有其他活跃智能体的收件箱。

        Args:
            sender_id: 发送者智能体 ID
            team_id: 目标团队 ID
            content: 消息内容
            msg_type: 消息类型

        Returns:
            List[MessageDeliveryResult]: 每个团队成员的投递结果列表
        """
        pass

    @abstractmethod
    async def send_shutdown_request(
        self, sender_id: str, target_id: str, reason: str
    ) -> MessageDeliveryResult:
        """发送关闭请求

        通知目标智能体进入优雅关闭流程。

        Args:
            sender_id: 发送者智能体 ID
            target_id: 目标智能体 ID
            reason: 关闭原因说明

        Returns:
            MessageDeliveryResult: 投递结果
        """
        pass

    @abstractmethod
    async def receive_messages(self, agent_id: str) -> List[Message]:
        """接收智能体收件箱中的所有消息

        获取并清空指定智能体收件箱中的所有待处理消息。

        Args:
            agent_id: 智能体 ID

        Returns:
            List[Message]: 收件箱中的消息列表
        """
        pass

    @abstractmethod
    async def register_agent(self, agent_id: str, team_id: str) -> None:
        """注册智能体到消息系统

        为智能体创建收件箱并关联到指定团队。

        Args:
            agent_id: 智能体 ID
            team_id: 所属团队 ID
        """
        pass

    @abstractmethod
    async def unregister_agent(self, agent_id: str) -> None:
        """从消息系统注销智能体

        移除智能体的收件箱和团队关联。

        Args:
            agent_id: 智能体 ID
        """
        pass
