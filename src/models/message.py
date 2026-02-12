"""Message-related data models for Agent Messaging System.

Defines the core data structures for P2P agent communication,
including message types, delivery status, and serialization support.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class MessageType(Enum):
    """消息类型枚举"""
    DIRECT = "direct"
    BROADCAST = "broadcast"
    SHUTDOWN = "shutdown"


class MessageDeliveryStatus(Enum):
    """消息投递状态枚举"""
    DELIVERED = "delivered"
    FAILED = "failed"


@dataclass
class Message:
    """消息数据结构

    Attributes:
        id: 唯一消息 ID
        sender_id: 发送者智能体 ID
        receiver_id: 接收者智能体 ID（广播时为团队 ID）
        content: 消息内容
        msg_type: 消息类型
        timestamp: 发送时间戳
        team_id: 所属团队 ID
        metadata: 附加元数据
    """
    id: str
    sender_id: str
    receiver_id: str
    content: Any
    msg_type: MessageType
    timestamp: float
    team_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "id": self.id,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "content": self.content,
            "msg_type": self.msg_type.value,
            "timestamp": self.timestamp,
            "team_id": self.team_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """从字典反序列化"""
        return cls(
            id=data["id"],
            sender_id=data["sender_id"],
            receiver_id=data["receiver_id"],
            content=data["content"],
            msg_type=MessageType(data["msg_type"]),
            timestamp=data["timestamp"],
            team_id=data["team_id"],
            metadata=data.get("metadata", {}),
        )


@dataclass
class MessageDeliveryResult:
    """消息投递结果

    Attributes:
        message_id: 消息 ID
        status: 投递状态
        error: 错误信息（投递失败时）
    """
    message_id: str
    status: MessageDeliveryStatus
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "message_id": self.message_id,
            "status": self.status.value,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageDeliveryResult":
        """从字典反序列化"""
        return cls(
            message_id=data["message_id"],
            status=MessageDeliveryStatus(data["status"]),
            error=data.get("error"),
        )
