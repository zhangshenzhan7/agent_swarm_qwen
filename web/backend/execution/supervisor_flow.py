"""主管规划流程"""

import asyncio
import traceback
from datetime import datetime
from typing import Dict, Any, Optional

from src import TaskStatus, AgentStatus, ExecutionFlow
from state import state
from utils import clean_thinking_tags
from execution.delegate import create_delegate_callback
from execution.swarm_flow import execute_task_with_swarm


async def execute_task_with_supervisor(task_id: str, content: str, metadata: Optional[Dict] = None):
    """先经过 AI 主管规划，再分配给智能体团队执行 - 支持多主管并行"""
    task = state.tasks[task_id]
    supervisor_instance = None  # 当前任务的主管实例
    supervisor_agent_instance = None  # 主管的 UI 显示实例
    
    async def log_event(message: str, level: str = "info"):
        """记录执行日志并广播 - 清理 thinking 标签"""
        clean_message = clean_thinking_tags(message)
        if not clean_message:
            return
        # 任务可能已被用户删除
        if task_id not in state.execution_logs:
            return
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "message": clean_message,
            "level": level
        }
        state.execution_logs[task_id].append(log_entry)
        await state.broadcast("task_log", {"task_id": task_id, "log": log_entry})
    
    async def log_agent_event(agent_id: str, message: str, level: str = "info", is_stream: bool = False):
        """记录 Agent 执行日志并广播"""
        if agent_id not in state.agent_logs:
            state.agent_logs[agent_id] = []
        
        # 获取 agent 所属的 task_id
        bound_task_id = state.get_task_for_agent(agent_id) or task_id
        
        if is_stream:
            # 流式输出，追加到当前流（保留 thinking 标签，前端会处理）
            state.agent_streams[agent_id] = state.agent_streams.get(agent_id, "") + message
            await state.broadcast("agent_stream", {
                "agent_id": agent_id,
                "task_id": bound_task_id,
                "content": message,
                "full_content": state.agent_streams[agent_id]
            })
        else:
            # 普通日志 - 清理 thinking 标签
            clean_message = clean_thinking_tags(message)
            if not clean_message:  # 如果清理后为空，跳过
                return
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "message": clean_message,
                "level": level
            }
            state.agent_logs[agent_id].append(log_entry)
            # 只保留最近 100 条日志
            if len(state.agent_logs[agent_id]) > 100:
                state.agent_logs[agent_id] = state.agent_logs[agent_id][-100:]
            await state.broadcast("agent_log", {"agent_id": agent_id, "task_id": bound_task_id, "log": log_entry})
    
    async def clear_agent_stream(agent_id: str):
        """清空 Agent 的流式输出"""
        state.agent_streams[agent_id] = ""
        await state.broadcast("agent_stream_clear", {"agent_id": agent_id, "task_id": task_id})
    
    async def update_stage(idx: int, status: str, details: str = None):
        """更新执行阶段状态"""
        # 任务可能已被用户删除
        if task_id not in state.tasks:
            return
        task["stages"][idx]["status"] = status
        if status == "running":
            task["stages"][idx]["started_at"] = datetime.now().isoformat()
        elif status in ["completed", "failed"]:
            task["stages"][idx]["completed_at"] = datetime.now().isoformat()
        if details:
            task["stages"][idx]["details"] = details
        
        # 计算进度：completed 算 100%，running 算 50%
        total = len(task["stages"])
        progress = 0
        for s in task["stages"]:
            if s["status"] == "completed":
                progress += 100
            elif s["status"] == "running":
                progress += 50
        task["progress"]["percentage"] = min(int(progress / total), 99) if total > 0 else 0
        task["progress"]["current_stage"] = task["stages"][idx]["name"]
        await state.broadcast("task_updated", task)
    
    try:
        await log_event(f"📋 收到任务: {content}")
        
        # 检查任务是否已被取消
        if task_id in state.cancelled_tasks or task_id not in state.tasks:
            return
        
        # ========== 阶段 0: 主管规划（创建独立实例）==========
        await update_stage(0, "running")
        
        # 创建主管实例（支持多任务并行）
        supervisor_agent_instance = state.create_agent_instance("supervisor", content[:50])
        supervisor_agent_instance["status"] = AgentStatus.RUNNING.value
        await state.broadcast("agent_created", supervisor_agent_instance)
        await state.broadcast("agent_updated", supervisor_agent_instance)
        
        supervisor_instance_id = supervisor_agent_instance["id"]
        # 绑定主管实例到当前任务
        state.bind_agent_to_task(supervisor_instance_id, task_id)
        await clear_agent_stream(supervisor_instance_id)
        await log_agent_event(supervisor_instance_id, "开始分析任务...", "info")
        await log_event(f"👔 {supervisor_agent_instance['name']} 正在分析和规划任务...")
        
        refined_content = content  # 默认使用原始内容
        plan = None
        
        if state.supervisor_config and state.swarm:
            # 创建独立的 Supervisor 实例
            supervisor_instance = state.create_supervisor_instance(task_id)
            supervisor_instance.set_delegate_callback(create_delegate_callback())
            
            # 创建流式回调函数 — 同时解析规划阶段推送前端进度
            async def supervisor_stream_callback(chunk: str):
                """将主管的流式输出广播到前端，并根据阶段标记更新 stages"""
                # 检测阶段切换标记（Supervisor 在 stream 中发送 [NEW_PHASE] 前缀）
                if "[NEW_PHASE]" in chunk:
                    clean_chunk = chunk.replace("[NEW_PHASE]", "")
                    # 根据内容判断当前规划子阶段，更新 stage details
                    if "分析" in clean_chunk or "评估" in clean_chunk:
                        task["stages"][0]["details"] = "正在分析任务..."
                    elif "委派" in clean_chunk or "搜索" in clean_chunk:
                        task["stages"][0]["details"] = "正在委派分析和调研..."
                    elif "改写" in clean_chunk:
                        task["stages"][0]["details"] = "正在改写任务..."
                    elif "执行计划" in clean_chunk or "制定" in clean_chunk:
                        task["stages"][0]["details"] = "正在制定执行计划..."
                    await state.broadcast("task_updated", task)
                await log_agent_event(supervisor_instance_id, chunk, "info", is_stream=True)
            
            # 调用主管进行任务规划（流式输出）
            plan = await supervisor_instance.plan_task(content, metadata, stream_callback=supervisor_stream_callback)
            task["plan"] = plan.to_dict()
            
            # 记录 ReAct 规划过程到主管日志
            for trace in plan.react_trace:
                phase = trace.get("phase", "")
                trace_type = trace["type"].upper()
                trace_content = trace["content"]
                
                # 确保 trace_content 是字符串
                if not isinstance(trace_content, str):
                    trace_content = str(trace_content)
                
                # 清理 thinking 标签
                trace_content = clean_thinking_tags(trace_content)
                
                # 记录到主管的日志
                await log_agent_event(supervisor_instance_id, f"[{phase}] {trace_content}", "info")
                
                # 截断过长内容用于任务日志
                if len(trace_content) > 300:
                    trace_content = trace_content[:300] + "..."
                
                await log_event(f"💭 [{phase}] {trace_content}")
            
            # 显示规划结果
            await log_agent_event(supervisor_instance_id, f"任务分析完成: 复杂度 {plan.estimated_complexity:.1f}/10", "success")
            await log_event(f"📊 任务分析: 复杂度 {plan.estimated_complexity:.1f}/10, 类型 {plan.task_analysis.get('task_type', 'N/A')}")
            await log_event(f"🎯 核心意图: {plan.task_analysis.get('core_intent', 'N/A')}")
            
            if plan.key_objectives:
                await log_agent_event(supervisor_instance_id, f"关键目标: {', '.join(plan.key_objectives[:3])}", "info")
                await log_event(f"📌 关键目标: {', '.join(plan.key_objectives[:3])}")
            
            if plan.suggested_agents:
                await log_agent_event(supervisor_instance_id, f"建议智能体: {', '.join(plan.suggested_agents)}", "info")
                await log_event(f"👥 建议智能体: {', '.join(plan.suggested_agents)}")
            
            # 显示改写后的任务
            await log_agent_event(supervisor_instance_id, f"改写任务: {plan.refined_task}", "info")
            await log_event(f"✏️ 改写任务: {plan.refined_task[:200]}..." if len(plan.refined_task) > 200 else f"✏️ 改写任务: {plan.refined_task}")
            
            # 显示执行计划（包含依赖关系）
            if plan.execution_plan:
                await log_agent_event(supervisor_instance_id, f"执行计划: {len(plan.execution_plan)} 个步骤", "success")
                await log_event(f"📋 执行计划: {len(plan.execution_plan)} 个步骤（动态依赖链路）")
                
                for i, step in enumerate(plan.execution_plan[:8], 1):
                    step_name = step.get("name", f"步骤{i}")
                    agent_type = step.get("agent_type", "unknown")
                    dependencies = step.get("dependencies", [])
                    
                    # 显示依赖关系
                    if dependencies:
                        dep_str = f" ← 依赖: {', '.join(dependencies)}"
                    else:
                        dep_str = " (起始步骤)"
                    
                    await log_agent_event(supervisor_instance_id, f"  {i}. [{agent_type}] {step_name}{dep_str}", "info")
                    await log_event(f"   {i}. [{agent_type}] {step_name}{dep_str}")
                
                # 显示执行流程图
                if plan.execution_flow:
                    flow_info = plan.execution_flow.get_progress()
                    await log_event(f"📊 执行流程: {flow_info['total']} 个节点，执行顺序: {' → '.join(plan.execution_flow.execution_order[:5])}")
            
            await update_stage(0, "completed", f"规划完成，{len(plan.execution_plan)} 个步骤")
            await log_agent_event(supervisor_instance_id, "规划完成，准备分配任务给员工", "success")
            
            # 更新主管模板统计
            state.agents["supervisor"]["stats"]["tasks_completed"] += 1
            
            # 检查是否是简单问题直接回答
            task_type = plan.task_analysis.get("task_type", "")
            is_direct_answer = task_type == "simple_direct"
            direct_answer = plan.task_analysis.get("direct_answer", "")
            
            # 使用主管判断的 output_type 覆盖任务的 output_type
            supervisor_output_type = plan.task_analysis.get("output_type", "")
            if supervisor_output_type:
                task["output_type"] = supervisor_output_type
                await log_event(f"🎯 主管判断输出类型: {supervisor_output_type}")
                await state.broadcast("task_updated", task)
            
            # 调试日志
            print(f"[DEBUG] task_type={task_type}, is_direct={is_direct_answer}, direct_answer={direct_answer[:50] if direct_answer else 'None'}")
            await log_event(f"🔍 任务类型: {task_type}, 直接回答: {is_direct_answer}")
            
            if is_direct_answer and direct_answer:
                # 简单问题，主管已直接回答，跳过员工执行
                await log_event(f"✅ 简单问题，主管已直接回答", "success")
                
                # 标记所有阶段为跳过
                for i in range(1, len(task["stages"])):
                    await update_stage(i, "skipped", "简单问题，无需执行")
                
                # 清理 THINKING 标签后设置结果
                task["result"] = clean_thinking_tags(direct_answer)
                task["status"] = TaskStatus.COMPLETED.value
                task["completed_at"] = datetime.now().isoformat()
                task["progress"]["percentage"] = 100
                
                await state.broadcast("task_completed", task)
                await log_event("🎉 任务完成!", "success")
                return
            
            # 使用改写后的任务
            refined_content = plan.refined_task
            
            # 将规划信息添加到 metadata
            if metadata is None:
                metadata = {}
            metadata["supervisor_plan"] = {
                "refined_task": plan.refined_task,
                "execution_plan": plan.execution_plan,
                "suggested_agents": plan.suggested_agents,
                "key_objectives": plan.key_objectives,
            }
        else:
            # 没有主管配置，直接执行
            await update_stage(0, "completed", "主管未初始化，直接执行")
            await log_event("⚠️ AI 主管未初始化，直接分配给智能体团队")
        
        # 继续执行智能体团队流程（使用改写后的任务）
        # 传递主管建议的智能体列表和执行流程
        suggested_agents = plan.suggested_agents if plan else []
        execution_flow = plan.execution_flow if plan else None
        await execute_task_with_swarm(task_id, refined_content, metadata, start_stage=1, suggested_agents=suggested_agents, execution_flow=execution_flow)
        
    except asyncio.CancelledError:
        # 任务被取消，静默退出
        if task_id in state.tasks:
            task = state.tasks[task_id]
            task["status"] = TaskStatus.FAILED.value
            task["error"] = "任务已被用户取消"
            await state.broadcast("task_deleted", {"task_id": task_id})
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        error_msg = str(e) if str(e) else f"未知错误: {type(e).__name__}"
        print(f"❌ 主管规划失败: {error_msg}")
        print(f"详细错误:\n{error_trace}")
        if task_id in state.tasks:
            task["status"] = TaskStatus.FAILED.value
            task["error"] = error_msg
            await state.broadcast("task_failed", {"task_id": task_id, "error": error_msg})
        await log_event(f"❌ 主管规划失败: {error_msg}\n{error_trace[:500]}", "error")
    
    finally:
        # 释放主管实例
        if supervisor_agent_instance:
            supervisor_agent_instance["status"] = AgentStatus.IDLE.value
            await state.broadcast("agent_updated", supervisor_agent_instance)
            await asyncio.sleep(0.3)
            state.release_agent_instance(supervisor_agent_instance["id"])
            await state.broadcast("agent_removed", {"id": supervisor_agent_instance["id"]})
        
        # 释放 Supervisor 逻辑实例
        state.release_supervisor_instance(task_id)
        # 清理取消标记和执行任务引用
        state.cancelled_tasks.discard(task_id)
        state.running_async_tasks.pop(task_id, None)
