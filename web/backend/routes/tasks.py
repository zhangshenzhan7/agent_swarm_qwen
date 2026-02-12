"""任务管理路由"""

import asyncio
import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, HTTPException

from src import TaskStatus
from src.models.enums import OutputType
from state import state
from models import TaskCreate, TaskCreateWithFiles
from utils import get_recommended_roles_for_files

VALID_OUTPUT_TYPES = [t.value for t in OutputType]

router = APIRouter()


@router.get("/api/agents")
async def list_agents():
    return state.get_all_agents()


@router.post("/api/tasks")
async def create_task(task_data: TaskCreate):
    from execution.supervisor_flow import execute_task_with_supervisor

    # "auto" 表示由主管自动判断，先默认 report，后续由 Supervisor 覆盖
    effective_output_type = task_data.output_type
    if effective_output_type == "auto":
        effective_output_type = "report"
    elif effective_output_type not in VALID_OUTPUT_TYPES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Invalid output_type: '{task_data.output_type}'",
                "available_types": ["auto"] + VALID_OUTPUT_TYPES,
            },
        )

    task_id = f"task_{uuid.uuid4().hex[:8]}"
    task_info = {
        "id": task_id,
        "content": task_data.content,
        "output_type": effective_output_type,
        "status": TaskStatus.PENDING.value,
        "created_at": datetime.now().isoformat(),
        "stages": [
            {"name": "主管规划", "status": "pending"},
            {"name": "任务分析", "status": "pending"},
            {"name": "任务分解", "status": "pending"},
            {"name": "智能体分配", "status": "pending"},
            {"name": "并行执行", "status": "pending"},
            {"name": "结果聚合", "status": "pending"},
        ],
        "assigned_agents": [],
        "progress": {"percentage": 0, "current_stage": "pending"},
        "metadata": task_data.metadata or {},
        "decision": None,
        "files": [],
    }
    state.tasks[task_id] = task_info
    state.execution_logs[task_id] = []
    await state.broadcast("task_created", task_info)
    bg_task = asyncio.create_task(execute_task_with_supervisor(task_id, task_data.content, task_data.metadata))
    state.running_async_tasks[task_id] = bg_task
    return task_info


@router.post("/api/tasks/with-files")
async def create_task_with_files(task_data: TaskCreateWithFiles):
    from execution.supervisor_flow import execute_task_with_supervisor
    from file_parser import extract_file_content

    # "auto" 表示由主管自动判断，先默认 report，后续由 Supervisor 覆盖
    effective_output_type = task_data.output_type
    if effective_output_type == "auto":
        effective_output_type = "report"
    elif effective_output_type not in VALID_OUTPUT_TYPES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Invalid output_type: '{task_data.output_type}'",
                "available_types": ["auto"] + VALID_OUTPUT_TYPES,
            },
        )

    task_id = f"task_{uuid.uuid4().hex[:8]}"
    files = task_data.files or []
    recommended_roles = get_recommended_roles_for_files(files) if files else []

    file_contents = []
    file_descriptions = []
    for f in files:
        file_type = f.get("type", "unknown")
        file_name = f.get("name", "unnamed")
        file_path = f.get("path", "")
        file_descriptions.append(f"- {file_name} ({file_type})")
        if file_path and os.path.exists(file_path):
            extract_result = extract_file_content(file_path, file_type)
            if extract_result.get("success") and extract_result.get("text"):
                file_contents.append({
                    "name": file_name,
                    "type": file_type,
                    "content": extract_result["text"],
                    "metadata": extract_result.get("metadata", {}),
                })

    enhanced_content = task_data.content
    if files:
        file_list = "\n".join(file_descriptions)
        file_summaries = [f"- {fc['name']}: {len(fc['content'])} 字符" for fc in file_contents]
        file_summary_text = "\n".join(file_summaries) if file_summaries else "（无法提取文件内容）"
        enhanced_content = f"""{task_data.content}

## 附件文件
{file_list}

## 文件信息摘要
{file_summary_text}

## 重要提示
- 这是一个需要分析附件文件的任务
- 文件内容已提取，将传递给执行任务的子智能体
- 请根据任务需求分配合适的智能体（如 document_analyst, researcher 等）
"""

    metadata = task_data.metadata or {}
    metadata["files"] = files
    metadata["recommended_roles"] = recommended_roles
    metadata["has_files"] = len(files) > 0
    metadata["file_types"] = list(set(f.get("type", "") for f in files))
    metadata["file_contents"] = file_contents

    task_info = {
        "id": task_id,
        "content": task_data.content,
        "enhanced_content": enhanced_content,
        "output_type": effective_output_type,
        "status": TaskStatus.PENDING.value,
        "created_at": datetime.now().isoformat(),
        "stages": [
            {"name": "主管规划", "status": "pending"},
            {"name": "任务分析", "status": "pending"},
            {"name": "任务分解", "status": "pending"},
            {"name": "智能体分配", "status": "pending"},
            {"name": "并行执行", "status": "pending"},
            {"name": "结果聚合", "status": "pending"},
        ],
        "assigned_agents": [],
        "progress": {"percentage": 0, "current_stage": "pending"},
        "metadata": metadata,
        "decision": None,
        "files": files,
        "recommended_roles": recommended_roles,
    }
    state.tasks[task_id] = task_info
    state.execution_logs[task_id] = []
    await state.broadcast("task_created", task_info)
    bg_task = asyncio.create_task(execute_task_with_supervisor(task_id, enhanced_content, metadata))
    state.running_async_tasks[task_id] = bg_task
    return task_info


@router.get("/api/tasks")
async def list_tasks():
    return list(state.tasks.values())


@router.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    if task_id not in state.tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return state.tasks[task_id]


@router.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    if task_id not in state.tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    # 标记任务为已取消，让执行循环自行退出
    state.cancelled_tasks.add(task_id)
    # 取消正在运行的 asyncio.Task
    if task_id in state.running_async_tasks:
        async_task = state.running_async_tasks[task_id]
        if not async_task.done():
            async_task.cancel()
        del state.running_async_tasks[task_id]
    if task_id in state.swarm_tasks:
        try:
            swarm_task = state.swarm_tasks[task_id]
            await state.swarm.cancel_task(swarm_task.id)
        except:
            pass
        del state.swarm_tasks[task_id]
    # 释放该任务绑定的所有 agent 实例
    bound_agents = list(state.task_agent_map.get(task_id, []))
    for agent_id in bound_agents:
        if agent_id in state.active_agents:
            state.active_agents[agent_id]["status"] = "idle"
            await state.broadcast("agent_updated", state.active_agents[agent_id])
            state.release_agent_instance(agent_id)
            await state.broadcast("agent_removed", {"id": agent_id})
        state.agent_task_map.pop(agent_id, None)
    state.task_agent_map.pop(task_id, None)
    del state.tasks[task_id]
    if task_id in state.execution_logs:
        del state.execution_logs[task_id]
    state.release_supervisor_instance(task_id)
    await state.broadcast("task_deleted", {"task_id": task_id})
    return {"message": "Task deleted"}


@router.get("/api/agents/{agent_id}/logs")
async def get_agent_logs(agent_id: str):
    if agent_id not in state.agents and agent_id not in state.active_agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {
        "agent_id": agent_id,
        "logs": state.agent_logs.get(agent_id, []),
        "current_stream": state.agent_streams.get(agent_id, ""),
    }


@router.get("/api/tasks/{task_id}/flow")
async def get_task_flow(task_id: str):
    if task_id not in state.tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = state.tasks[task_id]
    flow_data = state.subtask_flows.get(task_id, {})

    if task.get("plan") and task["plan"].get("execution_flow"):
        exec_flow = task["plan"]["execution_flow"]
        steps = exec_flow.get("steps", {})
        for step_id, step in steps.items():
            if step_id in state.subtask_results:
                result = state.subtask_results[step_id]
                step["output_data"] = result.get("output_data")
                step["error"] = result.get("error")
                step["agent_id"] = result.get("agent_id")
                step["agent_name"] = result.get("agent_name")
                step["logs"] = result.get("logs", [])
        result = {
            "task_id": task_id,
            "steps": steps,
            "execution_order": exec_flow.get("execution_order", []),
            "progress": exec_flow.get("progress", {"total": len(steps), "completed": 0, "running": 0, "failed": 0, "progress_percent": 0}),
        }
        if task.get("wave_execution"):
            result["wave_execution"] = task["wave_execution"]
        return result

    return {
        "task_id": task_id,
        "steps": flow_data.get("steps", {}),
        "execution_order": flow_data.get("execution_order", []),
        "progress": flow_data.get("progress", {"total": 0, "completed": 0, "running": 0, "failed": 0, "progress_percent": 0}),
    }


@router.get("/api/tasks/{task_id}/flow/{step_id}")
async def get_step_detail(task_id: str, step_id: str):
    if task_id not in state.tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = state.tasks[task_id]
    if task.get("plan") and task["plan"].get("execution_flow"):
        steps = task["plan"]["execution_flow"].get("steps", {})
        if step_id in steps:
            step = steps[step_id]
            if step_id in state.subtask_results:
                result = state.subtask_results[step_id]
                step["output_data"] = result.get("output_data")
                step["error"] = result.get("error")
                step["agent_id"] = result.get("agent_id")
                step["agent_name"] = result.get("agent_name")
                step["logs"] = result.get("logs", [])
            return step
    raise HTTPException(status_code=404, detail="Step not found")


@router.get("/api/stats")
async def get_platform_stats():
    total = len(state.tasks)
    completed = sum(1 for t in state.tasks.values() if t["status"] == "completed")
    failed = sum(1 for t in state.tasks.values() if t["status"] == "failed")
    running = sum(1 for t in state.tasks.values() if t["status"] in ["executing", "analyzing", "decomposing", "aggregating"])
    active = sum(1 for a in state.agents.values() if a["status"] == "running")
    success_rate = (completed / (completed + failed) * 100) if (completed + failed) > 0 else 100
    memory_stats = state.memory_manager.get_stats() if state.memory_manager else {}
    quality_stats = {"total_reports": len(state.quality_reports), "avg_score": 0}
    if state.quality_reports:
        scores = [r.get("score", 0) for r in state.quality_reports.values()]
        quality_stats["avg_score"] = round(sum(scores) / len(scores), 1) if scores else 0
    return {
        "total_tasks": total, "completed_tasks": completed, "failed_tasks": failed,
        "running_tasks": running, "pending_tasks": total - completed - failed - running,
        "total_agents": len(state.agents), "active_agents": active,
        "success_rate": round(success_rate, 1), "memory": memory_stats, "quality": quality_stats,
    }


@router.get("/api/tasks/{task_id}/research-tree")
async def get_research_tree(task_id: str):
    if task_id not in state.tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = state.tasks[task_id]
    return {
        "task_id": task_id,
        "research_tree": task.get("research_tree"),
        "mode": task.get("mode", "standard"),
    }
