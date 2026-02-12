"""AgentSwarm 执行进度监控"""

import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List

from src import TaskStatus, AgentStatus, PREDEFINED_ROLES
from state import state
from execution.helpers import check_and_start_ready_steps, analyze_dependency_layers, map_role_hint_to_key


async def monitor_execution_progress(
    task_id: str,
    swarm_task_id: str,
    log_event,
    update_stage,
    update_agent_status,
    stage_offset: int = 0,
    suggested_agents: Optional[List[str]] = None
):
    """监控 AgentSwarm 执行进度并实时更新 UI - 支持动态创建多个 Agent 实例"""
    task = state.tasks[task_id]
    last_status = None
    last_progress = {}
    created_instances: List[str] = []
    suggested_agents = suggested_agents or []
    step_agent_mapping: Dict[str, str] = {}

    async def update_step_status(step_id: str, status: str, agent_id: str = None, agent_name: str = None, output_data: Any = None, error: str = None):
        """更新执行流程中的步骤状态并广播"""
        started_at = None
        completed_at = None
        if task.get("plan") and task["plan"].get("execution_flow"):
            steps = task["plan"]["execution_flow"].get("steps", {})
            if step_id in steps:
                steps[step_id]["status"] = status
                if agent_id:
                    steps[step_id]["agent_id"] = agent_id
                if agent_name:
                    steps[step_id]["agent_name"] = agent_name
                if status == "running":
                    steps[step_id]["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                elif status in ("completed", "failed"):
                    steps[step_id]["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if output_data:
                    steps[step_id]["output_data"] = output_data
                if error:
                    steps[step_id]["error"] = error

                if agent_id and agent_id in state.agent_logs:
                    steps[step_id]["logs"] = state.agent_logs[agent_id].copy()

                started_at = steps[step_id].get("started_at")
                completed_at = steps[step_id].get("completed_at")

                total = len(steps)
                completed = sum(1 for s in steps.values() if s.get("status") == "completed")
                running = sum(1 for s in steps.values() if s.get("status") == "running")
                failed = sum(1 for s in steps.values() if s.get("status") == "failed")
                task["plan"]["execution_flow"]["progress"] = {
                    "total": total,
                    "completed": completed,
                    "running": running,
                    "failed": failed,
                    "progress_percent": int(completed / total * 100) if total > 0 else 0,
                }

        agent_logs = state.agent_logs.get(agent_id, []) if agent_id else []
        state.subtask_results[step_id] = {
            "status": status,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "output_data": output_data,
            "error": error,
            "logs": agent_logs.copy(),
        }

        await state.broadcast("step_status_changed", {
            "task_id": task_id,
            "step_id": step_id,
            "status": status,
            "output_data": output_data,
            "error": error,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "started_at": started_at,
            "completed_at": completed_at,
            "logs": agent_logs,
        })

    async def create_and_activate_agent(role_key: str, task_desc: str, step_id: str = None) -> str:
        """创建并激活 Agent 实例"""
        instance = state.create_agent_instance(role_key, task_desc)
        instance["status"] = AgentStatus.RUNNING.value
        created_instances.append(instance["id"])
        task["assigned_agents"].append(instance["id"])

        # 绑定 agent 实例到当前任务
        state.bind_agent_to_task(instance["id"], task_id)

        if instance["id"] not in state.agent_logs:
            state.agent_logs[instance["id"]] = []

        start_log = {
            "timestamp": datetime.now().isoformat(),
            "message": f"开始执行任务: {task_desc}",
            "level": "info"
        }
        state.agent_logs[instance["id"]].append(start_log)
        await state.broadcast("agent_log", {"agent_id": instance["id"], "task_id": task_id, "log": start_log})

        if step_id:
            step_agent_mapping[step_id] = instance["id"]
            await update_step_status(step_id, "running", instance["id"], instance["name"])

        await state.broadcast("agent_created", instance)
        await state.broadcast("agent_updated", instance)
        await log_event(f"🤖 创建 {instance['name']}，执行: {task_desc[:30]}...")

        return instance["id"]

    async def release_agent_instance(instance_id: str, step_id: str = None, success: bool = True, output: Any = None, error: str = None):
        """释放 Agent 实例"""
        if instance_id in state.active_agents:
            agent = state.active_agents[instance_id]
            agent["status"] = AgentStatus.IDLE.value
            agent["current_task"] = None

            if success:
                complete_log = {
                    "timestamp": datetime.now().isoformat(),
                    "message": f"任务执行成功",
                    "level": "success"
                }
            else:
                complete_log = {
                    "timestamp": datetime.now().isoformat(),
                    "message": f"任务执行失败: {error or '未知错误'}",
                    "level": "error"
                }

            if instance_id not in state.agent_logs:
                state.agent_logs[instance_id] = []
            state.agent_logs[instance_id].append(complete_log)
            await state.broadcast("agent_log", {"agent_id": instance_id, "task_id": task_id, "log": complete_log})

            role_key = agent.get("role")
            if role_key:
                base_agent_id = f"agent_{role_key}"
                if base_agent_id in state.agents:
                    state.agents[base_agent_id]["stats"]["tasks_completed"] += 1
                    if not success:
                        total = state.agents[base_agent_id]["stats"]["tasks_completed"]
                        current_rate = state.agents[base_agent_id]["stats"].get("success_rate", 100)
                        state.agents[base_agent_id]["stats"]["success_rate"] = max(0, int((current_rate * (total - 1) + (100 if success else 0)) / total))
                    await state.broadcast("agent_updated", state.agents[base_agent_id])

            await state.broadcast("agent_updated", agent)
            await log_event(f"✅ {agent['name']} 完成任务")

            if step_id:
                status = "completed" if success else "failed"
                await update_step_status(step_id, status, instance_id, agent["name"], output, error)

            await asyncio.sleep(0.5)
            state.release_agent_instance(instance_id)
            await state.broadcast("agent_removed", {"id": instance_id})

    # 跟踪已完成的步骤数（用于增量更新）
    last_completed_count = 0
    dep_layers_cache = None

    try:
        while True:
            await asyncio.sleep(0.5)

            try:
                progress = await state.swarm.get_progress(swarm_task_id)
                status = await state.swarm.get_task_status(swarm_task_id)

                if status != last_status:
                    last_status = status

                    if status == TaskStatus.DECOMPOSING:
                        task["status"] = TaskStatus.DECOMPOSING.value
                        await update_stage(stage_offset + 1, "running")
                        await log_event("🔧 正在将任务分解为子任务...")

                    elif status == TaskStatus.EXECUTING:
                        subtask_count = progress.get("total_subtasks", 0)
                        await update_stage(stage_offset + 1, "completed", f"分解为 {subtask_count} 个子任务")

                        await update_stage(stage_offset + 2, "running")

                        execution_steps = []
                        if task.get("plan") and task["plan"].get("execution_flow"):
                            steps = task["plan"]["execution_flow"].get("steps", {})
                            execution_steps = list(steps.values())

                        if execution_steps:
                            await log_event(f"👥 检测到 {len(execution_steps)} 个执行步骤，按依赖关系分层执行...")

                            dep_layers_cache = analyze_dependency_layers(execution_steps)
                            await log_event(f"📊 依赖分析: {len(dep_layers_cache)} 层执行流程")
                            for i, layer in enumerate(dep_layers_cache):
                                layer_names = [s.get("name", s.get("step_id")) for s in layer]
                                await log_event(f"   第 {i+1} 层: {', '.join(layer_names)}")

                            steps_dict = task["plan"]["execution_flow"].get("steps", {})
                            for step in execution_steps:
                                step_id = step.get("step_id")
                                deps = step.get("dependencies", [])
                                valid_deps = [d for d in deps if d in steps_dict]
                                if valid_deps:
                                    await update_step_status(step_id, "waiting")

                            await update_stage(stage_offset + 2, "completed", f"分析完成，{len(dep_layers_cache)} 层执行流程")

                            task["status"] = TaskStatus.EXECUTING.value
                            await update_stage(stage_offset + 3, "running")

                            if dep_layers_cache:
                                first_layer = dep_layers_cache[0]
                                await log_event(f"⚡ 开始执行第 1/{len(dep_layers_cache)} 层: {len(first_layer)} 个步骤并行")

                                for step in first_layer:
                                    step_id = step.get("step_id")
                                    agent_type = step.get("agent_type", "researcher")
                                    step_name = step.get("name", "执行任务")
                                    role_key = map_role_hint_to_key(agent_type)
                                    if role_key:
                                        await create_and_activate_agent(role_key, step_name, step_id)

                                await log_event(f"   已启动 {len(first_layer)} 个 AI 员工（第1层）")

                        elif suggested_agents:
                            await log_event(f"👥 使用建议的智能体类型创建实例...")
                            agents_per_type = max(1, subtask_count // len(suggested_agents))

                            for agent_type in suggested_agents:
                                role_key = map_role_hint_to_key(agent_type)
                                if role_key:
                                    num_instances = min(agents_per_type, 3)
                                    for i in range(num_instances):
                                        await create_and_activate_agent(role_key, f"并行执行 {agent_type} 任务 #{i+1}")

                            await update_stage(stage_offset + 2, "completed", f"已创建 {len(created_instances)} 个 AI 员工实例")
                            task["status"] = TaskStatus.EXECUTING.value
                            await update_stage(stage_offset + 3, "running")
                            await log_event(f"⚡ {len(created_instances)} 个 AI 员工开始并行执行任务...")
                        else:
                            await log_event(f"👥 使用默认智能体类型...")
                            for role_key in ["searcher", "analyst"]:
                                await create_and_activate_agent(role_key, "执行子任务")

                            await update_stage(stage_offset + 2, "completed", f"已创建 {len(created_instances)} 个 AI 员工实例")
                            task["status"] = TaskStatus.EXECUTING.value
                            await update_stage(stage_offset + 3, "running")
                            await log_event(f"⚡ {len(created_instances)} 个 AI 员工开始并行执行任务...")

                    elif status == TaskStatus.AGGREGATING:
                        await update_stage(stage_offset + 3, "completed", "所有子任务执行完成")

                        if task.get("plan") and task["plan"].get("execution_flow"):
                            steps = task["plan"]["execution_flow"].get("steps", {})
                            for step_id, step in steps.items():
                                if step.get("status") == "running":
                                    agent_id = step_agent_mapping.get(step_id)
                                    await update_step_status(step_id, "completed", agent_id)
                                    if agent_id and agent_id in state.active_agents:
                                        await release_agent_instance(agent_id, step_id, success=True)

                        for instance_id in list(created_instances):
                            if instance_id in state.active_agents:
                                found_step_id = None
                                for sid, aid in step_agent_mapping.items():
                                    if aid == instance_id:
                                        found_step_id = sid
                                        break
                                await release_agent_instance(instance_id, found_step_id, success=True)

                        task["status"] = TaskStatus.AGGREGATING.value
                        await update_stage(stage_offset + 4, "running")
                        await log_event("📊 正在聚合执行结果...")

                    elif status == TaskStatus.COMPLETED:
                        await update_stage(stage_offset + 4, "completed", "结果聚合完成")
                        break

                    elif status == TaskStatus.FAILED:
                        break

                # 更新进度百分比和层级进度
                if progress != last_progress:
                    last_progress = progress.copy()

                    completed_subtasks = progress.get("completed_subtasks", 0)
                    total_subtasks = progress.get("total_subtasks", 1)

                    if total_subtasks > 0:
                        base_pct = 20
                        exec_pct = int(completed_subtasks / total_subtasks * 60)
                        task["progress"]["percentage"] = min(base_pct + exec_pct, 80)
                        await state.broadcast("task_updated", task)

                    if task.get("plan") and task["plan"].get("execution_flow"):
                        steps = task["plan"]["execution_flow"].get("steps", {})
                        if steps:
                            if completed_subtasks > last_completed_count:
                                newly_completed = completed_subtasks - last_completed_count
                                last_completed_count = completed_subtasks

                                running_steps = [
                                    (sid, step) for sid, step in steps.items()
                                    if step.get("status") == "running"
                                ]
                                running_steps.sort(key=lambda x: x[1].get("step_number", 0))

                                for i, (step_id, step) in enumerate(running_steps):
                                    if i >= newly_completed:
                                        break

                                    agent_id = step_agent_mapping.get(step_id)
                                    agent_name = None
                                    if agent_id and agent_id in state.active_agents:
                                        agent_name = state.active_agents[agent_id].get("name")

                                    await update_step_status(step_id, "completed", agent_id, agent_name)
                                    await log_event(f"✅ 步骤完成: {step.get('name', step_id)}")

                                    if agent_id:
                                        await release_agent_instance(agent_id, step_id, success=True)

                                await check_and_start_ready_steps(
                                    task_id, task, created_instances, step_agent_mapping,
                                    log_event, create_and_activate_agent, update_step_status
                                )

                            completed_count = sum(1 for s in steps.values() if s.get("status") == "completed")
                            running_count = sum(1 for s in steps.values() if s.get("status") == "running")
                            waiting_count = sum(1 for s in steps.values() if s.get("status") == "waiting")
                            total_steps = len(steps)

                            if dep_layers_cache is None:
                                execution_steps = list(steps.values())
                                dep_layers_cache = analyze_dependency_layers(execution_steps)

                            current_layer = 0
                            completed_in_layer = 0
                            layer_total = 0

                            for layer_idx, layer in enumerate(dep_layers_cache):
                                layer_step_ids = {s.get("step_id") for s in layer}
                                layer_completed = sum(1 for sid in layer_step_ids if steps.get(sid, {}).get("status") == "completed")
                                layer_running = sum(1 for sid in layer_step_ids if steps.get(sid, {}).get("status") == "running")

                                if layer_running > 0 or (layer_completed < len(layer) and layer_completed > 0):
                                    current_layer = layer_idx + 1
                                    completed_in_layer = layer_completed
                                    layer_total = len(layer)
                                    break
                                elif layer_completed == len(layer):
                                    current_layer = layer_idx + 1
                                    continue

                            last_layer = progress.get("_last_layer", 0)
                            last_layer_completed = progress.get("_last_layer_completed", 0)

                            if current_layer != last_layer or completed_in_layer != last_layer_completed:
                                progress["_last_layer"] = current_layer
                                progress["_last_layer_completed"] = completed_in_layer

                                if current_layer > 0 and layer_total > 0:
                                    await log_event(f"📈 第 {current_layer}/{len(dep_layers_cache)} 层进度: {completed_in_layer}/{layer_total} 步骤完成 | 总进度: {completed_count}/{total_steps}")

            except Exception as e:
                pass

    except asyncio.CancelledError:
        pass
