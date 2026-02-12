"""质量保障和记忆管理路由"""

from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException

from src import MemoryType
from state import state

router = APIRouter()


# ==================== 质量保障 API ====================

@router.get("/api/quality/{task_id}")
async def get_quality_report(task_id: str):
    if task_id not in state.tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    report = state.quality_reports.get(task_id)
    if not report:
        return {"task_id": task_id, "report": None, "message": "质量报告尚未生成"}
    return {"task_id": task_id, "report": report}


@router.post("/api/quality/evaluate")
async def evaluate_quality(data: Dict[str, Any]):
    if not state.quality_assurance:
        raise HTTPException(status_code=503, detail="质量保障系统未初始化")
    content = data.get("content", "")
    if not content:
        raise HTTPException(status_code=400, detail="content 不能为空")
    report = await state.quality_assurance.evaluate_quality(
        content=content,
        task_description=data.get("task_description", ""),
        expected_output=data.get("expected_output", ""),
        agent_type=data.get("agent_type", "researcher"),
    )
    return report.to_dict()


@router.post("/api/quality/reflect")
async def reflect_and_improve(data: Dict[str, Any]):
    if not state.quality_assurance:
        raise HTTPException(status_code=503, detail="质量保障系统未初始化")
    content = data.get("content", "")
    if not content:
        raise HTTPException(status_code=400, detail="content 不能为空")
    quality_report = await state.quality_assurance.evaluate_quality(
        content=content, task_description=data.get("task_description", ""),
        expected_output="", agent_type="researcher",
    )
    result = await state.quality_assurance.reflect_and_improve(
        content=content, task_description=data.get("task_description", ""),
        quality_report=quality_report,
    )
    return result.to_dict()


@router.post("/api/quality/detect-conflicts")
async def detect_conflicts(data: Dict[str, Any]):
    if not state.quality_assurance:
        raise HTTPException(status_code=503, detail="质量保障系统未初始化")
    results = data.get("results", [])
    if len(results) < 2:
        raise HTTPException(status_code=400, detail="至少需要2个结果进行冲突检测")
    report = await state.quality_assurance.detect_conflicts(
        results=results, task_description=data.get("task_description", ""),
    )
    return report.to_dict()


# ==================== 记忆管理 API ====================

@router.get("/api/memory/stats")
async def get_memory_stats():
    if not state.memory_manager:
        raise HTTPException(status_code=503, detail="记忆管理器未初始化")
    return state.memory_manager.get_stats()


@router.get("/api/memory/task/{task_id}")
async def get_task_memory(task_id: str):
    if not state.memory_manager:
        raise HTTPException(status_code=503, detail="记忆管理器未初始化")
    memories = state.memory_manager.search_by_task(task_id, limit=20)
    return {
        "task_id": task_id,
        "memories": [m.to_dict() for m in memories],
        "context": state.memory_manager.get_context_for_task(task_id),
    }


@router.post("/api/memory/store")
async def store_memory(data: Dict[str, Any]):
    if not state.memory_manager:
        raise HTTPException(status_code=503, detail="记忆管理器未初始化")
    content = data.get("content", "")
    if not content:
        raise HTTPException(status_code=400, detail="content 不能为空")
    type_map = {
        "short_term": MemoryType.SHORT_TERM, "long_term": MemoryType.LONG_TERM,
        "working": MemoryType.WORKING, "semantic": MemoryType.SEMANTIC,
    }
    mt = type_map.get(data.get("memory_type", "short_term"), MemoryType.SHORT_TERM)
    memory = state.memory_manager.store(
        content=content, memory_type=mt, task_id=data.get("task_id"),
        agent_type=data.get("agent_type"), tags=data.get("tags", []),
        importance=data.get("importance", 0.5),
    )
    return memory.to_dict()


@router.get("/api/memory/search")
async def search_memory(tags: Optional[str] = None, agent_type: Optional[str] = None, limit: int = 10):
    if not state.memory_manager:
        raise HTTPException(status_code=503, detail="记忆管理器未初始化")
    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        memories = state.memory_manager.search_by_tags(tag_list, limit=limit)
    elif agent_type:
        memories = state.memory_manager.search_by_agent(agent_type, limit=limit)
    else:
        memories = list(state.memory_manager._short_term.values())[-limit:]
    return {"memories": [m.to_dict() for m in memories]}
