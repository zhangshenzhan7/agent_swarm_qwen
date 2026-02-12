"""Enumeration types for Qwen Agent Swarm."""

from enum import Enum


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    ANALYZING = "analyzing"
    DECOMPOSING = "decomposing"
    EXECUTING = "executing"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentStatus(Enum):
    """智能体状态枚举"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"

class OutputType(Enum):
    """输出类型枚举"""
    REPORT = "report"
    CODE = "code"
    WEBSITE = "website"
    IMAGE = "image"
    VIDEO = "video"
    DATASET = "dataset"
    DOCUMENT = "document"
    COMPOSITE = "composite"

