"""自适应编排路由"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter

from src import TaskStatus
from state import state
from models import TaskCreate

router = APIRouter()


@router.post("/api/tasks/adaptive")
async def create_adaptive_task(task_data: TaskCreate):
    from execution.adaptive import execute_adaptive_task

    task_id = f"adaptive_{uuid.uuid4().hex[:8]}"
    task_info = {
        "id": task_id,
        "content": task_data.content,
        "status": TaskStatus.PENDING.value,
        "created_at": datetime.now().isoformat(),
        "mode": "adaptive",
        "stages": [
            {"name": "自适应规划", "status": "pending"},
            {"name": "并行研究", "status": "pending"},
            {"name": "实时编排", "status": "pending"},
            {"name": "结果聚合", "status": "pending"},
        ],
        "assigned_agents": [],
        "progress": {"percentage": 0, "current_stage": "pending"},
        "metadata": task_data.metadata or {},
        "research_tree": None,
    }
    state.tasks[task_id] = task_info
    state.execution_logs[task_id] = []
    await state.broadcast("task_created", task_info)
    asyncio.create_task(execute_adaptive_task(task_id, task_data.content, task_data.metadata))
    return task_info
