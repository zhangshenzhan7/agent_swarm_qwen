"""全局平台状态"""

import json
from datetime import datetime
from typing import Dict, Any, Optional, List

from fastapi import WebSocket

from src import (
    AgentSwarm,
    Supervisor,
    SupervisorConfig,
    AgentStatus,
    QualityAssurance,
    MemoryManager,
)


class PlatformState:
    def __init__(self):
        self.swarm: Optional[AgentSwarm] = None
        self.supervisor_config: Optional[SupervisorConfig] = None
        self.quality_assurance: Optional[QualityAssurance] = None
        self.memory_manager: Optional[MemoryManager] = None
        self.api_key: Optional[str] = None
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.swarm_tasks: Dict[str, Any] = {}
        self.agents: Dict[str, Dict[str, Any]] = {}
        self.active_agents: Dict[str, Dict[str, Any]] = {}
        self.active_supervisors: Dict[str, Supervisor] = {}
        self.agent_counter: Dict[str, int] = {}
        self.websockets: List[WebSocket] = []
        self.execution_logs: Dict[str, List[Dict[str, Any]]] = {}
        self.agent_logs: Dict[str, List[Dict[str, Any]]] = {}
        self.agent_streams: Dict[str, str] = {}
        self.subtask_flows: Dict[str, Dict[str, Any]] = {}
        self.subtask_results: Dict[str, Dict[str, Any]] = {}
        self.quality_reports: Dict[str, Dict[str, Any]] = {}
        self.execution_mode: str = "scheduler"  # 'scheduler' 或 'team'
        # 沙箱代码解释器配置
        self.sandbox_account_id: Optional[str] = None
        self.sandbox_region_id: str = "cn-hangzhou"
        self.sandbox_template_name: str = "python-sandbox"
        self.sandbox_idle_timeout: int = 3600
        self.sandbox_access_key_id: Optional[str] = None
        self.sandbox_access_key_secret: Optional[str] = None
        # 任务与 agent 实例的映射关系
        self.task_agent_map: Dict[str, List[str]] = {}  # task_id -> [agent_id, ...]
        self.agent_task_map: Dict[str, str] = {}  # agent_id -> task_id
        # 任务取消与执行追踪
        self.cancelled_tasks: set = set()  # 已取消的 task_id 集合
        self.running_async_tasks: Dict[str, Any] = {}  # task_id -> asyncio.Task

    def create_supervisor_instance(self, task_id: str) -> Supervisor:
        """为任务创建独立的 Supervisor 实例"""
        if not self.swarm or not self.supervisor_config:
            raise RuntimeError("Swarm 或 Supervisor 配置未初始化")
        supervisor = Supervisor(
            qwen_client=self.swarm.qwen_client,
            config=self.supervisor_config,
        )
        self.active_supervisors[task_id] = supervisor
        return supervisor

    def release_supervisor_instance(self, task_id: str):
        if task_id in self.active_supervisors:
            del self.active_supervisors[task_id]

    def create_agent_instance(self, role_key: str, task_description: str = "") -> Dict[str, Any]:
        """动态创建 Agent 实例"""
        if role_key not in self.agent_counter:
            self.agent_counter[role_key] = 0
        self.agent_counter[role_key] += 1

        instance_num = self.agent_counter[role_key]
        instance_id = f"agent_{role_key}_{instance_num}"

        base_agent = self.agents.get(f"agent_{role_key}", {})
        if role_key == "supervisor":
            base_agent = self.agents.get("supervisor", {})

        agent_instance = {
            "id": instance_id,
            "name": f"{base_agent.get('name', role_key)} #{instance_num}",
            "role": role_key,
            "instance_num": instance_num,
            "description": base_agent.get("description", ""),
            "status": AgentStatus.IDLE.value,
            "avatar": base_agent.get("avatar", "🤖"),
            "current_task": task_description[:50] + "..." if len(task_description) > 50 else task_description,
            "tools": base_agent.get("tools", []),
            "stats": {"tasks_completed": 0, "total_time": 0, "success_rate": 100},
            "is_instance": True,
            "parent_id": f"agent_{role_key}" if role_key != "supervisor" else "supervisor",
        }

        self.active_agents[instance_id] = agent_instance
        return agent_instance

    def release_agent_instance(self, instance_id: str):
        if instance_id in self.active_agents:
            del self.active_agents[instance_id]

    def bind_agent_to_task(self, agent_id: str, task_id: str):
        """绑定 agent 实例到任务"""
        if task_id not in self.task_agent_map:
            self.task_agent_map[task_id] = []
        if agent_id not in self.task_agent_map[task_id]:
            self.task_agent_map[task_id].append(agent_id)
        self.agent_task_map[agent_id] = task_id

    def get_task_for_agent(self, agent_id: str) -> Optional[str]:
        """获取 agent 所属的 task_id"""
        return self.agent_task_map.get(agent_id)

    def get_active_agents_by_role(self, role_key: str) -> List[Dict[str, Any]]:
        return [
            agent for agent in self.active_agents.values()
            if agent.get("role") == role_key and agent.get("status") == AgentStatus.RUNNING.value
        ]

    def get_all_agents(self) -> List[Dict[str, Any]]:
        all_agents = list(self.agents.values())
        all_agents.extend(self.active_agents.values())
        return all_agents

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        message = json.dumps({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }, ensure_ascii=False, default=str)
        disconnected = []
        for ws in self.websockets:
            try:
                await ws.send_text(message)
            except:
                disconnected.append(ws)
        for ws in disconnected:
            if ws in self.websockets:
                self.websockets.remove(ws)


state = PlatformState()
