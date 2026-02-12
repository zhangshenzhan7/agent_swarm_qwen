"""执行辅助函数"""

from datetime import datetime
from typing import Dict, Any, Optional, List

from src import PREDEFINED_ROLES, AgentStatus
from state import state


async def check_and_start_ready_steps(task_id: str, task: Dict, created_instances: List[str], step_agent_mapping: Dict[str, str], log_event, create_and_activate_agent, update_step_status):
    """检查并启动依赖已完成的步骤"""
    if not task.get("plan") or not task["plan"].get("execution_flow"):
        return
    
    steps = task["plan"]["execution_flow"].get("steps", {})
    if not steps:
        return
    
    # 获取已完成的步骤
    completed_steps = set()
    running_steps = set()
    waiting_steps = set()
    
    for step_id, step in steps.items():
        status = step.get("status", "pending")
        if status == "completed":
            completed_steps.add(step_id)
        elif status == "running":
            running_steps.add(step_id)
        elif status == "waiting":
            waiting_steps.add(step_id)
    
    # 检查 waiting 状态的步骤，看是否可以启动
    for step_id in list(waiting_steps):
        step = steps[step_id]
        deps = step.get("dependencies", [])
        valid_deps = [d for d in deps if d in steps]
        
        # 检查所有依赖是否已完成
        if all(d in completed_steps for d in valid_deps):
            # 依赖已完成，可以启动
            agent_type = step.get("agent_type", "researcher")
            step_name = step.get("name", "执行任务")
            role_key = map_role_hint_to_key(agent_type)
            
            if role_key and step_id not in step_agent_mapping:
                await log_event(f"🔄 依赖完成，启动步骤: {step_name}")
                instance_id = await create_and_activate_agent(role_key, step_name, step_id)
                
                # 记录依赖完成日志
                dep_names = [steps.get(d, {}).get("name", d) for d in valid_deps]
                dep_log = {
                    "timestamp": datetime.now().isoformat(),
                    "message": f"依赖步骤已完成: {', '.join(dep_names)}，开始执行",
                    "level": "info"
                }
                if instance_id in state.agent_logs:
                    state.agent_logs[instance_id].append(dep_log)
                    await state.broadcast("agent_log", {"agent_id": instance_id, "task_id": task_id, "log": dep_log})


def analyze_dependency_layers(steps: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """
    分析步骤的依赖关系，返回分层执行顺序
    
    Args:
        steps: 步骤列表
        
    Returns:
        分层的步骤列表，每层内的步骤可以并行执行
    """
    if not steps:
        return []
    
    # 构建步骤映射
    step_map = {s.get("step_id"): s for s in steps}
    step_ids = set(step_map.keys())
    
    # 计算每个步骤的依赖
    dependencies = {}
    for step in steps:
        step_id = step.get("step_id")
        deps = step.get("dependencies", [])
        # 只保留有效的依赖（存在于当前步骤列表中的）
        valid_deps = [d for d in deps if d in step_ids]
        dependencies[step_id] = set(valid_deps)
    
    layers = []
    completed = set()
    remaining = set(step_ids)
    
    while remaining:
        # 找出所有依赖已完成的步骤
        ready = []
        for step_id in remaining:
            deps = dependencies.get(step_id, set())
            if deps <= completed:
                ready.append(step_map[step_id])
        
        if not ready:
            # 存在循环依赖，打破循环：选择依赖最少的步骤
            min_deps = min(len(dependencies.get(sid, set()) - completed) for sid in remaining)
            for step_id in remaining:
                if len(dependencies.get(step_id, set()) - completed) == min_deps:
                    ready.append(step_map[step_id])
                    break
        
        # 按 step_number 排序
        ready.sort(key=lambda x: x.get("step_number", 0))
        
        layers.append(ready)
        
        # 更新状态
        for step in ready:
            step_id = step.get("step_id")
            remaining.discard(step_id)
            completed.add(step_id)
    
    return layers


def map_role_hint_to_key(role_hint: str) -> Optional[str]:
    """将角色提示映射到预定义角色 key"""
    role_hint_lower = role_hint.lower()
    
    # 精确匹配
    if role_hint_lower in PREDEFINED_ROLES:
        return role_hint_lower
    
    # 关键词匹配
    keyword_map = {
        "search": "searcher",
        "搜索": "searcher",
        "检索": "searcher",
        "analysis": "analyst",
        "分析": "analyst",
        "数据": "analyst",
        "fact": "fact_checker",
        "核查": "fact_checker",
        "验证": "fact_checker",
        "write": "writer",
        "撰写": "writer",
        "文档": "writer",
        "translate": "translator",
        "翻译": "translator",
        "code": "coder",
        "程序": "coder",
        "编程": "coder",
        "debug": "coder",
        "research": "researcher",
        "研究": "researcher",
        "summarize": "summarizer",
        "总结": "summarizer",
        "摘要": "summarizer",
        "creative": "creative",
        "创意": "creative",
        "构思": "creative",
        # 多模态生成
        "text_to_image": "text_to_image",
        "文生图": "text_to_image",
        "画图": "text_to_image",
        "生成图": "text_to_image",
        "text_to_video": "text_to_video",
        "文生视频": "text_to_video",
        "生成视频": "text_to_video",
        "image_to_video": "image_to_video",
        "图生视频": "image_to_video",
        "voice_synthesizer": "voice_synthesizer",
        "语音合成": "voice_synthesizer",
        "配音": "voice_synthesizer",
        # 视觉理解
        "image_analyst": "image_analyst",
        "图像分析": "image_analyst",
        "ocr": "ocr_reader",
        "图表": "chart_reader",
        "ui分析": "ui_analyst",
        "图像描述": "image_describer",
        "视觉问答": "visual_qa",
        # 其他角色
        "editor": "writer",
        "编辑": "writer",
        "copywriter": "writer",
        "文案": "writer",
        "strategist": "analyst",
        "战略": "analyst",
        "consultant": "researcher",
        "咨询": "researcher",
        "extractor": "analyst",
        "提取": "analyst",
        "classifier": "analyst",
        "分类": "analyst",
        "formatter": "writer",
        "格式": "writer",
        "document_analyst": "researcher",
        "legal_reviewer": "researcher",
        "architect": "coder",
        "架构": "coder",
        "reviewer": "coder",
        "审查": "fact_checker",
        "debugger": "coder",
        "assistant": "summarizer",
    }
    
    for keyword, role_key in keyword_map.items():
        if keyword in role_hint_lower:
            return role_key
    
    # 默认返回 searcher
    return "searcher"
