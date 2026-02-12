"""员工管理（Agent Registry）路由"""

import uuid
from typing import List

from fastapi import APIRouter, HTTPException

from src.models.agent_registry import (
    get_registry,
    RegisteredAgent,
    ModelConfig,
    AgentType,
    AgentCapability,
    MULTIMODAL_AGENT_TEMPLATES,
    create_agent_from_template,
)
from state import state
from models import AgentCreate, AgentUpdate

router = APIRouter()


@router.get("/api/registry/agents")
async def list_registered_agents(include_disabled: bool = False):
    registry = get_registry()
    agents = registry.list_all(include_disabled=include_disabled)
    return {"agents": [a.to_dict() for a in agents], "total": len(agents)}


@router.get("/api/registry/agents/{agent_id}")
async def get_registered_agent(agent_id: str):
    registry = get_registry()
    agent = registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent.to_dict()


@router.post("/api/registry/agents")
async def create_agent(data: AgentCreate):
    registry = get_registry()
    agent_id = f"custom_{data.role_key}_{uuid.uuid4().hex[:8]}"
    capabilities = []
    for cap in data.capabilities:
        try:
            capabilities.append(AgentCapability(cap))
        except ValueError:
            pass
    agent = RegisteredAgent(
        id=agent_id, name=data.name, role_key=data.role_key,
        description=data.description, agent_type=AgentType(data.agent_type),
        capabilities=capabilities,
        model_config=ModelConfig(model_id=data.model_id, temperature=data.temperature),
        system_prompt=data.system_prompt, avatar=data.avatar,
        available_tools=data.available_tools, is_enabled=True, is_builtin=False,
        priority=data.priority, tags=data.tags,
    )
    if registry.register(agent):
        state.agents[f"agent_{data.role_key}"] = {
            "id": f"agent_{data.role_key}", "name": data.name, "role": data.role_key,
            "description": data.description, "status": "idle", "avatar": data.avatar,
            "current_task": None, "tools": data.available_tools,
            "stats": {"tasks_completed": 0, "total_time": 0, "success_rate": 100},
            "is_custom": True,
        }
        await state.broadcast("agent_registered", agent.to_dict())
        return {"success": True, "agent": agent.to_dict()}
    raise HTTPException(status_code=400, detail="Agent already exists")


@router.post("/api/registry/agents/from-template")
async def create_agent_from_template_api(template_key: str):
    agent = create_agent_from_template(template_key)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Template '{template_key}' not found")
    registry = get_registry()
    if registry.register(agent):
        state.agents[f"agent_{agent.role_key}"] = {
            "id": f"agent_{agent.role_key}", "name": agent.name, "role": agent.role_key,
            "description": agent.description, "status": "idle", "avatar": agent.avatar,
            "current_task": None, "tools": agent.available_tools,
            "stats": {"tasks_completed": 0, "total_time": 0, "success_rate": 100},
            "is_custom": True, "agent_type": agent.agent_type.value,
        }
        await state.broadcast("agent_registered", agent.to_dict())
        return {"success": True, "agent": agent.to_dict()}
    raise HTTPException(status_code=400, detail="Failed to register agent")


@router.put("/api/registry/agents/{agent_id}")
async def update_agent(agent_id: str, data: AgentUpdate):
    registry = get_registry()
    updates = {}
    for field in ["name", "description", "system_prompt", "avatar", "available_tools", "is_enabled", "priority", "tags"]:
        val = getattr(data, field, None)
        if val is not None:
            updates[field] = val
    if data.model_id is not None or data.temperature is not None:
        agent = registry.get(agent_id)
        if agent:
            model_cfg = agent.model_config.to_dict()
            if data.model_id is not None:
                model_cfg["model_id"] = data.model_id
            if data.temperature is not None:
                model_cfg["temperature"] = data.temperature
            updates["model_config"] = model_cfg
    if registry.update(agent_id, updates):
        agent = registry.get(agent_id)
        await state.broadcast("agent_updated", agent.to_dict())
        return {"success": True, "agent": agent.to_dict()}
    raise HTTPException(status_code=404, detail="Agent not found")


@router.delete("/api/registry/agents/{agent_id}")
async def delete_agent(agent_id: str):
    registry = get_registry()
    agent = registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if registry.unregister(agent_id):
        agent_key = f"agent_{agent.role_key}"
        if agent_key in state.agents and not agent.is_builtin:
            del state.agents[agent_key]
        await state.broadcast("agent_unregistered", {"id": agent_id, "is_builtin": agent.is_builtin})
        return {"success": True, "message": "Agent disabled" if agent.is_builtin else "Agent removed"}
    raise HTTPException(status_code=400, detail="Failed to remove agent")


@router.post("/api/registry/agents/{agent_id}/enable")
async def enable_agent(agent_id: str):
    registry = get_registry()
    if registry.enable(agent_id):
        agent = registry.get(agent_id)
        await state.broadcast("agent_enabled", agent.to_dict())
        return {"success": True}
    raise HTTPException(status_code=404, detail="Agent not found")


@router.post("/api/registry/agents/{agent_id}/disable")
async def disable_agent(agent_id: str):
    registry = get_registry()
    if registry.disable(agent_id):
        agent = registry.get(agent_id)
        await state.broadcast("agent_disabled", agent.to_dict())
        return {"success": True}
    raise HTTPException(status_code=404, detail="Agent not found")


@router.get("/api/registry/templates")
async def list_agent_templates():
    templates = []
    for key, template in MULTIMODAL_AGENT_TEMPLATES.items():
        templates.append({
            "key": key, "name": template["name"], "description": template["description"],
            "agent_type": template["agent_type"].value,
            "capabilities": [c.value for c in template["capabilities"]],
            "avatar": template.get("avatar", "🤖"), "tags": template.get("tags", []),
        })
    return {"templates": templates}


@router.get("/api/registry/capabilities")
async def list_capabilities():
    return {"capabilities": [{"value": c.value, "name": c.name} for c in AgentCapability]}


@router.get("/api/registry/agent-types")
async def list_agent_types():
    return {"types": [{"value": t.value, "name": t.name} for t in AgentType]}
