"""Result-related data models."""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from .tool import ToolCallRecord


@dataclass
class SubTaskResult:
    """子任务执行结果"""
    subtask_id: str
    agent_id: str
    success: bool
    output: Any
    error: Optional[str]
    tool_calls: List[ToolCallRecord]
    execution_time: float
    token_usage: Dict[str, int] = field(default_factory=dict)
    output_type: str = "report"
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "subtask_id": self.subtask_id,
            "agent_id": self.agent_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "tool_calls": [
                {
                    "id": tc.id,
                    "tool_name": tc.tool_name,
                    "arguments": tc.arguments,
                    "result": tc.result,
                    "success": tc.success,
                    "error": tc.error,
                    "start_time": tc.start_time,
                    "end_time": tc.end_time,
                    "agent_id": tc.agent_id,
                }
                for tc in self.tool_calls
            ],
            "execution_time": self.execution_time,
            "token_usage": self.token_usage,
            "output_type": self.output_type,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubTaskResult":
        """从字典反序列化"""
        return cls(
            subtask_id=data["subtask_id"],
            agent_id=data["agent_id"],
            success=data["success"],
            output=data["output"],
            error=data.get("error"),
            tool_calls=[
                ToolCallRecord(
                    id=tc["id"],
                    tool_name=tc["tool_name"],
                    arguments=tc["arguments"],
                    result=tc["result"],
                    success=tc["success"],
                    error=tc.get("error"),
                    start_time=tc["start_time"],
                    end_time=tc["end_time"],
                    agent_id=tc["agent_id"],
                )
                for tc in data.get("tool_calls", [])
            ],
            execution_time=data["execution_time"],
            token_usage=data.get("token_usage", {}),
            output_type=data.get("output_type", "report"),
        )


@dataclass
class TaskResult:
    """任务结果数据结构"""
    task_id: str
    success: bool
    output: Any
    error: Optional[str]
    execution_time: float
    sub_results: List[SubTaskResult] = field(default_factory=list)
    output_type: str = "report"
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "task_id": self.task_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "execution_time": self.execution_time,
            "sub_results": [sr.to_dict() for sr in self.sub_results],
            "output_type": self.output_type,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskResult":
        """从字典反序列化"""
        return cls(
            task_id=data["task_id"],
            success=data["success"],
            output=data["output"],
            error=data.get("error"),
            execution_time=data["execution_time"],
            sub_results=[
                SubTaskResult.from_dict(sr) for sr in data.get("sub_results", [])
            ],
            output_type=data.get("output_type", "report"),
        )
