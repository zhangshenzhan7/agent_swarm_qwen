"""Execution context data models."""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import threading

from .enums import TaskStatus
from .agent import SubAgent
from .result import SubTaskResult


@dataclass
class ExecutionContext:
    """执行上下文"""
    task_id: str
    start_time: float
    status: TaskStatus
    sub_agents: Dict[str, SubAgent] = field(default_factory=dict)
    subtask_results: Dict[str, SubTaskResult] = field(default_factory=dict)
    tool_call_count: int = 0
    shared_data: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "task_id": self.task_id,
            "start_time": self.start_time,
            "status": self.status.value,
            "sub_agents": {
                agent_id: agent.to_dict() 
                for agent_id, agent in self.sub_agents.items()
            },
            "subtask_results": {
                subtask_id: result.to_dict()
                for subtask_id, result in self.subtask_results.items()
            },
            "tool_call_count": self.tool_call_count,
            "shared_data": self.shared_data,
            "errors": self.errors,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionContext":
        """从字典反序列化"""
        return cls(
            task_id=data["task_id"],
            start_time=data["start_time"],
            status=TaskStatus(data["status"]),
            sub_agents={
                agent_id: SubAgent.from_dict(agent_data)
                for agent_id, agent_data in data.get("sub_agents", {}).items()
            },
            subtask_results={
                subtask_id: SubTaskResult.from_dict(result_data)
                for subtask_id, result_data in data.get("subtask_results", {}).items()
            },
            tool_call_count=data.get("tool_call_count", 0),
            shared_data=data.get("shared_data", {}),
            errors=data.get("errors", []),
        )


class ThreadSafeExecutionContext:
    """线程安全的执行上下文包装器"""
    
    def __init__(self, context: ExecutionContext):
        self._context = context
        self._lock = threading.RLock()
    
    @property
    def task_id(self) -> str:
        return self._context.task_id
    
    @property
    def start_time(self) -> float:
        return self._context.start_time
    
    @property
    def status(self) -> TaskStatus:
        with self._lock:
            return self._context.status
    
    @status.setter
    def status(self, value: TaskStatus) -> None:
        with self._lock:
            self._context.status = value
    
    @property
    def tool_call_count(self) -> int:
        with self._lock:
            return self._context.tool_call_count
    
    def increment_tool_calls(self, count: int = 1) -> int:
        """增加工具调用计数，返回新的总数"""
        with self._lock:
            self._context.tool_call_count += count
            return self._context.tool_call_count
    
    def register_agent(self, agent: SubAgent) -> None:
        """注册子智能体"""
        with self._lock:
            self._context.sub_agents[agent.id] = agent
    
    def get_agent(self, agent_id: str) -> Optional[SubAgent]:
        """获取子智能体"""
        with self._lock:
            return self._context.sub_agents.get(agent_id)
    
    def get_all_agents(self) -> Dict[str, SubAgent]:
        """获取所有子智能体"""
        with self._lock:
            return dict(self._context.sub_agents)
    
    def update_agent_status(self, agent_id: str, status: "AgentStatus") -> bool:
        """更新子智能体状态"""
        from .enums import AgentStatus
        with self._lock:
            if agent_id in self._context.sub_agents:
                self._context.sub_agents[agent_id].status = status
                return True
            return False
    
    def record_result(self, result: SubTaskResult) -> None:
        """记录子任务结果"""
        with self._lock:
            self._context.subtask_results[result.subtask_id] = result
    
    def get_result(self, subtask_id: str) -> Optional[SubTaskResult]:
        """获取子任务结果"""
        with self._lock:
            return self._context.subtask_results.get(subtask_id)
    
    def get_all_results(self) -> Dict[str, SubTaskResult]:
        """获取所有子任务结果"""
        with self._lock:
            return dict(self._context.subtask_results)
    
    def set_shared_data(self, key: str, value: Any) -> None:
        """设置共享数据"""
        with self._lock:
            self._context.shared_data[key] = value
    
    def get_shared_data(self, key: str) -> Optional[Any]:
        """获取共享数据"""
        with self._lock:
            return self._context.shared_data.get(key)
    
    def add_error(self, error: Dict[str, Any]) -> None:
        """添加错误记录"""
        with self._lock:
            self._context.errors.append(error)
    
    def get_errors(self) -> List[Dict[str, Any]]:
        """获取所有错误"""
        with self._lock:
            return list(self._context.errors)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        with self._lock:
            return self._context.to_dict()
    
    def get_raw_context(self) -> ExecutionContext:
        """获取原始上下文（非线程安全）"""
        return self._context
